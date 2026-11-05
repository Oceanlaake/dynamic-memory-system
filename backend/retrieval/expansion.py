"""Bounded query-seeded retrieval over state history or evidence neighborhoods.

This is a set expansion, not a new similarity ranking. Added candidates get a
zero placeholder score and an explicit source; initial ranking is preserved.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.dynamic_state.question import (
    WORD, question_type, select_state_slots, state_slot, supports_question,
)
from backend.schemas import CandidateMemory, ExpandedSlot, ExpansionTrace, Memory, RetrievalResult
from backend.retrieval.evidence import expand_query_evidence


def expand_state_slots(
    retrieval: RetrievalResult,
    sample_memories: Sequence[Memory],
    *,
    enabled: bool = False,
    max_new_memories: int = 50,
) -> tuple[RetrievalResult, ExpansionTrace]:
    """Caller must supply only memories belonging to retrieval.sample_id.

    Dynamic scalar queries retain complete same-slot history when under the cap.
    Factual/collection queries can retrieve related source neighbors without
    pretending that every fact sharing an attribute is a replaceable state.
    """
    if not 1 <= max_new_memories <= 200:
        raise ValueError("max_new_memories must be between 1 and 200")
    kind = question_type(retrieval.question)
    trace = ExpansionTrace(
        enabled=enabled, question_type=kind,
        initial_count=len(retrieval.candidates), stop_reason="disabled",
    )
    if not enabled:
        return retrieval, trace
    if kind == "factual":
        return expand_query_evidence(
            retrieval, sample_memories, trace, max_new_memories=max_new_memories,
        )

    query_terms = set(WORD.findall(retrieval.question.casefold()))
    named_subjects = {
        memory.subject.strip().casefold()
        for memory in sample_memories
        if (terms := set(WORD.findall(memory.subject.casefold()))) and terms <= query_terms
    }
    relevant_slots = {
        slot
        for candidate in retrieval.candidates
        if (slot := state_slot(candidate.memory)) is not None
        and supports_question(retrieval.question, candidate.memory)
        and (not named_subjects or slot[0] in named_subjects)
    }
    slots = select_state_slots(retrieval.question, retrieval.candidates, subject_scope=sample_memories)
    trace.expanded_slots = [ExpandedSlot(subject=s, attribute=a) for s, a in sorted(slots)]
    if retrieval.degraded:
        trace.stop_reason = "no_seed"
        return retrieval, trace
    if not relevant_slots or not slots:
        # Collection attributes remain usable retrieval cues. They are not
        # promoted to mutually exclusive state dimensions by this fallback.
        return expand_query_evidence(
            retrieval, sample_memories, trace, max_new_memories=max_new_memories,
        )

    candidates = []
    seen = set()
    for candidate in retrieval.candidates:
        if candidate.memory.memory_id not in seen:
            candidates.append(candidate.model_copy(update={"rank": len(candidates) + 1}))
            seen.add(candidate.memory.memory_id)
    # Stable across JSON ordering. Truncation is conservative: the query service
    # refuses an answer if a selected slot's closure could not be completed.
    eligible = {m.memory_id: m for m in sample_memories
                if m.memory_id not in seen and state_slot(m) in slots}
    trace.eligible_count = len(eligible)
    for memory in sorted(eligible.values(), key=lambda item: item.memory_id):
        if len(trace.added_memory_ids) == max_new_memories:
            trace.truncated = True
            break
        candidates.append(CandidateMemory(
            memory=memory, rank=len(candidates) + 1, score=0,
            candidate_source="slot_expansion",
            expansion_reason="same_slot",
        ))
        trace.added_memory_ids.append(memory.memory_id)
        seen.add(memory.memory_id)
    trace.stop_reason = (
        "candidate_limit" if trace.truncated else
        "expanded" if trace.added_memory_ids else "no_new_memory"
    )
    return retrieval.model_copy(update={"candidates": candidates}), trace
