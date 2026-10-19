"""基于 sentence-transformers 的语义检索。

设计要点：
- 模型懒加载：只有真正发生检索时才加载，避免 BM25 模式下被拖慢。
- 文档向量两级缓存：进程内按 Memory 集合缓存，磁盘按文本指纹缓存。
- encoder 可注入：测试用假 encoder 即可覆盖排序/缓存/退化逻辑，不需要下载模型。
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, NamedTuple, Sequence

from backend.retrieval.text import build_index_text
from backend.schemas import CandidateMemory, Memory, RetrievalResult, Strategy

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_CACHE_DIR = Path("data/cache/embeddings")
DEFAULT_MIN_SCORE = 0.2


def _slug(model_name: str) -> str:
    return model_name.replace("/", "__").replace(":", "_")


class _DocumentVectors(NamedTuple):
    vectors: Any
    memories: Sequence[Memory]


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
        self._document_cache: dict[tuple[str, ...], _DocumentVectors] = {}
        self._query_cache: dict[str, Any] = {}

    @property
    def encoder(self) -> Any:
        if self._encoder is None:
            self._encoder = self._load_encoder()
        return self._encoder

    def _load_encoder(self) -> Any:
        """优先使用本地缓存，避免联网校验带来的长时间超时。

        模型已缓存时完全离线加载；未缓存时才允许下载。设 HF_HUB_OFFLINE=1 可强制离线。
        """
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

        from sentence_transformers import SentenceTransformer

        if os.environ.get("HF_HUB_OFFLINE") in {"1", "true", "True"}:
            return SentenceTransformer(self.model_name, local_files_only=True)
        try:
            return SentenceTransformer(self.model_name, local_files_only=True)
        except Exception:
            logger.info("model %s not in local cache; downloading", self.model_name)
            return SentenceTransformer(self.model_name)

    def embed(self, texts: Sequence[str]) -> Any:
        return self.encoder.encode(
            list(texts), normalize_embeddings=True, show_progress_bar=False
        )

    def _query_vector(self, question: str) -> Any:
        """同一问题在 embedding 与 hybrid 两路里会重复出现，缓存避免重复编码。"""
        cached = self._query_cache.get(question)
        if cached is None:
            cached = self.embed([question])[0]
            if len(self._query_cache) >= 4096:
                self._query_cache.clear()
            self._query_cache[question] = cached
        return cached

    def rank_all(self, question: str, memories: Sequence[Memory]) -> list[tuple[float, Memory]]:
        """返回 score >= min_score 的 (分数, memory)，按分数降序。"""
        if not memories:
            return []

        document_vectors = self._document_vectors(memories).vectors
        query_vector = self._query_vector(question)

        sims = document_vectors @ query_vector
        scored = [
            (float(score), memory)
            for score, memory in zip(sims, memories)
            if float(score) >= self.min_score
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[1].memory_id))
        return [(min(1.0, max(0.0, score)), memory) for score, memory in scored]

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
                matched_by=["embedding"],
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

    def _document_vectors(self, memories: Sequence[Memory]) -> _DocumentVectors:
        key = tuple(memory.memory_id for memory in memories)
        cached = self._document_cache.get(key)
        if cached is not None:
            return cached

        import numpy as np

        texts = [build_index_text(memory) for memory in memories]
        digest = hashlib.sha256(
            ("\x00".join([self.model_name, *texts])).encode("utf-8")
        ).hexdigest()[:16]
        path = self.cache_dir / f"{_slug(self.model_name)}-{digest}.npz"

        if path.exists():
            with np.load(path) as stored:
                vectors = stored["vectors"]
        else:
            vectors = self.embed(texts)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            np.savez(path, vectors=vectors)

        entry = _DocumentVectors(vectors=vectors, memories=memories)
        self._document_cache[key] = entry
        return entry
