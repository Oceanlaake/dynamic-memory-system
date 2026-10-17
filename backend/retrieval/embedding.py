"""基于 sentence-transformers 的语义检索。

设计要点：
- 模型懒加载：只有真正发生检索时才加载，避免 BM25 模式下被拖慢。
- 文档向量落盘缓存：同一批 Memory 第二次检索不再重算。
- encoder 可注入：测试用假 encoder 即可覆盖排序/缓存/退化逻辑，不需要下载模型。
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Sequence

from backend.retrieval.text import build_index_text
from backend.schemas import CandidateMemory, Memory, RetrievalResult, Strategy

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_CACHE_DIR = Path("data/cache/embeddings")
DEFAULT_MIN_SCORE = 0.2


def _slug(model_name: str) -> str:
    return model_name.replace("/", "__").replace(":", "_")


class SentenceTransformerRetriever:
    name: Strategy = "embedding"

    def __init__(
        self,
        model_name: str | None = None,
        cache_dir: Path | str | None = None,
        encoder: Any | None = None,
        min_score: float = DEFAULT_MIN_SCORE,
    ) -> None:
        self.model_name = model_name or os.environ.get("DMS_EMBEDDING_MODEL") or DEFAULT_MODEL
        self.cache_dir = Path(
            cache_dir or os.environ.get("DMS_EMBEDDING_CACHE") or DEFAULT_CACHE_DIR
        )
        self.min_score = min_score
        self._encoder = encoder

    @property
    def encoder(self) -> Any:
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(self.model_name)
        return self._encoder

    def embed(self, texts: Sequence[str]) -> Any:
        return self.encoder.encode(
            list(texts), normalize_embeddings=True, show_progress_bar=False
        )

    def retrieve(
        self,
        question: str,
        memories: Sequence[Memory],
        top_k: int,
        *,
        sample_id: str = "",
    ) -> RetrievalResult:
        if not memories:
            return self._degraded(question, top_k, sample_id)

        texts = [build_index_text(memory) for memory in memories]
        document_vectors = self._document_vectors(texts)
        query_vector = self.embed([question])[0]

        sims = document_vectors @ query_vector
        ranked = sorted(
            zip(sims, memories),
            key=lambda pair: (-float(pair[0]), pair[1].memory_id),
        )
        kept = [(float(score), memory) for score, memory in ranked if float(score) >= self.min_score]
        if not kept:
            return self._degraded(question, top_k, sample_id)

        candidates = [
            CandidateMemory(
                memory=memory,
                score=round(min(1.0, max(0.0, score)), 4),
                rank=index,
                matched_by=["embedding"],
            )
            for index, (score, memory) in enumerate(kept[:top_k], start=1)
        ]
        return RetrievalResult(
            sample_id=sample_id,
            question=question,
            top_k=top_k,
            strategy=self.name,
            candidates=candidates,
            degraded=False,
        )

    def _document_vectors(self, texts: Sequence[str]) -> Any:
        import numpy as np

        digest = hashlib.sha256(
            ("\x00".join([self.model_name, *texts])).encode("utf-8")
        ).hexdigest()[:16]
        path = self.cache_dir / f"{_slug(self.model_name)}-{digest}.npz"
        if path.exists():
            with np.load(path) as cached:
                return cached["vectors"]

        vectors = self.embed(texts)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        np.savez(path, vectors=vectors)
        return vectors

    def _degraded(self, question: str, top_k: int, sample_id: str) -> RetrievalResult:
        return RetrievalResult(
            sample_id=sample_id,
            question=question,
            top_k=top_k,
            strategy=self.name,
            candidates=[],
            degraded=True,
        )
