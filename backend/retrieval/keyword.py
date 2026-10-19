"""BM25 检索基线：零第三方依赖，作为离线/demo 的兜底策略。

score 采用“相对本次最高分”的归一化：最高分记为 1.0，其余按比例缩放，便于前端展示。
它表达的是同一问题内的相对相关性，不能跨问题比较。

性能：索引按 Memory 集合缓存，同一批记忆上的多次查询不再重复分词。
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Sequence

from backend.retrieval.text import build_index_text, tokenize
from backend.schemas import CandidateMemory, Memory, RetrievalResult, Strategy


class _BM25Index:
    __slots__ = ("term_freqs", "lengths", "doc_freq", "avg_len", "total")

    def __init__(self, docs: Sequence[Sequence[str]]) -> None:
        self.total = len(docs)
        self.term_freqs = [Counter(doc) for doc in docs]
        self.lengths = [len(doc) for doc in docs]
        self.avg_len = (sum(self.lengths) / self.total) if self.total else 1.0
        self.doc_freq: Counter[str] = Counter()
        for doc in docs:
            self.doc_freq.update(set(doc))


class BM25Retriever:
    name: Strategy = "bm25"

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._indexes: dict[tuple[str, ...], _BM25Index] = {}

    def _index(self, memories: Sequence[Memory]) -> _BM25Index:
        key = tuple(memory.memory_id for memory in memories)
        cached = self._indexes.get(key)
        if cached is not None:
            return cached
        index = _BM25Index([tokenize(build_index_text(memory)) for memory in memories])
        self._indexes[key] = index
        return index

    def rank_all(self, question: str, memories: Sequence[Memory]) -> list[tuple[float, Memory]]:
        """返回全部有命中的 (归一化分数, memory)，按分数降序。"""
        if not memories:
            return []
        query_tokens = tokenize(question)
        if not query_tokens:
            return []

        index = self._index(memories)
        scored: list[tuple[float, Memory]] = []
        for term_freq, length, memory in zip(index.term_freqs, index.lengths, memories):
            score = self._score_doc(query_tokens, term_freq, length, index)
            if score > 0:
                scored.append((score, memory))
        if not scored:
            return []

        scored.sort(key=lambda pair: (-pair[0], pair[1].memory_id))
        best = scored[0][0]
        return [(min(1.0, score / best), memory) for score, memory in scored]

    def retrieve(
        self,
        question: str,
        memories: Sequence[Memory],
        top_k: int,
        *,
        sample_id: str = "",
    ) -> RetrievalResult:
        ranked = self.rank_all(question, memories)[:top_k]
        if not ranked:
            return RetrievalResult(
                sample_id=sample_id,
                question=question,
                top_k=top_k,
                strategy=self.name,
                candidates=[],
                degraded=True,
            )

        candidates = [
            CandidateMemory(
                memory=memory,
                score=round(score, 4),
                rank=index,
                matched_by=["keyword"],
            )
            for index, (score, memory) in enumerate(ranked, start=1)
        ]
        return RetrievalResult(
            sample_id=sample_id,
            question=question,
            top_k=top_k,
            strategy=self.name,
            candidates=candidates,
            degraded=False,
        )

    def _score_doc(
        self,
        query_tokens: Sequence[str],
        term_freq: Counter[str],
        length: int,
        index: _BM25Index,
    ) -> float:
        score = 0.0
        for token in query_tokens:
            freq = term_freq.get(token, 0)
            if freq == 0:
                continue
            idf = math.log(
                1 + (index.total - index.doc_freq[token] + 0.5) / (index.doc_freq[token] + 0.5)
            )
            denominator = freq + self.k1 * (1 - self.b + self.b * length / index.avg_len)
            score += idf * freq * (self.k1 + 1) / denominator
        return score
