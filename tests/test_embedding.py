"""语义检索与混合检索测试。

用可注入的 FakeEncoder，测试不依赖模型下载与网络。
"""

from __future__ import annotations

import zlib

import numpy as np
import pytest

from backend.retrieval.embedding import SentenceTransformerRetriever
from backend.retrieval.factory import build_retriever
from backend.retrieval.hybrid import HybridRetriever
from backend.retrieval.keyword import BM25Retriever
from backend.retrieval.text import tokenize
from backend.schemas import CandidateMemory, Memory, RetrievalResult
from backend.store import MemoryStore

QUESTION = "How long did it take for Jon to open his studio?"


class FakeEncoder:
    """把 token 哈希到固定维度，确定性且不需要模型。"""

    def __init__(self, dim: int = 128) -> None:
        self.dim = dim
        self.encode_calls = 0

    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        self.encode_calls += 1
        vectors = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in tokenize(text):
                vectors[row, zlib.crc32(token.encode("utf-8")) % self.dim] += 1.0
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms


class StubRetriever:
    def __init__(self, name, scores: dict[str, float]) -> None:
        self.name = name
        self.scores = scores

    def retrieve(self, question, memories, top_k, *, sample_id=""):
        candidates = [
            CandidateMemory(memory=memory, score=score, rank=index, matched_by=["embedding"])
            for index, memory in enumerate(
                [m for m in memories if m.memory_id in self.scores][:top_k], start=1
            )
            for score in [self.scores[memory.memory_id]]
        ]
        candidates.sort(key=lambda c: (-c.score, c.memory.memory_id))
        for index, candidate in enumerate(candidates, start=1):
            candidate.rank = index
        return RetrievalResult(
            sample_id=sample_id,
            question=question,
            top_k=top_k,
            strategy=self.name,
            candidates=candidates,
        )


@pytest.fixture(scope="module")
def memories():
    loaded = MemoryStore().memories("conv-30")
    assert loaded
    return loaded


@pytest.fixture
def retriever(tmp_path):
    return SentenceTransformerRetriever(cache_dir=tmp_path, encoder=FakeEncoder(), min_score=0.0)


def test_returns_ranked_candidates(retriever, memories):
    result = retriever.retrieve(QUESTION, memories, 3, sample_id="conv-30")
    assert result.strategy == "embedding"
    assert result.degraded is False
    assert len(result.candidates) == 3
    assert [c.rank for c in result.candidates] == [1, 2, 3]
    scores = [c.score for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= score <= 1.0 for score in scores)
    assert all(c.matched_by == ["embedding"] for c in result.candidates)


def test_min_score_drops_weak_matches(tmp_path, memories):
    retriever = SentenceTransformerRetriever(
        cache_dir=tmp_path, encoder=FakeEncoder(), min_score=0.99
    )
    result = retriever.retrieve("completely unrelated zebra quantum", memories, 5)
    assert result.candidates == []
    assert result.degraded is True


def test_empty_store_is_degraded(retriever):
    result = retriever.retrieve(QUESTION, [], 5, sample_id="conv-30")
    assert result.candidates == []
    assert result.degraded is True


def test_document_vectors_are_cached(tmp_path, memories):
    encoder = FakeEncoder()
    first = SentenceTransformerRetriever(cache_dir=tmp_path, encoder=encoder, min_score=0.0)
    first.retrieve(QUESTION, memories, 3)
    assert encoder.encode_calls == 2  # 文档 + query

    cached_files = list(tmp_path.glob("*.npz"))
    assert len(cached_files) == 1

    second = SentenceTransformerRetriever(cache_dir=tmp_path, encoder=encoder, min_score=0.0)
    second.retrieve(QUESTION, memories, 3)
    assert encoder.encode_calls == 3  # 只重算了 query


def test_hybrid_merges_both_signals(memories):
    semantic_scores = {"mem-conv30-002": 0.8, "mem-conv30-004": 0.6, "mem-conv30-001": 0.7}
    hybrid = HybridRetriever(
        lexical=BM25Retriever(),
        semantic=StubRetriever("embedding", semantic_scores),
        lexical_weight=0.5,
        min_score=0.0,
    )
    result = hybrid.retrieve(QUESTION, memories, 5, sample_id="conv-30")
    assert result.strategy == "hybrid"
    assert result.degraded is False

    lexical = BM25Retriever().retrieve(QUESTION, memories, len(memories))
    lexical_scores = {c.memory.memory_id: c.score for c in lexical.candidates}

    top = result.candidates[0]
    expected = 0.5 * lexical_scores[top.memory.memory_id] + 0.5 * semantic_scores[top.memory.memory_id]
    assert top.score == pytest.approx(round(expected, 4), abs=1e-4)
    assert top.matched_by == ["embedding", "keyword"]


def test_hybrid_keeps_lexical_only_hits(memories):
    hybrid = HybridRetriever(
        lexical=BM25Retriever(),
        semantic=StubRetriever("embedding", {"mem-conv30-002": 0.9}),
        lexical_weight=0.5,
        min_score=0.0,
    )
    ids = [c.memory.memory_id for c in hybrid.retrieve(QUESTION, memories, 5).candidates]
    assert "mem-conv30-004" in ids
    assert "mem-conv30-005" in ids


def test_hybrid_rejects_invalid_weight():
    with pytest.raises(ValueError):
        HybridRetriever(lexical_weight=1.5)


def test_factory_honours_env(monkeypatch):
    monkeypatch.setenv("DMS_RETRIEVER", "bm25")
    assert isinstance(build_retriever(), BM25Retriever)


def test_factory_rejects_unknown_choice(monkeypatch):
    monkeypatch.setenv("DMS_RETRIEVER", "gpt")
    with pytest.raises(ValueError):
        build_retriever()


def test_factory_auto_falls_back_when_library_missing(monkeypatch):
    import backend.retrieval.factory as factory

    monkeypatch.setattr(factory, "_has_sentence_transformers", lambda: False)
    monkeypatch.setenv("DMS_RETRIEVER", "auto")
    assert isinstance(build_retriever(), BM25Retriever)


def test_factory_auto_falls_back_when_model_unavailable(monkeypatch):
    import backend.retrieval.factory as factory

    def boom(force_load=False):
        raise RuntimeError("model offline")

    monkeypatch.setattr(factory, "_has_sentence_transformers", lambda: True)
    monkeypatch.setattr(factory, "_hybrid", boom)
    monkeypatch.setenv("DMS_RETRIEVER", "auto")
    assert isinstance(build_retriever(), BM25Retriever)
