"""Question-conditioned evidence neighborhoods, independent of state labels.

An attribute may organize facts without defining mutually exclusive states.
Facts with no attribute can also be found through nearby source turns. Gold QA
answers/evidence never enter this module.
"""

from __future__ import annotations

from collections.abc import Sequence
import re

from backend.dynamic_state.question import state_slot
from backend.retrieval.keyword import BM25Retriever
from backend.retrieval.text import tokenize
from backend.schemas import CandidateMemory, ExpandedSlot, ExpansionTrace, Memory, RetrievalResult

_TURN = re.compile(r"D(\d+):(\d+)")
_QUERY_CONTROLS = frozenset(
    "name names type types kind kinds current currently now latest status change changed changes long take".split()
)


def _terms(text: str) -> set[str]:
    return {word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word
            for word in tokenize(text) if word != "s"}


def _coordinates(memory: Memory) -> list[tuple[int, int]]:
    return [(int(match[1]), int(match[2])) for ref in memory.evidence
            if (match := _TURN.fullmatch(ref.dia_id)) is not None]


def expand_query_evidence(
    retrieval: RetrievalResult,
    sample_memories: Sequence[Memory],
    trace: ExpansionTrace,
    *,
    max_new_memories: int,
) -> tuple[RetrievalResult, ExpansionTrace]:
    """Add at most initial-count memories, constrained by related source/slots.

    This is a relevance-budgeted retrieval step, not a complete state closure.
    Unselected neighbors therefore do not automatically invalidate an answer.
    """
    trace.expansion_policy = "query_evidence"
    query_terms = _terms(retrieval.question)
    named = {m.subject.strip().casefold() for m in sample_memories
             if (terms := _terms(m.subject)) and terms <= query_terms}
    names = set().union(*(_terms(m.subject) for m in sample_memories
                         if m.subject.strip().casefold() in named))
    core = query_terms - names - _QUERY_CONTROLS
    generic_buckets = {"plan", "goal", "project"}
    if core - generic_buckets:
        core -= generic_buckets

    def related(memory: Memory) -> bool:
        text = " ".join(filter(None, [memory.attribute, memory.value, memory.content]))
        return bool(core & _terms(text))

    seeds = [candidate.memory for candidate in retrieval.candidates if related(candidate.memory)
             and (not named or candidate.memory.subject.strip().casefold() in named)]
    if retrieval.degraded or not seeds:
        trace.stop_reason = "no_seed"
        return retrieval, trace
    slots = {slot for m in seeds if (slot := state_slot(m)) is not None}
    trace.expanded_slots = [ExpandedSlot(subject=s, attribute=a) for s, a in sorted(slots)]
    anchors = [coordinate for m in seeds for coordinate in _coordinates(m)]
    existing = {candidate.memory.memory_id for candidate in retrieval.candidates}
    # A local ranker avoids sharing cached indices between mutable test/store versions.
    ranked = BM25Retriever().rank_all(retrieval.question, sample_memories)
    additions: dict[str, tuple[float, Memory, str]] = {}
    for score, memory in ranked:
        if memory.memory_id in existing or not related(memory) or score < 0.15:
            continue
        if named and memory.subject.strip().casefold() not in named:
            # A nearby invitation/interaction may be attributed to the other
            # participant, but must explicitly mention a queried subject.
            content_terms = _terms(memory.content)
            if not any(_terms(name) <= content_terms for name in named):
                continue
        distance = min((abs(turn - anchor) for session, turn in _coordinates(memory)
                        for origin, anchor in anchors if session == origin), default=10**9)
        same_slot = state_slot(memory) in slots
        if not same_slot and distance > 1:
            continue
        reason = "same_slot" if same_slot else "same_turn" if distance == 0 else "adjacent_turn"
        priority = score + 0.10 * same_slot + 0.10 * (distance == 0) + 0.05 * (distance == 1)
        additions[memory.memory_id] = (priority, memory, reason)
    ordered = sorted(additions.values(), key=lambda item: (-item[0], item[1].memory_id))
    budget = min(max_new_memories, len(existing))
    trace.budget_limited = len(ordered) > budget
    trace.eligible_count = len(ordered)
    candidates = []
    seen = set()
    for candidate in retrieval.candidates:
        if candidate.memory.memory_id not in seen:
            candidates.append(candidate.model_copy(update={"rank": len(candidates)+1}))
            seen.add(candidate.memory.memory_id)
    for _, memory, reason in ordered[:budget]:
        candidates.append(CandidateMemory(
            memory=memory, score=0, rank=len(candidates)+1,
            candidate_source="slot_expansion" if reason == "same_slot" else "context_expansion",
            expansion_reason=reason,
        ))
        trace.added_memory_ids.append(memory.memory_id)
    trace.stop_reason = "expanded" if trace.added_memory_ids else "no_new_memory"
    return retrieval.model_copy(update={"candidates": candidates}), trace
