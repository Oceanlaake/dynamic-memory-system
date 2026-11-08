"""Shared query orchestration used by HTTP and controlled evaluation."""

from collections.abc import Sequence

from backend.dynamic_state.base import DynamicStateResolver
from backend.graph_memory import expand_graph_memories
from backend.retrieval.expansion import expand_state_slots
from backend.schemas import Memory, QueryResponse, RetrievalResult


def resolve_query(
    retrieval: RetrievalResult,
    sample_memories: Sequence[Memory],
    resolver: DynamicStateResolver,
    *,
    expand_slots: bool = False,
    max_expansion_memories: int = 50,
    graph_expand: bool = False,
    graph_max_hops: int = 3,
    max_graph_memories: int = 5,
    analysis_only: bool = False,
) -> QueryResponse:
    expanded, trace = expand_state_slots(
        retrieval, sample_memories, enabled=expand_slots,
        max_new_memories=max_expansion_memories,
    )
    graph_expanded, graph_trace = expand_graph_memories(
        expanded, sample_memories, enabled=graph_expand,
        max_hops=graph_max_hops, max_new_memories=max_graph_memories,
    )
    response = resolver.analyze(graph_expanded) if analysis_only else resolver.resolve(graph_expanded)
    response.expansion = trace
    response.graph = graph_trace
    if trace.truncated or trace.stop_reason == "no_seed":
        # A missing relevant seed or omitted versions cannot establish the
        # selected state. Keep candidates visible without offering a guess.
        response.answer = None
        response.effective_memories = []
        response.evidence = []
        response.evidence_status = "insufficient"
        response.degraded = True
    return response
