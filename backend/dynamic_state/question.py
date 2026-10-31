"""Shared, conservative English query rules for the LoCoMo prototype."""

from __future__ import annotations

import re

from collections.abc import Sequence

from backend.schemas import CandidateMemory, Memory, QuestionType

DURATION_QUESTION = re.compile(
    r"^\s*how\s+long\s+did\s+it\s+take\s+for\s+(.+?)\s+to\s+(.+?)\??\s*$",
    re.IGNORECASE,
)
WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset("""
    a an the and or but if then than that this these those
    is are was were be been being am do does did doing done have has had having
    how what when where which who whom why for from with without about into over under
    after before his her their its our your my me him them us you i he she it we they
    of on in at to by as so such not no nor only own same too very can will just s
    current currently now latest status change changed changes evolve evolved evolution
""".split())


def question_type(question: str) -> QuestionType:
    if DURATION_QUESTION.match(question):
        return "duration"
    if re.search(r"\b(chang(?:e|ed|es)|evol(?:ve|ved|ution)|transitions?)\b", question, re.I):
        return "change"
    if re.search(r"\b(now|current(?:ly)?|latest|status|still|favou?rite|preferences?)\b", question, re.I):
        return "current_state"
    if re.search(r"\bwhere\b.*\b(?:live|lives|reside|resides)\b", question, re.I):
        return "current_state"
    return "factual"


def supports_question(question: str, memory: Memory) -> bool:
    """Require a content concept beyond the subject's name; never use gold labels."""
    core = set(WORD.findall(question.casefold())) - STOPWORDS
    core -= set(WORD.findall(memory.subject.casefold()))
    text = " ".join(filter(None, [memory.attribute, memory.value, memory.content]))
    return bool(core & set(WORD.findall(text.casefold())))


def state_slot(memory: Memory) -> tuple[str, str] | None:
    subject = memory.subject.strip().casefold()
    attribute = (memory.attribute or "").strip().casefold()
    return (subject, attribute) if subject and attribute else None


# These dimensions collect independent facts rather than one replaceable value.
# Unknown dimensions keep the existing conservative comparison policy. This is
# a schema-level rule, not a list of subjects, questions, or gold evidence IDs.
_COLLECTION_DIMENSIONS = frozenset({
    "venture", "plan", "plans", "goal", "goals", "intention", "intentions",
    "project", "projects", "possession", "possessions", "hobby", "hobbies",
    "offering", "offerings", "support", "anticipation",
})


def is_collection_slot(memory: Memory) -> bool:
    terms = set(WORD.findall((memory.attribute or "").replace("_", " ").casefold()))
    # Explicit lifecycle/state subdimensions are not the broad plan/project bucket.
    if terms & {"status", "stage", "state", "lifecycle"}:
        return False
    return bool(terms & _COLLECTION_DIMENSIONS)


def explicit_opposites(first: Memory, second: Memory) -> bool:
    """Recognize narrow categorical contradictions even in a collection field."""
    tokens = [set(WORD.findall((m.value or "").casefold())) for m in (first, second)]
    negation = {"not", "no", "never"}
    if (bool(tokens[0] & negation) != bool(tokens[1] & negation)
            and tokens[0] - negation and tokens[0] - negation == tokens[1] - negation):
        return True
    for pair in (
        {"open", "closed"}, {"active", "inactive"}, {"enabled", "disabled"},
        {"yes", "no"}, {"employed", "unemployed"}, {"planned", "cancelled"},
    ):
        left, right = tokens[0] & pair, tokens[1] & pair
        if (len(left) == len(right) == 1 and left != right
                and tokens[0] - pair == tokens[1] - pair):
            return True
    return False


def select_state_slots(
    question: str, candidates: Sequence[CandidateMemory], *,
    subject_scope: Sequence[Memory] | None = None,
) -> set[tuple[str, str]]:
    """Select query-relevant, comparable dimensions without gold or time ranking.

    Prefer explicit attribute overlap over generic content overlap, and retain
    one primary dimension per named subject for current/change questions.
    Duration questions may need different start/end roles, so keep their
    relevant non-collection seeds. This does not invent cross-slot links.
    """
    query_terms = set(WORD.findall(question.casefold()))
    named = {
        m.subject.strip().casefold()
        for m in (subject_scope if subject_scope is not None else [c.memory for c in candidates])
        if (terms := set(WORD.findall(m.subject.casefold()))) and terms <= query_terms
    }
    eligible = [c for c in candidates
                if state_slot(c.memory) is not None and not is_collection_slot(c.memory)
                and supports_question(question, c.memory)
                and (not named or c.memory.subject.strip().casefold() in named)]
    if question_type(question) == "duration":
        return {slot for c in eligible if (slot := state_slot(c.memory)) is not None}
    best: dict[str, tuple[tuple[int, int], tuple[str, str]]] = {}
    for candidate in eligible:
        memory = candidate.memory
        slot = state_slot(memory)
        assert slot is not None
        terms = query_terms - set(WORD.findall(memory.subject.casefold()))
        terms -= STOPWORDS - {"status"}
        attribute_terms = set(WORD.findall((memory.attribute or "").replace("_", " ").casefold()))
        score = (len(terms & attribute_terms), -candidate.rank)
        if slot[0] not in best or score > best[slot[0]][0]:
            best[slot[0]] = (score, slot)
    return {slot for _, slot in best.values()}
