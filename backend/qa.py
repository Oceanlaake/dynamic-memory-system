"""Shared evidence-first LLM QA for the Web and every formal experiment."""

from __future__ import annotations

from collections.abc import Sequence

from backend.answer import AnswerGenerator
from backend.dynamic_state.base import DynamicStateResolver
from backend.query import resolve_query
from backend.retrieval.text import tokenize
from backend.schemas import (
    AnswerEvidenceRef, GenerationResult, GenerationTrace, Memory, QueryResponse, RetrievalResult,
)

GenerationCache = dict[tuple[str, str], GenerationResult]


def _asks_for_multiple_names(question: str) -> bool:
    """High-precision completion route for explicit plural-name questions."""
    return "names" in tokenize(question)


def _memory_head(memory: Memory) -> str:
    head = " ".join(part for part in (memory.subject, memory.attribute or "", memory.value or "") if part)
    if memory.time.effective_at:
        head += f" (effective {memory.time.effective_at})"
    if memory.time.date_time:
        head += f" (observed {memory.time.date_time})"
    return head


def _record(memory: Memory, hint: str = "") -> str:
    sources = "\n".join(f"  source {r.session_id}/{r.dia_id}: {r.quote or ''}" for r in memory.evidence)
    return f"- [id:{memory.memory_id}] {hint}{_memory_head(memory)}: {memory.content}\n{sources}"


def memory_context(memories: Sequence[Memory]) -> str:
    return "\n".join(_record(m) for m in memories)


def labeled_memory_context(response: QueryResponse) -> str:
    selected = {item.memory_id: item.role for item in response.effective_memories}
    superseded = {r.from_ for r in response.relations if r.relation == "SUPERSEDE"}
    conflicting = {key for r in response.relations if r.relation == "CONFLICT" for key in (r.from_, r.to)}
    records = []
    for candidate in response.candidate_memories:
        m = candidate.memory
        tags = []
        if m.memory_id in selected:
            tags.append(f"rule_selected:{selected[m.memory_id]}")
        if m.memory_id in superseded:
            tags.append("historical")
        if m.memory_id in conflicting:
            tags.append("conflicting")
        if candidate.candidate_source == "graph_expansion":
            tags.append("graph_supplemental")
        records.append(_record(m, f"[{','.join(tags)}] " if tags else ""))
    if not records:
        return ""
    relations = "\n".join(f"{r.from_} -> {r.to}: {r.relation}; {r.reason}" for r in response.relations)
    return (f"Rule evidence hint (not a verified answer): {response.evidence_status}\n"
            + "\n".join(records) + (f"\nRule relation hints:\n{relations}" if relations else ""))


def generate_grounded_answer(
    question: str, context: str, generator: AnswerGenerator, *,
    memories: Sequence[Memory] | None = None, cache: GenerationCache | None = None,
) -> GenerationResult:
    if not context:
        return skipped_generation(generator, "no_evidence")
    key = (question, context)
    if cache is not None and key in cache:
        result = cache[key].model_copy(deep=True)
        result.trace.api_called = False
        result.trace.reused = True
        result.trace.elapsed_ms = 0
        return result
    result = generator.generate(question, context).model_copy(deep=True)
    allowed = {m.memory_id for m in memories or []}
    if (not set(result.memory_ids) <= allowed
            or (memories is not None and result.answer is not None and not result.memory_ids)):
        result.answer, result.memory_ids = None, []
        result.trace.status, result.trace.error_code = "error", "invalid_citation"
    if cache is not None and result.trace.status in {"answered", "refused"}:
        cache[key] = result.model_copy(deep=True)
    return result


def skipped_generation(generator: AnswerGenerator, reason: str) -> GenerationResult:
    return GenerationResult(trace=GenerationTrace(
        provider=getattr(generator, "provider", "injected"), model=getattr(generator, "model", "unknown"),
        status="skipped", error_code=reason,
    ))


