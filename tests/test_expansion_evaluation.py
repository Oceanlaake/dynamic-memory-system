"""Check scoring, fair resolver use, and rejection of mismatched gold data."""

import json

import pytest

from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.schemas import CandidateMemory, RetrievalResult
from backend.store import MemoryStore
from evaluation.slot_expansion import answer_f1, run
from tests.test_expansion import memory
from tests.fakes import FixtureAnswerGenerator


class FixedRetriever:
    def retrieve(self, question, memories, top_k, *, sample_id):
        return RetrievalResult(sample_id=sample_id, question=question, top_k=top_k,
                               strategy="bm25", candidates=[
            CandidateMemory(memory=m, score=1/(i+1), rank=i+1)
            for i, m in enumerate(memories[:top_k])
        ])


def test_comparison_recovers_evidence_and_does_not_invent_missing_metrics(tmp_path):
    old = memory("m1", date="2023-01-01")
    new = memory("m2", "open", date="2023-02-01", session="session_2")
    (tmp_path / "sample.json").write_text(json.dumps({
        "sample_id": "sample", "memories": [old.model_dump(), new.model_dump()],
    }))
    case = {"sample_id": "sample", "question": "What is Jon's studio status now?",
            "required_memory_ids": ["m2"], "expected_effective_memory_ids": ["m2"],
            "expected_answer": new.content,
            "expected_relations": [{"from": "m1", "to": "m2", "relation": "SUPERSEDE"}]}
    report = run([case], MemoryStore(tmp_path), FixedRetriever(), RuleBasedDynamicStateResolver(),
                 top_k=1, larger_k=2, generator=FixtureAnswerGenerator())
    summary = report["summary"]
    assert summary["fixed_k"]["mean_evidence_set_recall"] == 0
    assert summary["slot_expansion"]["mean_evidence_set_recall"] == 1
    assert summary["slot_expansion"]["mean_effective_exact_match"] == 1
    assert summary["slot_expansion"]["mean_answer_f1"] == 1
    assert summary["slot_expansion"]["relation_accuracy"] == 1
    assert summary["fixed_k"]["relation_accuracy"] == 0
    assert all(s["resolver_calls"] == 1 for s in summary.values())
    minimal = {key: case[key] for key in ("sample_id", "question", "required_memory_ids")}
    missing = run([minimal], MemoryStore(tmp_path), FixedRetriever(), RuleBasedDynamicStateResolver(),
                  top_k=1, larger_k=2, generator=FixtureAnswerGenerator())["summary"]["slot_expansion"]
    assert missing["mean_answer_f1"] is None
    assert missing["mean_effective_exact_match"] is None
    assert missing["relation_accuracy"] is None
    assert missing["answer_f1_annotated_cases"] == 0
    with pytest.raises(ValueError, match="gold evidence"):
        run([{**case, "required_memory_ids": ["not-in-store"]}], MemoryStore(tmp_path),
            FixedRetriever(), RuleBasedDynamicStateResolver(), top_k=1, larger_k=2)


def test_english_token_f1_counts_duplicates_and_handles_refusals():
    assert answer_f1("The studio opened", "studio opened") == 1
    assert answer_f1(None, "studio opened") == 0
    assert answer_f1("dance dance", "dance") == pytest.approx(2/3)
