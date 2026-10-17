"""B1 检索行为测试：只验证检索该负责的事（召回、排序、K、退化）。"""

from __future__ import annotations

import pytest

from backend.retrieval.keyword import BM25Retriever
from backend.retrieval.text import build_index_text, tokenize
from backend.store import MemoryStore

QUESTION = "How long did it take for Jon to open his studio?"


@pytest.fixture(scope="module")
def memories():
    store = MemoryStore()
    loaded = store.memories("conv-30")
    assert loaded, "data/memories/conv-30.json missing"
    return loaded


@pytest.fixture(scope="module")
def retriever():
    return BM25Retriever()


def test_index_text_includes_semantic_fields(memories):
    text = build_index_text(memories[1])
    assert "Jon" in text
    assert "goal" in text
    assert "planned" in text
    assert "dance studio" in text.lower()
    assert "I'm starting a dance studio" not in text


def test_stopwords_are_removed():
    assert tokenize("How long did it take for Jon") == ["long", "take", "jon"]


def test_top_k_is_respected(retriever, memories):
    result = retriever.retrieve(QUESTION, memories, 2, sample_id="conv-30")
    assert len(result.candidates) == 2
    assert [c.rank for c in result.candidates] == [1, 2]


def test_ranks_and_scores_are_ordered(retriever, memories):
    result = retriever.retrieve(QUESTION, memories, 5)
    scores = [c.score for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= score <= 1.0 for score in scores)
    assert result.candidates[0].score == pytest.approx(1.0)


def test_relevant_memories_outrank_the_preference(retriever, memories):
    result = retriever.retrieve(QUESTION, memories, 5)
    ranked_ids = [c.memory.memory_id for c in result.candidates]
    assert {"mem-conv30-004", "mem-conv30-002"} <= set(ranked_ids[:2])
    assert ranked_ids.index("mem-conv30-004") < ranked_ids.index("mem-conv30-003")


def test_unrelated_question_degrades_instead_of_hallucinating(retriever, memories):
    result = retriever.retrieve("What is the capital of France?", memories, 5)
    assert result.candidates == []
    assert result.degraded is True


def test_all_stopword_question_is_degraded(retriever, memories):
    result = retriever.retrieve("how did it", memories, 5)
    assert result.candidates == []
    assert result.degraded is True


def test_top_k_larger_than_store_is_safe(retriever, memories):
    result = retriever.retrieve(QUESTION, memories, 50)
    assert len(result.candidates) <= len(memories)
    assert result.degraded is False


def test_retrieval_is_deterministic(retriever, memories):
    first = retriever.retrieve(QUESTION, memories, 5)
    second = retriever.retrieve(QUESTION, memories, 5)
    assert first.model_dump() == second.model_dump()


def test_empty_store_is_degraded(retriever):
    result = retriever.retrieve(QUESTION, [], 5, sample_id="conv-30")
    assert result.candidates == []
    assert result.degraded is True
