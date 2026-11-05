"""评估管道测试：指标计算与 qa.evidence -> memory_id 的自动映射。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.schemas import Memory
from evaluation.build_cases import build_cases, index_memories, parse_evidence
from evaluation.metrics import macro_average, rank_metrics
from evaluation.state_accuracy import build_report, load_cases

SAMPLE = {
    "sample_id": "conv-99",
    "qa": [
        {
            "question": "When did Jon open the studio?",
            "answer": "June 2023",
            "evidence": ["D1:2", "D2:5"],
            "category": 2,
        },
        {
            "question": "What does Jon like?",
            "answer": "dance",
            "evidence": ["D9:9"],
            "category": 4,
        },
        {
            "question": "What is Jon's dog called?",
            "answer": "Not mentioned",
            "evidence": [],
            "category": 5,
        },
    ],
}


def make_memory(memory_id: str, dia_ids: list[str]) -> Memory:
    return Memory.model_validate(
        {
            "memory_id": memory_id,
            "subject": "Jon",
            "type": "event",
            "content": "filler",
            "time": {"session_id": "session_1"},
            "evidence": [{"session_id": "session_1", "dia_id": dia_id} for dia_id in dia_ids],
        }
    )


def test_parse_evidence_handles_list_and_packed_strings():
    assert parse_evidence(["D1:2", "D2:5"]) == ["D1:2", "D2:5"]
    assert parse_evidence("D8:6; D9:17") == ["D8:6", "D9:17"]
    assert parse_evidence(None) == []


def test_index_memories_maps_every_cited_turn():
    memories = [make_memory("m1", ["D1:2", "D1:3"]), make_memory("m2", ["D1:2"])]
    assert index_memories(memories) == {"D1:2": ["m1", "m2"], "D1:3": ["m1"]}


def test_build_cases_maps_evidence_to_memories():
    memories = {
        "conv-99": [make_memory("m1", ["D1:2"]), make_memory("m2", ["D2:5"]), make_memory("m3", ["D1:9"])]
    }
    cases, stats = build_cases([SAMPLE], memories, include_categories={1, 2, 3, 4})

    assert len(cases) == 1
    case = cases[0]
    assert case["required_memory_ids"] == ["m1", "m2"]
    assert case["question"] == "When did Jon open the studio?"
    assert stats["qa_total"] == 3
    assert stats["skipped_category"] == 1
    assert stats["skipped_no_memory"] == 1
    assert stats["skipped_examples"][0]["question"] == "What does Jon like?"


def test_build_cases_skips_samples_without_memories():
    cases, stats = build_cases([SAMPLE], {}, include_categories=None)
    assert cases == []
    assert stats["samples"] == 0


def test_build_cases_can_include_adversarial_category():
    memories = {"conv-99": [make_memory("m1", ["D1:2"])]}
    cases, stats = build_cases([SAMPLE], memories, include_categories=None)
    assert stats["skipped_category"] == 0
    assert len(cases) == 1


def test_rank_metrics_perfect_and_partial():
    perfect = rank_metrics(["a", "b", "c"], ["a", "b"], [1, 2])
    assert perfect["recall"] == {1: 0.5, 2: 1.0}
    assert perfect["mrr"] == 1.0

    partial = rank_metrics(["x", "b", "y"], ["a", "b"], [1, 3])
    assert partial["recall"] == {1: 0.0, 3: 0.5}
    assert partial["mrr"] == 0.5


def test_rank_metrics_without_hit():
    metrics = rank_metrics(["x", "y"], ["a"], [1, 5])
    assert metrics["recall"] == {1: 0.0, 5: 0.0}
    assert metrics["mrr"] == 0.0


def test_rank_metrics_rejects_empty_required():
    with pytest.raises(ValueError):
        rank_metrics(["a"], [], [1])


def test_macro_average():
    rows = [
        {"recall": {1: 1.0, 3: 1.0}, "mrr": 1.0},
        {"recall": {1: 0.0, 3: 0.5}, "mrr": 0.5},
    ]
    aggregate = macro_average(rows, [1, 3])
    assert aggregate["recall"] == {1: 0.5, 3: 0.75}
    assert aggregate["mrr"] == 0.75


def test_b2_relation_evaluation_set_records_rules_baseline():
    cases = load_cases(
        [
            Path("evaluation/cases/b2_relations.json"),
            Path("evaluation/cases/b2_relations_challenge.json"),
        ]
    )
    report = build_report(cases, RuleBasedDynamicStateResolver())

    assert report["summary"]["total"] == 16
    assert report["summary"]["correct"] == 9
    # The factual residence-history case has no deterministic temporal edge;
    # the rules now leave it unclassified instead of inventing SUPERSEDE.
    assert report["summary"]["no_prediction"] == 1
