"""检索器的代码级边界。

B2(Dynamic State)与 C(Web)只依赖本协议，不关心内部用的是 BM25、embedding 还是混合策略。
换实现时不需要改动任何调用方。
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from backend.schemas import Memory, RetrievalResult, Strategy


@runtime_checkable
class Retriever(Protocol):
    name: Strategy

    def retrieve(
        self,
        question: str,
        memories: Sequence[Memory],
        top_k: int,
        *,
        sample_id: str = "",
    ) -> RetrievalResult:
        """返回按 score 降序的至多 top_k 条候选；没有命中时返回空列表并置 degraded=True。"""
        ...
