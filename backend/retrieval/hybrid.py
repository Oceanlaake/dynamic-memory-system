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

    def rank_all(self, question: str, memories: Sequence[Memory]) -> list[tuple[float, Memory]]:
        """融合两路得分，返回 score >= min_score 的 (分数, memory)，按分数降序。"""
        return [(score, memory) for score, memory, _ in self._fuse(question, memories)]

    def _fuse(
        self, question: str, memories: Sequence[Memory]
    ) -> list[tuple[float, Memory, set[MatchSource]]]:
        if not memories:
            return []

        by_id = {memory.memory_id: memory for memory in memories}
        scores: dict[str, float] = {}
        matched: dict[str, set[MatchSource]] = {}

        for weight, retriever, source in (
            (self.lexical_weight, self.lexical, "keyword"),
            (1 - self.lexical_weight, self.semantic, "embedding"),
        ):
            for score, memory in self._rank(retriever, question, memories):
                memory_id = memory.memory_id
                scores[memory_id] = scores.get(memory_id, 0.0) + weight * score
                matched.setdefault(memory_id, set()).add(source)

        ranked = sorted(
            (
                (score, by_id[memory_id], matched[memory_id])
                for memory_id, score in scores.items()
                if score > 0 and score >= self.min_score
            ),
            key=lambda triple: (-triple[0], triple[1].memory_id),
        )
        return [(min(1.0, score), memory, sources) for score, memory, sources in ranked]

    @staticmethod
    def _rank(
        retriever: Retriever, question: str, memories: Sequence[Memory]
    ) -> list[tuple[float, Memory]]:
        rank_all = getattr(retriever, "rank_all", None)
        if rank_all is not None:
            return rank_all(question, memories)
        result = retriever.retrieve(question, memories, len(memories))
        return [(candidate.score, candidate.memory) for candidate in result.candidates]

    def retrieve(
        self,
        question: str,
        memories: Sequence[Memory],
        top_k: int,
        *,
        sample_id: str = "",
    ) -> RetrievalResult:
        ranked = self._fuse(question, memories)[:top_k]
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
                matched_by=sorted(sources),
            )
            for index, (score, memory, sources) in enumerate(ranked, start=1)
        ]
        return RetrievalResult(
            sample_id=sample_id,
            question=question,
            top_k=top_k,
            strategy=self.name,
            candidates=candidates,
            degraded=False,
        )
