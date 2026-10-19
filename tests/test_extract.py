"""A2 抽取流水线测试。

关注三件事：

1. LoCoMo 解析是否稳定（10 个样本都能读、turn 索引可用）；
2. 产出的 Memory JSON 是否满足 ``APIs/memory_schema.json`` 与证据可追溯；
3. 抽取过程是否完全不依赖 ``qa``（避免测试集泄漏）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.extract.locomo import (
    dia_sort_key,
    load_dataset,
    parse_session_date,
    resolve_effective_date,
    session_id_from_dia_id,
)
from backend.extract.pipeline import ExtractionConfig, extract_sample
from backend.extract.postprocess import (
    NormalizeStats,
    canonicalize_values,
    merge_same_state,
    validate_document,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = REPO_ROOT / "data" / "raw" / "locomo10.json"
OUTPUT_DIR = REPO_ROOT / "outputs" / "memories"


def _normalized(text: str) -> str:
    """与后处理一致的空白归一（原数据里有双空格）。"""

    return " ".join(text.split()).lower()


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(RAW_PATH)


class RecordingClient:
    """记录提示词、返回空结果的假客户端。"""

    name = "recording"

    def __init__(self) -> None:
        self.prompts: list[tuple[str, str]] = []

    def extract_json(self, system_prompt: str, user_prompt: str) -> dict:
        self.prompts.append((system_prompt, user_prompt))
        return {"memories": [], "attributes": {}}


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
def test_dataset_has_all_samples(dataset):
    assert len(dataset) == 10
    assert {sample.sample_id for sample in dataset} == {
        "conv-26", "conv-30", "conv-41", "conv-42", "conv-43",
        "conv-44", "conv-47", "conv-48", "conv-49", "conv-50",
    }


def test_every_turn_has_consistent_dia_id(dataset):
    for sample in dataset:
        assert sample.speakers, f"{sample.sample_id} has no speakers"
        assert len(sample.dialogue_sessions()) >= 19
        for turn in sample.all_turns():
            assert turn.dia_id == turn.dia_id.strip()
            assert session_id_from_dia_id(turn.dia_id) == turn.session_id
            assert turn.speaker in sample.speakers


def test_session_dates_are_parsed(dataset):
    for sample in dataset:
        for session in sample.dialogue_sessions():
            assert session.date is not None, f"{sample.sample_id}/{session.session_id}"
            assert 2020 <= session.date.year <= 2026, session.date


def test_parse_session_date_formats():
    assert parse_session_date("1:56 pm on 8 May, 2023").isoformat() == "2023-05-08"
    assert parse_session_date("12:05 am on 21 December, 2022").isoformat() == "2022-12-21"
    assert parse_session_date("not a date") is None


def test_resolve_relative_dates():
    session_date = parse_session_date("1:00 pm on 25 May, 2023")
    assert resolve_effective_date("Melanie ran a charity race yesterday.", session_date).isoformat() == "2023-05-24"
    assert resolve_effective_date("She will go tomorrow.", session_date).isoformat() == "2023-05-26"
    assert resolve_effective_date("It happened on 2 July 2023.", session_date).isoformat() == "2023-07-02"
    assert resolve_effective_date("She moved a few years ago.", session_date) is None


def test_dia_sort_key_orders_numerically():
    ids = ["D10:2", "D2:10", "D2:9", "D1:1"]
    assert sorted(ids, key=dia_sort_key) == ["D1:1", "D2:9", "D2:10", "D10:2"]


# --------------------------------------------------------------------------- #
# 规则模式产出
# --------------------------------------------------------------------------- #
def test_rules_mode_produces_valid_document(dataset):
    sample = next(item for item in dataset if item.sample_id == "conv-30")
    document, report = extract_sample(
        sample, config=ExtractionConfig(provider="rules", cache_dir=None)
    )

    assert validate_document(document, sample) == []
    assert document["sample_id"] == "conv-30"
    assert len(document["memories"]) > 50
    assert report.memories == len(document["memories"])

    ids = [memory["memory_id"] for memory in document["memories"]]
    assert len(ids) == len(set(ids))
    assert all(memory_id.startswith("mem-conv30-") for memory_id in ids)

    for memory in document["memories"]:
        assert memory["subject"] in sample.speakers
        assert memory["evidence"], "every memory needs at least one evidence"
        for evidence in memory["evidence"]:
            turn = sample.turn(evidence["dia_id"])
            assert turn is not None
            assert evidence["session_id"] == turn.session_id
            if evidence["quote"] is not None:
                    assert _normalized(evidence["quote"]) in _normalized(turn.searchable_text)

def test_non_event_memories_have_attribute_and_value(dataset):
    sample = next(item for item in dataset if item.sample_id == "conv-26")
    document, _ = extract_sample(
        sample, config=ExtractionConfig(provider="rules", cache_dir=None)
    )
    for memory in document["memories"]:
        if memory["type"] != "event":
            assert memory["attribute"], memory
            assert memory["value"], memory


# --------------------------------------------------------------------------- #
# 不得使用 qa
# --------------------------------------------------------------------------- #
def test_extraction_prompts_never_contain_questions(dataset):
    sample = next(item for item in dataset if item.sample_id == "conv-30")
    client = RecordingClient()
    extract_sample(
        sample,
        client=client,
        config=ExtractionConfig(
            provider="deepseek",
            workers=1,
            cache_dir=None,
            gap_fill=True,
            max_gap_calls_per_sample=3,
        ),
    )
    assert client.prompts, "expected the flow to make at least one call"

    questions = [str(item.get("question", "")).strip() for item in sample.qa if item.get("question")]
    assert questions
    for _, user_prompt in client.prompts:
        for question in questions:
            assert question not in user_prompt, "QA question leaked into an extraction prompt"


def test_gap_fill_targets_are_not_qa_evidence(dataset):
    """补抽挑的是“没被引用的 turn”，不是 QA evidence。"""

    sample = next(item for item in dataset if item.sample_id == "conv-30")
    client = RecordingClient()
    extract_sample(
        sample,
        client=client,
        config=ExtractionConfig(
            provider="deepseek",
            workers=1,
            cache_dir=None,
            gap_fill=True,
            max_gap_calls_per_sample=1,
        ),
    )
    gap_prompts = [prompt for _, prompt in client.prompts if "TARGET TURNS" in prompt]
    assert gap_prompts, "gap-fill did not run"

    qa_turns = set(sample.qa_evidence_dia_ids())
    all_turns = {turn.dia_id for turn in sample.all_turns()}
    mentioned = set(re.findall(r"D\d+:\d+", gap_prompts[0]))
    # 目标里必须包含与 QA evidence 无关的 turn，说明补抽不是被 evidence 驱动的
    assert mentioned & all_turns
    assert mentioned - qa_turns, "gap-fill appears to be restricted to QA evidence turns"


# --------------------------------------------------------------------------- #
# 合并规则
# --------------------------------------------------------------------------- #
def _memory(session_id: str, dia_id: str, value: str, subject: str = "Jon", attribute: str = "studio") -> dict:
    return {
        "subject": subject,
        "type": "state",
        "attribute": attribute,
        "value": value,
        "content": f"Jon is {value.replace('_', ' ')}.",
        "time": {"session_id": session_id, "date_time": None, "effective_at": None},
        "evidence": [{"session_id": session_id, "dia_id": dia_id, "quote": None}],
        "confidence": 0.9,
    }


def test_state_cycle_is_not_merged():
    memories = [
        _memory("session_1", "D1:1", "planning"),
        _memory("session_2", "D2:1", "opening"),
        _memory("session_3", "D3:1", "planning"),
    ]
    merged = merge_same_state(memories, NormalizeStats())
    assert len(merged) == 3, "A -> B -> A must keep both A statements"


def test_repeated_state_is_merged():
    memories = [
        _memory("session_1", "D1:1", "owns_studio"),
        _memory("session_4", "D4:2", "owns_studio"),
    ]
    merged = merge_same_state(memories, NormalizeStats())
    assert len(merged) == 1
    assert len(merged[0]["evidence"]) == 2


def test_value_canonicalization_keeps_lifecycle_stages_apart():
    memories = [
        _memory("session_1", "D1:1", "owns_dance_studio"),
        _memory("session_2", "D2:1", "starting_a_dance_studio"),
        _memory("session_3", "D3:1", "own_dance_studio"),
    ]
    canonicalize_values(memories)
    values = {memory["value"] for memory in memories}
    assert "starting_a_dance_studio" in values, "a plan must not be folded into an owned business"
    assert len(values) == 2  # owns/own 被归一，starting_* 保持独立


# --------------------------------------------------------------------------- #
# 已落盘产物
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not OUTPUT_DIR.is_dir(), reason="outputs/memories not generated")
def test_generated_files_validate_against_schema(dataset):
    samples = {sample.sample_id: sample for sample in dataset}
    files = sorted(OUTPUT_DIR.glob("conv-*.json"))
    assert len(files) == 10

    for path in files:
        document = json.loads(path.read_text(encoding="utf-8"))
        sample = samples[document["sample_id"]]
        assert validate_document(document, sample) == [], path.name
        assert document["memories"]


@pytest.mark.skipif(not OUTPUT_DIR.is_dir(), reason="outputs/memories not generated")
def test_generated_quotes_are_verbatim(dataset):
    samples = {sample.sample_id: sample for sample in dataset}
    for path in sorted(OUTPUT_DIR.glob("conv-*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        sample = samples[document["sample_id"]]
        for memory in document["memories"]:
            for evidence in memory["evidence"]:
                if evidence["quote"] is None:
                    continue
                turn = sample.turn(evidence["dia_id"])
                assert turn is not None
                assert _normalized(evidence["quote"]) in _normalized(turn.searchable_text), (
                    f"{memory['memory_id']} quote is not verbatim"
                )