def answer_query(
    retrieval: RetrievalResult, sample_memories: Sequence[Memory], resolver: DynamicStateResolver,
    generator: AnswerGenerator, *, expand_slots: bool = False, max_expansion_memories: int = 50,
    graph_expand: bool = False, graph_max_hops: int = 3, max_graph_memories: int = 5,
    graph_retry_on_refusal: bool = False,
    cache: GenerationCache | None = None,
) -> QueryResponse:
    baseline: QueryResponse | None = None
    if graph_expand and graph_retry_on_refusal:
        baseline = answer_query(
            retrieval, sample_memories, resolver, generator,
            expand_slots=expand_slots, max_expansion_memories=max_expansion_memories,
            graph_expand=False, graph_max_hops=graph_max_hops,
            max_graph_memories=max_graph_memories, cache=cache,
        )
        if (baseline.generation is None
                or (baseline.generation.status != "refused"
                    and not _asks_for_multiple_names(retrieval.question))):
            return baseline

    response = resolve_query(retrieval, sample_memories, resolver, expand_slots=expand_slots,
                             max_expansion_memories=max_expansion_memories,
                             graph_expand=graph_expand, graph_max_hops=graph_max_hops,
                             max_graph_memories=max_graph_memories, analysis_only=True)
    trace = response.expansion
    if not response.candidate_memories:
        result = skipped_generation(generator, "no_evidence")
    elif trace and trace.truncated:
        result = skipped_generation(generator, "incomplete_state_history")
    elif trace and trace.stop_reason == "no_seed":
        result = skipped_generation(generator, "no_relevant_seed")
    else:
        result = generate_grounded_answer(
            retrieval.question, labeled_memory_context(response), generator,
            memories=[c.memory for c in response.candidate_memories], cache=cache,
        )
    response.answer = result.answer
    response.answer_memory_ids = result.memory_ids
    response.generation = result.trace
    response.evidence = []
    if result.answer is not None:
        by_id = {c.memory.memory_id: c.memory for c in response.candidate_memories}
        seen = set()
        for memory_id in result.memory_ids:
            for ref in by_id[memory_id].evidence:
                key = (ref.session_id, ref.dia_id)
                if key not in seen:
                    response.evidence.append(AnswerEvidenceRef(session_id=key[0], dia_id=key[1]))
                    seen.add(key)
    if result.trace.status == "error":
        response.degraded = True
    if baseline is not None and baseline.answer is not None:
        added = set(response.graph.added_memory_ids if response.graph else [])
        cites_added = bool(added & set(response.answer_memory_ids))
        if (response.answer is None
                or len(response.answer_memory_ids) <= len(baseline.answer_memory_ids)
                or not cites_added):
            return baseline
    return response


def generation_summary(traces: Sequence[GenerationTrace]) -> dict:
    """Separate standalone token footprints from actual calls with reuse."""
    physical = [t for t in traces if t.api_called]
    fields = ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens", "uncached_input_tokens", "reasoning_tokens")
    footprint, actual = {}, {}
    for field in fields:
        known = [getattr(t.usage, field) for t in traces if getattr(t.usage, field) is not None]
        spent = [getattr(t.usage, field) for t in physical if getattr(t.usage, field) is not None]
        footprint[field] = {"mean_reported": sum(known)/len(known) if known else None, "reported_rows": len(known)}
        actual[field] = {"sum_reported": 0 if not physical else sum(spent) if spent else None,
                         "reported_calls": len(spent)}
    return {"rows": len(traces), "api_calls": len(physical), "reused": sum(t.reused for t in traces),
            "errors": sum(t.status == "error" for t in traces),
            "model_refusals": sum(t.status == "refused" for t in traces),
            "skipped": sum(t.status == "skipped" for t in traces),
            "mean_api_elapsed_ms": sum(t.elapsed_ms for t in physical)/len(physical) if physical else None,
            "standalone_token_footprint": footprint, "actual_calls_usage": actual,
            "usage_scope": "answer_generation_only; reused rows retain original equivalent-call usage for footprint, excluded from actual spend; missing usage is null"}
