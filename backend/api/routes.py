"""HTTP 接口定义。FastAPI 会自动生成 /docs 与 /openapi.json，即机器可校验的接口文档。"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from backend.dynamic_state.base import DynamicStateResolver
from backend.answer import AnswerGenerator, build_answer_generator
from backend.dynamic_state.factory import build_dynamic_state_resolver
from backend.retrieval.base import Retriever
from backend.retrieval.factory import build_retriever
from backend.qa import answer_query
from backend.schemas import (
    ErrorResponse,
    Memory,
    QueryRequest,
    QueryResponse,
    RetrievalRequest,
    RetrievalResult,
    SampleSummary,
)
from backend.store import MemoryStore

router = APIRouter(prefix="/api", tags=["memory"])


@lru_cache(maxsize=1)
def get_store() -> MemoryStore:
    """进程内单例。切换到 embedding 策略或数据更新后需重启服务。"""
    return MemoryStore()


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    """按 DMS_RETRIEVER 选择策略（auto 默认优先 hybrid）。进程内单例。"""
    return build_retriever()


@lru_cache(maxsize=1)
def get_dynamic_state_resolver() -> DynamicStateResolver:
    """B2 resolver singleton; rules-only by default, optionally hybrid."""
    return build_dynamic_state_resolver()


@lru_cache(maxsize=1)
def get_answer_generator() -> AnswerGenerator:
    try:
        return build_answer_generator()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "ANSWER_MODEL_NOT_CONFIGURED", "message": "Configure the answer provider and model.",
        }) from exc


def _require_memories(store: MemoryStore, sample_id: str) -> list[Memory]:
    memories = store.memories(sample_id)
    if memories is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SAMPLE_NOT_FOUND", "message": f"Unknown sample_id: {sample_id}"},
        )
    return memories


@router.get("/health", summary="健康检查")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/samples", response_model=list[SampleSummary], summary="列出已导入的对话样本")
def list_samples(store: MemoryStore = Depends(get_store)) -> list[SampleSummary]:
    return store.summaries()


@router.get(
    "/samples/{sample_id}/memories",
    response_model=list[Memory],
    summary="读取某个样本的全部结构化 Memory",
)
def list_memories(sample_id: str, store: MemoryStore = Depends(get_store)) -> list[Memory]:
    return _require_memories(store, sample_id)


@router.post(
    "/retrieve",
    response_model=RetrievalResult,
    responses={404: {"model": ErrorResponse}},
    summary="B1：问题 -> Top-K 候选记忆",
)
def retrieve(
    request: RetrievalRequest,
    store: MemoryStore = Depends(get_store),
    retriever: Retriever = Depends(get_retriever),
) -> RetrievalResult:
    memories = _require_memories(store, request.sample_id)
    return retriever.retrieve(
        request.question,
        memories,
        request.top_k,
        sample_id=request.sample_id,
    )


@router.post(
    "/query",
    response_model=QueryResponse,
    responses={404: {"model": ErrorResponse}},
    summary="全链路：检索 + 动态状态解析 + 答案与证据",
)
def query(
    request: QueryRequest,
    store: MemoryStore = Depends(get_store),
    retriever: Retriever = Depends(get_retriever),
    resolver: DynamicStateResolver = Depends(get_dynamic_state_resolver),
    generator: AnswerGenerator = Depends(get_answer_generator),
) -> QueryResponse:
    memories = _require_memories(store, request.sample_id)
    retrieval = retriever.retrieve(
        request.question,
        memories,
        request.top_k,
        sample_id=request.sample_id,
    )
    return answer_query(
        retrieval, memories, resolver, generator,
        expand_slots=request.expand_slots,
        max_expansion_memories=request.max_expansion_memories,
    )
