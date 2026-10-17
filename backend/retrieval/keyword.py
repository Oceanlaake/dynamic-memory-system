"""BM25 检索基线：零第三方依赖，作为离线/demo 的兜底策略。

score 采用“相对本次最高分”的归一化：最高分记为 1.0，其余按比例缩放，便于前端展示。
它表达的是同一问题内的相对相关性，不能跨问题比较。
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Sequence

from backend.retrieval.text import build_index_text, tokenize
from backend.schemas import CandidateMemory, Memory, RetrievalResult, Strategy


class BM25Retriever:
    name: Strategy = "bm25"

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

    def retrieve(
        self,
        question: str,
        memories: Sequence[Memory],
        top_k: int,
        *,
        sample_id: str = "",
    ) -> RetrievalResult:
        query_tokens = tokenize(question)
        docs = [tokenize(build_index_text(memory)) for memory in memories]
        scores = self._score(query_tokens, docs)

        ranked = sorted(
            ((score, memory) for score, memory in zip(scores, memories) if score > 0),
            key=lambda pair: (-pair[0], pair[1].memory_id),
        )[:top_k]

        if not ranked:
            return RetrievalResult(
                sample_id=sample_id,
                question=question,
                top_k=top_k,
                strategy=self.name,
                candidates=[],
                degraded=True,
            )

        best = ranked[0][0]
        candidates = [
            CandidateMemory(
                memory=memory,
                score=round(min(1.0, score / best), 4),
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

    def _score(self, query_tokens: Sequence[str], docs: Sequence[Sequence[str]]) -> list[float]:
        if not docs:
            return []
        if not query_tokens:
            return [0.0] * len(docs)

        total = len(docs)
        avg_len = sum(len(doc) for doc in docs) / total or 1.0
        doc_freq: Counter[str] = Counter()
        for doc in docs:
            doc_freq.update(set(doc))

        scores: list[float] = []
        for doc in docs:
            term_freq = Counter(doc)
            length = len(doc)
            score = 0.0
            for token in query_tokens:
                freq = term_freq.get(token, 0)
                if freq == 0:
                    continue
                idf = math.log(1 + (total - doc_freq[token] + 0.5) / (doc_freq[token] + 0.5))
                denominator = freq + self.k1 * (1 - self.b + self.b * length / avg_len)
                score += idf * freq * (self.k1 + 1) / denominator
            scores.append(score)
        return scores
