"""Shared query orchestration used by HTTP and controlled evaluation."""

from collections.abc import Sequence

from backend.dynamic_state.base import DynamicStateResolver
from backend.retrieval.expansion import expand_state_slots
from backend.schemas import Memory, QueryResponse, RetrievalResult


def resolve_query(
    retrieval: RetrievalResult,
    sample_memories: Sequence[Memory],
    resolver: DynamicStateResolver,
    *,
    expand_slots: bool = False,
    max_expansion_memories: int = 50,
    analysis_only: bool = False,
) -> QueryResponse:
    expanded, trace = expand_state_slots(
        retrieval, sample_memories, enabled=expand_slots,
        max_new_memories=max_expansion_memories,
    )
    response = resolver.analyze(expanded) if analysis_only else resolver.resolve(expanded)
    response.expansion = trace
    if trace.truncated or trace.stop_reason == "no_seed":
        # A missing relevant seed or omitted versions cannot establish the
        # selected state. Keep candidates visible without offering a guess.
        response.answer = None
        response.effective_memories = []
        response.evidence = []
        response.evidence_status = "insufficient"
        response.degraded = True
    return response
