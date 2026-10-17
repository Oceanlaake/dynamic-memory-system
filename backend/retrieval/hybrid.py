"""混合检索：词法(BM25)与语义(embedding)加权融合。

词法保证专有名词、日期等精确匹配不被稀释；语义保证“失业”与“开业耗时”这类
没有字面重叠但语义相关的关系能被召回。
"""

from __future__ import annotations

from typing import Sequence

from backend.retrieval.base import Retriever
from backend.retrieval.keyword import BM25Retriever
from backend.schemas import CandidateMemory, MatchSource, Memory, RetrievalResult, Strategy


class HybridRetriever:
    name: Strategy = "hybrid"

    def __init__(
        self,
        lexical: Retriever | None = None,
        semantic: Retriever | None = None,
        lexical_weight: float = 0.4,
        min_score: float = 0.15,
    ) -> None:
        if not 0.0 <= lexical_weight <= 1.0:
            raise ValueError("lexical_weight must be within [0, 1]")
        self.lexical = lexical or BM25Retriever()
        self.semantic = semantic or self._default_semantic()
        self.lexical_weight = lexical_weight
        self.min_score = min_score

    @staticmethod
    def _default_semantic() -> Retriever:
        from backend.retrieval.embedding import SentenceTransformerRetriever

        return SentenceTransformerRetriever()

    def retrieve(
        self,
        question: str,
        memories: Sequence[Memory],
        top_k: int,
        *,
        sample_id: str = "",
    ) -> RetrievalResult:
        if not memories:
            return RetrievalResult(
                sample_id=sample_id,
                question=question,
                top_k=top_k,
                strategy=self.name,
                candidates=[],
                degraded=True,
            )

        size = len(memories)
        lexical_result = self.lexical.retrieve(question, memories, size, sample_id=sample_id)
        semantic_result = self.semantic.retrieve(question, memories, size, sample_id=sample_id)

        scores: dict[str, float] = {}
        matched: dict[str, set[MatchSource]] = {}
        by_id = {memory.memory_id: memory for memory in memories}

        for weight, result, source in (
            (self.lexical_weight, lexical_result, "keyword"),
            (1 - self.lexical_weight, semantic_result, "embedding"),
        ):
            for candidate in result.candidates:
                memory_id = candidate.memory.memory_id
                scores[memory_id] = scores.get(memory_id, 0.0) + weight * candidate.score
                matched.setdefault(memory_id, set()).add(source)

        ranked = sorted(
            (
                (score, by_id[memory_id])
                for memory_id, score in scores.items()
                if score > 0 and score >= self.min_score
            ),
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

        candidates = [
            CandidateMemory(
                memory=memory,
                score=round(min(1.0, score), 4),
                rank=index,
                matched_by=sorted(matched[memory.memory_id]),
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
