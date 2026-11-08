"""契约一致性测试：JSON Schema、Pydantic 模型、数据文件三者不能分叉。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from backend.graph_memory import MemoryGraph
from backend.schemas import CandidateMemory, Memory, QueryResponse, RetrievalResult

REPO_ROOT = Path(__file__).resolve().parents[1]
APIS = REPO_ROOT / "APIs"
SCHEMA_FILES = (
    "memory_schema.json", "retrieval.schema.json", "graph.schema.json", "query.schema.json",
)


def load_schema(name: str) -> dict:
    return json.loads((APIS / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def registry() -> Registry:
    reg: Registry = Registry()
    for name in SCHEMA_FILES:
        reg = reg.with_resource(name, Resource.from_contents(load_schema(name), default_specification=DRAFT202012))
    return reg


def validator_for(schema_name: str, definition: str) -> Draft202012Validator:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"{schema_name}#/$defs/{definition}",
    }
    return Draft202012Validator(schema, registry=registry())


@pytest.mark.parametrize("name", SCHEMA_FILES)
def test_schema_documents_are_valid(name: str) -> None:
    Draft202012Validator.check_schema(load_schema(name))


def test_memory_store_matches_memory_schema() -> None:
    validator = Draft202012Validator(load_schema("memory_schema.json"))
    for path in sorted((REPO_ROOT / "data" / "memories").glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        errors = sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
        assert not errors, f"{path.name}: {[e.message for e in errors]}"


def test_memory_model_roundtrips_through_json_schema() -> None:
    document = json.loads((REPO_ROOT / "data" / "memories" / "conv-30.json").read_text(encoding="utf-8"))
    memories = [Memory.model_validate(item) for item in document["memories"]]
    memory_item_validator = Draft202012Validator(
        load_schema("memory_schema.json")["properties"]["memories"]["items"]
    )
    for memory in memories:
        payload = memory.model_dump(mode="json")
        memory_item_validator.validate(payload)


def test_retrieval_result_roundtrips_through_json_schema() -> None:
    document = json.loads((REPO_ROOT / "data" / "memories" / "conv-30.json").read_text(encoding="utf-8"))
    memories = [Memory.model_validate(item) for item in document["memories"]]
    result = RetrievalResult(
        sample_id="conv-30",
        question="How long did it take for Jon to open his studio?",
        top_k=3,
        strategy="bm25",
        candidates=[
            CandidateMemory(memory=memory, score=1.0 - index / 10, rank=index + 1, matched_by=["keyword"])
            for index, memory in enumerate(memories[:3])
        ],
    )
    validator_for("retrieval.schema.json", "RetrievalResult").validate(
        result.model_dump(mode="json", exclude_none=True)
    )


def test_query_response_roundtrips_through_json_schema() -> None:
    document = json.loads((REPO_ROOT / "data" / "memories" / "conv-30.json").read_text(encoding="utf-8"))
    memories = [Memory.model_validate(item) for item in document["memories"]]
    response = QueryResponse.model_validate(
        {
            "sample_id": "conv-30",
            "question": "How long did it take for Jon to open his studio?",
            "candidate_memories": [
                {
                    "memory": memories[3].model_dump(mode="json"),
                    "score": 0.95,
                    "rank": 1,
                    "matched_by": ["keyword"],
                }
            ],
            "relations": [
                {
                    "from": "mem-conv30-002",
                    "to": "mem-conv30-004",
                    "relation": "SUPERSEDE",
                    "reason": "The studio lifecycle advanced from a plan to a scheduled opening.",
                }
            ],
            "effective_memories": [
                {"memory_id": "mem-conv30-001", "role": "start_time"},
                {"memory_id": "mem-conv30-004", "role": "opening_time"},
            ],
            "answer": "It took Jon six months to open his studio.",
            "evidence": [{"session_id": "session_1", "dia_id": "D1:2"}],
        }
    )
    validator_for("query.schema.json", "QueryResponse").validate(
        response.model_dump(mode="json", by_alias=True, exclude_none=True)
    )


def test_graph_document_roundtrips_through_json_schema() -> None:
    document = json.loads((REPO_ROOT / "data" / "memories" / "conv-30.json").read_text(encoding="utf-8"))
    memories = [Memory.model_validate(item) for item in document["memories"]]
    graph = MemoryGraph("conv-30", memories).document()
    validator_for("graph.schema.json", "GraphDocument").validate(
        graph.model_dump(mode="json", exclude_none=True)
    )


def _memory_payload(**time_fields) -> dict:
    return {
        "memory_id": "mem-conv30-900",
        "subject": "Jon",
        "type": "event",
        "content": "Jon scheduled the opening.",
        "time": {"session_id": "session_15", **time_fields},
        "evidence": [{"session_id": "session_15", "dia_id": "D15:5"}],
    }


def test_memory_time_effective_at_is_optional_but_supported() -> None:
    item = Draft202012Validator(load_schema("memory_schema.json")["properties"]["memories"]["items"])

    without = _memory_payload()
    item.validate(without)
    assert Memory.model_validate(without).time.effective_at is None

    with_effective = _memory_payload(date_time="10:04 am on 19 June, 2023", effective_at="2023-06-20")
    item.validate(with_effective)
    memory = Memory.model_validate(with_effective)
    assert memory.time.session_id == "session_15"
    assert memory.time.date_time == "10:04 am on 19 June, 2023"
    assert memory.time.effective_at == "2023-06-20"


def test_memory_time_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        Memory.model_validate(_memory_payload(resolved_date="2023-06-20"))


def test_retrieval_candidate_carries_effective_at() -> None:
    memory = Memory.model_validate(
        _memory_payload(date_time="10:04 am on 19 June, 2023", effective_at="2023-06-20")
    )
    candidate = CandidateMemory(memory=memory, score=0.9, rank=1, matched_by=["embedding"])
    payload = candidate.model_dump(mode="json", exclude_none=True)
    assert payload["memory"]["time"]["effective_at"] == "2023-06-20"
    validator_for("retrieval.schema.json", "CandidateMemory").validate(payload)
