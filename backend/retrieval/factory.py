"""检索器工厂：由 DMS_RETRIEVER 环境变量选择策略，默认 auto。

auto = 能用 embedding 就用 hybrid，否则静默退回 bm25。
显式指定 embedding/hybrid 时不做回退，让配置错误直接暴露。
"""

from __future__ import annotations

import importlib.util
import logging
import os

from backend.retrieval.base import Retriever
from backend.retrieval.keyword import BM25Retriever

logger = logging.getLogger(__name__)

CHOICES = ("auto", "bm25", "embedding", "hybrid")


def build_retriever(choice: str | None = None) -> Retriever:
    selected = (choice or os.environ.get("DMS_RETRIEVER") or "auto").strip().lower()
    if selected not in CHOICES:
        raise ValueError(f"DMS_RETRIEVER must be one of {CHOICES}, got {selected!r}")

    if selected == "bm25":
        return BM25Retriever()
    if selected == "embedding":
        return _embedding()
    if selected == "hybrid":
        return _hybrid()

    if not _has_sentence_transformers():
        logger.warning("sentence-transformers is not installed; using bm25")
        return BM25Retriever()
    try:
        return _hybrid(force_load=True)
    except Exception as exc:  # model unavailable offline / cache missing
        logger.warning("embedding unavailable (%s); using bm25", exc)
        return BM25Retriever()


def _has_sentence_transformers() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


def _embedding() -> Retriever:
    from backend.retrieval.embedding import SentenceTransformerRetriever

    return SentenceTransformerRetriever()


def _hybrid(force_load: bool = False) -> Retriever:
    from backend.retrieval.hybrid import HybridRetriever

    retriever = HybridRetriever(semantic=_embedding())
    if force_load:
        getattr(retriever.semantic, "encoder")
    return retriever
