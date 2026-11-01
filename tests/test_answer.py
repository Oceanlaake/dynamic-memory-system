"""Answer generation boundary and the unified QA comparison runner."""

from __future__ import annotations

import json

from backend.answer import build_answer_generator
from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.schemas import CandidateMemory, Memory, QueryResponse, RetrievalResult
from backend.store import MemoryStore
from evaluation.final.qa_compare import (
    build_full_text_context, labeled_memory_context, run_comparison,
)


def memory(memory_id, value="planned", *, subject="Jon", attribute="studio.status",
           session="session_1", date=None, content=None):
    return Memory.model_validate({
        "memory_id": memory_id, "subject": subject, "type": "state",
        "attribute": attribute, "value": value,
        "content": content or f"{subject}'s studio is {value}.",
        "time": {"session_id": session, "effective_at": date},
        "evidence": [{"session_id": session, "dia_id": f"{memory_id}:1"}],
    })


class FakeAnswerGenerator:
    def __init__(self, answers):
        self.answers = answers

    def answer(self, question, context):
        return self.answers.get(question)


class FakeRetriever:
    name = "hybrid"

    def __init__(self, memory_id):
        self.memory_id = memory_id

    def retrieve(self, question, memories, top_k, *, sample_id):
        chosen = [item for item in memories if item.memory_id == self.memory_id][:top_k]
        return RetrievalResult(
            sample_id=sample_id, question=question, top_k=top_k, strategy="hybrid",
            candidates=[CandidateMemory(memory=item, score=1.0, rank=index)
                        for index, item in enumerate(chosen, start=1)],
            degraded=not chosen,
        )


def test_build_full_text_context_orders_sessions_and_includes_turns():
    sample = {
        "sample_id": "s1",
        "conversation": {
            "speaker_a": "A", "speaker_b": "B",
            "session_2_date_time": "later", "session_2": [{"speaker": "A", "dia_id": "D2:1", "text": "hello again"}],
            "session_1_date_time": "earlier", "session_1": [{"speaker": "B", "dia_id": "D1:1", "text": "hi"}],
        },
    }
    text, turns, truncated = build_full_text_context(sample)
    assert turns == 2
    assert text.index("earlier") < text.index("later")
    assert "B: hi" in text and "A: hello again" in text
    assert truncated is False


def test_build_full_text_context_can_truncate():
    sample = {
        "sample_id": "s1",
        "conversation": {
            "session_1": [{"speaker": "A", "dia_id": "D1:1", "text": "a long answer"}],
        },
    }
    text, _, truncated = build_full_text_context(sample, max_chars=4)
    assert text == "A: a"
    assert truncated is True


def test_build_answer_generator_returns_injected_generator():
    fake = FakeAnswerGenerator({})
    assert build_answer_generator(generator=fake) is fake


def test_labeled_memory_context_marks_current_historical_and_conflicting():
    old = memory("m1", date="2023-01-01")
    current = memory("m2", "open", session="session_2", date="2023-02-01")
    conflicting = memory("m3", "closed", session="unknown", content="Jon's studio is closed.")
    response = QueryResponse.model_validate({
        "sample_id": "sample", "question": "What is Jon's studio status?",
        "candidate_memories": [
            {"memory": old.model_dump(), "score": 1.0, "rank": 1},
            {"memory": current.model_dump(), "score": 0.9, "rank": 2},
            {"memory": conflicting.model_dump(), "score": 0.8, "rank": 3},
        ],
        "relations": [
            {"from": "m1", "to": "m2", "relation": "SUPERSEDE", "reason": "later value"},
            {"from": "m2", "to": "m3", "relation": "CONFLICT", "reason": "incompatible"},
        ],
        "effective_memories": [{"memory_id": "m2", "role": "current_state"}],
    })
    text = labeled_memory_context(response)
    assert "[historical]" in text
    assert "current" in text and "conflicting" in text
    assert "effective 2023-01-01" in text and "effective 2023-02-01" in text


def test_run_comparison_scores_all_methods_without_network(tmp_path):
    old = memory("m1", date="2023-01-01")
    new = memory("m2", "open", session="session_2", date="2023-02-01")
    (tmp_path / "sample.json").write_text(json.dumps({
        "sample_id": "sample", "memories": [old.model_dump(), new.model_dump()],
    }))
    raw = {
        "sample_id": "sample",
        "conversation": {
            "session_1": [{"speaker": "Jon", "dia_id": "D1:1", "text": "The studio is open."}],
        },
    }
    case = {
        "sample_id": "sample", "question": "Is the studio open?",
        "required_memory_ids": ["m2"], "expected_answer": "open",
    }
    generator = FakeAnswerGenerator({"Is the studio open?": "open"})
    report = run_comparison(
        [case], MemoryStore(tmp_path), {"sample": raw}, generator,
        FakeRetriever("m1"), FakeRetriever("m2"), RuleBasedDynamicStateResolver(),
    )
    summary = report["summary"]
    assert set(summary) == {"full_text", "vector_rag", "state_topk", "state_bonus"}
    for name in summary:
        assert summary[name]["mean_answer_f1"] == 1.0
        assert summary[name]["refusals"] == 0
    assert report["cases"][0]["vector_rag"]["candidate_memory_ids"] == ["m1"]
    assert report["cases"][0]["state_bonus"]["effective_memory_ids"] == ["m2"]
