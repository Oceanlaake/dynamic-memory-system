"""Behavioral regressions for bounded, query-seeded state history completion."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.routes import get_dynamic_state_resolver, get_retriever, get_store
from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.main import app
from backend.query import resolve_query
from backend.retrieval.expansion import expand_state_slots
from backend.retrieval.keyword import BM25Retriever
from backend.schemas import CandidateMemory, Memory, QueryRequest, RetrievalResult
from backend.store import MemoryStore
from tests.test_contract import validator_for


def memory(memory_id, value="planned", *, subject="Jon", attribute="studio.status",
           session="session_1", date=None, content=None):
    return Memory.model_validate({
        "memory_id": memory_id, "subject": subject, "type": "state",
        "attribute": attribute, "value": value,
        "content": content or f"{subject}'s studio is {value}.",
        "time": {"session_id": session, "effective_at": date},
        "evidence": [{"session_id": session, "dia_id": f"{memory_id}:1"}],
    })


def retrieval(*memories, question="What is Jon's studio status now?"):
    return RetrievalResult(
        sample_id="sample", question=question, top_k=max(1, len(memories)), strategy="bm25",
        candidates=[CandidateMemory(memory=m, score=0.9, rank=i+1)
                    for i, m in enumerate(memories)],
    )


def query(initial, all_memories, **kwargs):
    return resolve_query(initial, all_memories, RuleBasedDynamicStateResolver(), **kwargs)


def test_later_state_missing_from_top_k_is_recovered_without_changing_baseline():
    old = memory("m1", date="2023-01-01")
    new = memory("m2", "open", session="session_2", date="2023-02-01")
    initial = retrieval(old)
    baseline = query(initial, [old, new])
    expanded = query(initial, [old, new], expand_slots=True)
    assert baseline.answer == old.content
    assert baseline.expansion.stop_reason == "disabled"
    assert expanded.answer == new.content
    assert expanded.evidence_status == "sufficient"
    assert expanded.effective_memories[0].memory_id == "m2"
    assert expanded.expansion.added_memory_ids == ["m2"]
    assert expanded.candidate_memories[1].candidate_source == "slot_expansion"
    assert expanded.candidate_memories[1].score == 0
    assert initial.candidates == baseline.candidate_memories
    assert len(initial.candidates) == 1
    validator_for("query.schema.json", "QueryResponse").validate(
        expanded.model_dump(mode="json", by_alias=True)
    )


def test_slot_normalization_deduplication_and_other_subjects_and_attributes():
    old = memory("m1", subject=" Jon ", attribute=" Studio.Status ")
    new = memory("m2", "open", subject="jon", attribute="studio.status", session="session_2")
    unrelated = memory("m3", subject="Gina")
    other_slot = memory("m4", attribute="studio.finance")
    expanded, trace = expand_state_slots(
        retrieval(old), [new, unrelated, old, other_slot, new], enabled=True,
    )
    assert [item.memory.memory_id for item in expanded.candidates] == ["m1", "m2"]
    assert trace.expanded_slots[0].model_dump() == {"subject": "jon", "attribute": "studio.status"}
    assert trace.added_memory_ids == ["m2"]


@pytest.mark.parametrize("question, attribute, reason", [
    ("What is Jon's gender?", "studio.status", "not_dynamic"),
    ("What is Jon's gender now?", "studio.status", "no_seed"),
    ("What is Jon's studio status?", None, "no_seed"),
    ("Where was Jon's studio in 2020?", "studio.status", "not_dynamic"),
])
def test_no_unrelated_or_unstructured_seed_expansion(question, attribute, reason):
    old = memory("m1", attribute=attribute)
    result, trace = expand_state_slots(
        retrieval(old, question=question), [old, memory("m2")], enabled=True,
    )
    assert trace.stop_reason == reason
    assert len(result.candidates) == 1


def test_subject_named_in_query_prevents_expanding_other_subject_seed():
    gina = memory("g1", subject="Gina")
    jon = memory("j1")
    _, trace = expand_state_slots(retrieval(gina), [gina, jon], enabled=True)
    assert trace.stop_reason == "no_seed"
    result = query(retrieval(gina), [gina, jon], expand_slots=True)
    assert result.answer is None
    assert result.evidence_status == "insufficient"


def test_no_new_memory_can_still_be_sufficient():
    old = memory("m1")
    result = query(retrieval(old), [old], expand_slots=True)
    assert result.expansion.stop_reason == "no_new_memory"
    assert result.answer == old.content
    assert result.evidence_status == "sufficient"


def test_cap_does_not_drop_initials_and_prevents_answering_incomplete_history():
    old = memory("m0")
    others = [memory(f"m{i}", f"stage{i}", session=f"session_{i+1}") for i in range(1, 4)]
    result = query(retrieval(old), [old, *others], expand_slots=True, max_expansion_memories=1)
    assert [c.memory.memory_id for c in result.candidate_memories] == ["m0", "m1"]
    assert result.expansion.truncated
    assert result.expansion.stop_reason == "candidate_limit"
    assert result.answer is None
    assert result.evidence == result.effective_memories == []
    assert result.evidence_status == "insufficient"


def test_exact_cap_is_not_truncation_and_store_order_is_irrelevant():
    old = memory("m0")
    new = memory("m1", "open", session="session_2")
    a = query(retrieval(old), [new, old], expand_slots=True, max_expansion_memories=1)
    b = query(retrieval(old), [old, new], expand_slots=True, max_expansion_memories=1)
    assert not a.expansion.truncated
    assert a.model_dump() == b.model_dump()


def test_expansion_exposes_conflict_instead_of_answering_stale_state():
    first = memory("m1", "open", session="unknown")
    second = memory("m2", "closed", session="unknown")
    result = query(retrieval(first), [first, second], expand_slots=True)
    assert result.expansion.stop_reason == "expanded"
    assert result.evidence_status == "conflict"
    assert result.answer is None


def test_change_question_needs_ordered_same_slot_history():
    old = memory("m1", date="2023-01-01")
    new = memory("m2", "open", date="2023-02-01", session="session_2")
    initial = retrieval(new, question="How did Jon's studio status change?")
    baseline = query(initial, [old, new])
    expanded = query(initial, [old, new], expand_slots=True)
    assert baseline.answer is None
    assert baseline.evidence_status == "missing_transition"
    assert expanded.answer == f"{old.content} → {new.content}"
    assert [m.memory_id for m in expanded.effective_memories] == ["m1", "m2"]
    assert len(expanded.evidence) == 2


def test_same_value_without_reliable_order_cannot_describe_change():
    old, new = memory("m1", session="unknown"), memory("m2", session="unknown")
    result = query(retrieval(old, question="How did Jon's studio status change?"),
                   [old, new], expand_slots=True)
    assert result.answer is None
    assert result.evidence_status == "unorderable"


def test_duration_recovers_same_slot_anchor_but_does_not_guess_cross_attribute_links():
    start = memory("m1", "started", date="2023-01-01", content="Jon started his studio.")
    end = memory("m2", "opened", session="session_2", date="2023-02-01",
                 content="Jon opened his studio.")
    initial = retrieval(end, question="How long did it take for Jon to open his studio?")
    result = query(initial, [start, end], expand_slots=True)
    assert result.evidence_status == "sufficient"
    assert [m.role for m in result.effective_memories] == ["start_time", "opening_time"]
    other_attribute = start.model_copy(update={"attribute": "employment_event"})
    missing = query(initial, [other_attribute, end], expand_slots=True)
    assert missing.answer is None
    assert missing.evidence_status == "missing_anchor"


def test_two_dates_alone_do_not_establish_duration_roles():
    first = memory("m1", "popular", date="2023-01-01")
    second = memory("m2", "busy", date="2023-02-01", session="session_2")
    result = query(retrieval(second, question="How long did it take for Jon to open his studio?"),
                   [first, second], expand_slots=True)
    assert result.answer is None
    assert result.evidence_status == "missing_anchor"


def test_degraded_retrieval_is_not_rescued_using_store_alone():
    initial = retrieval(memory("m1")).model_copy(update={"degraded": True})
    expanded, trace = expand_state_slots(initial, [memory("m2")], enabled=True)
    assert trace.stop_reason == "no_seed"
    assert len(expanded.candidates) == 1


def test_query_api_uses_only_requested_sample_and_validates_request(tmp_path):
    import json

    old, new = memory("m1"), memory("m2", "open", session="session_2")
    other = memory("m3", "closed", session="session_3")
    for sample_id, memories in [("sample", [old, new]), ("other", [other])]:
        (tmp_path / f"{sample_id}.json").write_text(json.dumps({
            "sample_id": sample_id, "memories": [m.model_dump() for m in memories],
        }))
    overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_store] = lambda: MemoryStore(tmp_path)
    app.dependency_overrides[get_retriever] = lambda: BM25Retriever()
    app.dependency_overrides[get_dynamic_state_resolver] = lambda: RuleBasedDynamicStateResolver()
    try:
        with TestClient(app) as client:
            payload = {"sample_id": "sample", "question": "What is Jon's studio status now?",
                       "top_k": 1, "expand_slots": True, "max_expansion_memories": 5}
            validator_for("query.schema.json", "QueryRequest").validate(payload)
            assert QueryRequest.model_validate(payload).expand_slots
            response = client.post("/api/query", json=payload)
            assert response.status_code == 200
            body = response.json()
            assert {c["memory"]["memory_id"] for c in body["candidate_memories"]} == {"m1", "m2"}
            assert body["answer"] == new.content
            assert client.post("/api/query", json={**payload, "max_expansion_memories": 0}).status_code == 422
            assert client.post("/api/query", json={**payload, "max_expansion_memories": 201}).status_code == 422
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)
