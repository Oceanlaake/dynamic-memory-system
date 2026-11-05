"""Deterministic B2 dynamic-state resolution.

This is the offline baseline for the course prototype.  It deliberately keeps
retrieval and state resolution separate:

* B1 decides which memories are relevant and supplies ``RetrievalResult``.
* B2 orders comparable memories, labels their relation, selects the memories
  that can answer the question, and returns traceable evidence.

The rules are intentionally conservative.  An unresolved contradiction never
produces an answer, and retrieval scores are never treated as truth or recency.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from typing import Sequence

from backend.dynamic_state.llm import RelationJudge
from backend.dynamic_state.question import (
    DURATION_QUESTION as _DURATION_QUESTION, WORD as _WORD,
    explicit_opposites, is_collection_slot, question_type,
    select_state_slots, state_slot, supports_question,
)
from backend.schemas import (
    AnswerEvidenceRef,
    CandidateMemory,
    EffectiveMemory,
    EvidenceStatus,
    Memory,
    QueryResponse,
    Relation,
    RetrievalResult,
)


_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})(?:[T ][^\s]+)?\b")
_TEXT_DATE = re.compile(
    r"\b(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r",?\s+(\d{4})\b",
    re.IGNORECASE,
)
_SESSION_NUMBER = re.compile(r"(\d+)$")


@dataclass(frozen=True)
class _TimedMemory:
    candidate: CandidateMemory
    effective_at: datetime | None
    observed_at: datetime | None
    session_order: int | None

    @property
    def memory(self) -> Memory:
        return self.candidate.memory

    @property
    def sort_key(self) -> tuple[int, datetime, int, str]:
        point = self.effective_at or self.observed_at
        return (
            0 if point is not None else 1,
            point or datetime.max,
            self.session_order if self.session_order is not None else 10**9,
            self.memory.memory_id,
        )


class RuleBasedDynamicStateResolver:
    """Explainable B2 resolver with an optional judge for ambiguous pairs."""

    def __init__(self, relation_judge: RelationJudge | None = None) -> None:
        self._relation_judge = relation_judge

    def resolve(self, retrieval: RetrievalResult) -> QueryResponse:
        """Legacy offline regression path; public QA uses analyze() plus an LLM."""
        return self._resolve(retrieval, legacy_answer=True)

    def analyze(self, retrieval: RetrievalResult) -> QueryResponse:
        return self._resolve(retrieval, legacy_answer=False)

    def _resolve(self, retrieval: RetrievalResult, *, legacy_answer: bool) -> QueryResponse:
        if retrieval.degraded or not retrieval.candidates:
            return self._response(retrieval, answer=None, degraded=True)

        timed = [self._timed(candidate) for candidate in retrieval.candidates]
        relations = self._relations(retrieval.question, timed)
        resolution_input = self._answerable_candidates(retrieval.question, timed)
        if not resolution_input:
            return self._response(
                retrieval,
                relations=relations,
                answer=None,
                degraded=True,
            )

        answerable_ids = {item.memory.memory_id for item in resolution_input}
        relevant_relations = [
            relation
            for relation in relations
            if relation.from_ in answerable_ids and relation.to in answerable_ids
        ]

        if any(relation.relation == "CONFLICT" for relation in relevant_relations):
            return self._response(
                retrieval,
                relations=relations,
                answer=None,
                evidence_status="conflict",
            )

        effective = self._effective_memories(
            retrieval.question,
            resolution_input,
            relevant_relations,
        )
        if not effective:
            kind = question_type(retrieval.question)
            status: EvidenceStatus = "insufficient"
            if kind == "duration":
                status = "missing_anchor"
            elif kind == "change":
                status = "missing_transition"
                groups: dict[tuple[str, str], list[_TimedMemory]] = defaultdict(list)
                for item in resolution_input:
                    if (slot := state_slot(item.memory)) is not None:
                        groups[slot].append(item)
                if any(len(group) > 1 for group in groups.values()):
                    status = "unorderable"
            return self._response(
                retrieval,
                relations=relations,
                answer=None,
                degraded=True,
                evidence_status=status,
            )
        answer = self._answer(retrieval.question, effective) if legacy_answer else None
        evidence = self._evidence(effective)
        return self._response(
            retrieval,
            relations=relations,
            effective_memories=[item[1] for item in effective],
            answer=answer,
            evidence=evidence,
            evidence_status="sufficient",
        )

    def _answerable_candidates(
        self,
        question: str,
        memories: Sequence[_TimedMemory],
    ) -> list[_TimedMemory]:
        """Keep memories that contain evidence for the question's core concepts.

        Duration questions are multi-hop: their start event may not repeat the action
        named in the question, so the dedicated duration resolver receives all candidates.
        Other questions must match at least one non-stopword term beyond the candidate's
        subject name. This prevents a subject-only hit (for example ``Jon`` when asking
        about an unstored ``gender`` attribute) from becoming an effective memory.
        """
        query_terms = set(_WORD.findall(question.casefold()))
        named_subjects = {
            item.memory.subject.strip().casefold()
            for item in memories
            if (terms := set(_WORD.findall(item.memory.subject.casefold()))) and terms <= query_terms
        }
        scoped = [item for item in memories if not named_subjects
                  or item.memory.subject.strip().casefold() in named_subjects]
        if _DURATION_QUESTION.match(question):
            return scoped
        supporting = [item for item in scoped if supports_question(question, item.memory)]
        if question_type(question) not in {"current_state", "change"}:
            return supporting
        slots = select_state_slots(question, [item.candidate for item in supporting])
        if not slots:
            return supporting
        return [item for item in scoped if state_slot(item.memory) in slots]

    _TIME_QUESTION = re.compile(
        r"\bwhen\b|\bwhat\s+(?:date|day|year|month|time)\b|\bhow\s+long\s+ago\b",
        re.IGNORECASE,
    )

    def _asks_for_time(self, question: str) -> bool:
        return bool(self._TIME_QUESTION.search(question))

    def _response(
        self,
        retrieval: RetrievalResult,
        *,
        relations: Sequence[Relation] = (),
        effective_memories: Sequence[EffectiveMemory] = (),
        answer: str | None,
        evidence: Sequence[AnswerEvidenceRef] = (),
        degraded: bool | None = None,
        evidence_status: EvidenceStatus | None = None,
    ) -> QueryResponse:
        return QueryResponse(
            evidence_status=evidence_status or ("sufficient" if answer is not None else "insufficient"),
            sample_id=retrieval.sample_id,
            question=retrieval.question,
            candidate_memories=retrieval.candidates,
            relations=list(relations),
            effective_memories=list(effective_memories),
            answer=answer,
            evidence=list(evidence),
            degraded=retrieval.degraded if degraded is None else degraded,
        )

    def _relations(self, question: str, memories: Sequence[_TimedMemory]) -> list[Relation]:
        exact_slots: dict[tuple[str, str], list[_TimedMemory]] = defaultdict(list)
        topics: dict[tuple[str, str], list[_TimedMemory]] = defaultdict(list)

        for item in memories:
            memory = item.memory
            if not memory.attribute:
                continue
            subject = memory.subject.strip().casefold()
            attribute = memory.attribute.strip().casefold()
            exact_slots[(subject, attribute)].append(item)
            namespace = self._namespace(attribute)
            if namespace:
                topics[(subject, namespace)].append(item)

        relations: list[Relation] = []
        seen_pairs: set[tuple[str, str]] = set()

        for slot in exact_slots.values():
            ordered = sorted(slot, key=lambda item: item.sort_key)
            for older, newer in zip(ordered, ordered[1:]):
                relation = self._same_slot_relation(question, older, newer)
                if relation is None:
                    continue
                relations.append(relation)
                seen_pairs.add((relation.from_, relation.to))
            # Collection buckets contain independent facts. An unrelated middle
            # fact must not hide a clear contradiction between two other nodes.
            if is_collection_slot(ordered[0].memory):
                for first, second in combinations(ordered, 2):
                    pair = (first.memory.memory_id, second.memory.memory_id)
                    if pair in seen_pairs or not explicit_opposites(first.memory, second.memory):
                        continue
                    relation = self._same_slot_relation(question, first, second)
                    if relation is not None:
                        relations.append(relation)
                        seen_pairs.add(pair)

        for topic in topics.values():
            ordered = sorted(topic, key=lambda item: item.sort_key)
            for older, newer in zip(ordered, ordered[1:]):
                pair = (older.memory.memory_id, newer.memory.memory_id)
                if pair in seen_pairs or older.memory.attribute == newer.memory.attribute:
                    continue
                fallback = None
                if self._compare_time(older, newer) is not None:
                    fallback = Relation(
                        **{
                            "from": older.memory.memory_id,
                            "to": newer.memory.memory_id,
                            "relation": "UPDATE",
                            "reason": (
                                f"The later memory adds {newer.memory.attribute} for the same "
                                f"{self._namespace(newer.memory.attribute or '')} topic without "
                                f"invalidating {older.memory.attribute}."
                            ),
                        }
                    )
                relation = self._judge_or_fallback(question, older, newer, fallback)
                if relation is None:
                    continue
                relations.append(relation)
                seen_pairs.add(pair)

        return sorted(relations, key=lambda item: (item.from_, item.to, item.relation))

    def _same_slot_relation(
        self,
        question: str,
        older: _TimedMemory,
        newer: _TimedMemory,
    ) -> Relation | None:
        previous = older.memory
        current = newer.memory
        previous_value, current_value = self._normalise(previous.value), self._normalise(current.value)
        same_value = (
            bool(previous_value and previous_value == current_value)
            or self._normalise(previous.content) == self._normalise(current.content)
        )
        ordering = self._compare_time(older, newer)

        if same_value:
            return Relation(
                **{
                    "from": previous.memory_id,
                    "to": current.memory_id,
                    "relation": "RETAIN",
                    "reason": (
                        f"Both memories report the same {previous.attribute} value; the later "
                        "evidence confirms rather than replaces it."
                    ),
                }
            )

        if ((is_collection_slot(previous) or question_type(question) == "factual")
                and not explicit_opposites(previous, current)):
            # Retrieval cues are not automatically exclusive state dimensions.
            # A factual question (names, dates, participants, etc.) may need
            # multiple distinct facts; avoid inventing a temporal state relation.
            # Preserve explicit contradictions and dynamic-state checks.
            # An explicitly configured semantic judge can still resolve the pair.
            return self._judge_or_fallback(question, older, newer, None)

        if ordering is None or ordering == 0:
            fallback = Relation(
                **{
                    "from": previous.memory_id,
                    "to": current.memory_id,
                    "relation": "CONFLICT",
                    "reason": (
                        f"The memories give incompatible {previous.attribute} values and their "
                        "effective order cannot be established."
                    ),
                }
            )
        else:
            fallback = Relation(
                **{
                    "from": previous.memory_id,
                    "to": current.memory_id,
                    "relation": "SUPERSEDE",
                    "reason": (
                        f"The later memory changes {previous.subject}'s {previous.attribute} "
                        f"from {previous.value or 'an earlier value'} to "
                        f"{current.value or 'a later value'}, so the earlier value is historical."
                    ),
                }
            )

        # Observation/session order only tells us when something was mentioned. It cannot prove
        # that two differently worded values are different states, or that a later mention is a
        # later event. Only two explicit effective dates make SUPERSEDE deterministic.
        if not self._has_explicit_effective_order(older, newer):
            return self._judge_or_fallback(question, older, newer, fallback) or fallback
        return fallback

    @staticmethod
    def _has_explicit_effective_order(first: _TimedMemory, second: _TimedMemory) -> bool:
        return (
            first.effective_at is not None
            and second.effective_at is not None
            and first.effective_at != second.effective_at
        )

    def _judge_or_fallback(
        self,
        question: str,
        first: _TimedMemory,
        second: _TimedMemory,
        fallback: Relation | None,
    ) -> Relation | None:
        if self._relation_judge is None:
            return fallback
        try:
            decision = self._relation_judge.judge(question, first.memory, second.memory)
        except Exception:
            decision = None
        if decision is None:
            return fallback
        return Relation(
            **{
                "from": first.memory.memory_id,
                "to": second.memory.memory_id,
                "relation": decision.relation,
                "reason": decision.reason,
            }
        )

    def _effective_memories(
        self,
        question: str,
        memories: Sequence[_TimedMemory],
        relations: Sequence[Relation],
    ) -> list[tuple[_TimedMemory, EffectiveMemory]]:
        duration_match = _DURATION_QUESTION.match(question)
        if duration_match:
            duration = self._duration_memories(memories, duration_match.group(2))
            if duration:
                start, end = duration
                end_role = "opening_time" if "open" in duration_match.group(2).casefold() else "end_time"
                return [
                    (start, EffectiveMemory(memory_id=start.memory.memory_id, role="start_time")),
                    (end, EffectiveMemory(memory_id=end.memory.memory_id, role=end_role)),
                ]
            return []

        if question_type(question) == "change":
            by_id = {item.memory.memory_id: item for item in memories}
            connected: set[str] = set()
            for relation in relations:
                first, second = by_id[relation.from_], by_id[relation.to]
                if (state_slot(first.memory) is not None
                        and state_slot(first.memory) == state_slot(second.memory)
                        and self._compare_time(first, second) not in {None, 0}
                        and relation.relation in {"RETAIN", "UPDATE", "SUPERSEDE"}):
                    connected.update((relation.from_, relation.to))
            ordered = sorted((by_id[key] for key in connected), key=lambda item: item.sort_key)
            return [(item, EffectiveMemory(memory_id=item.memory.memory_id, role="state_history"))
                    for item in ordered]

        if question_type(question) == "factual" and self._asks_for_time(question):
            best = max(
                memories,
                key=lambda item: (int(item.effective_at is not None), -item.candidate.rank),
            )
            role = "supporting_event" if best.memory.type == "event" else "current_state"
            return [(best, EffectiveMemory(memory_id=best.memory.memory_id, role=role))]

        superseded = {
            relation.from_
            for relation in relations
            if relation.relation == "SUPERSEDE"
        }
        available = [item for item in memories if item.memory.memory_id not in superseded]
        if not available:
            return []

        best = min(available, key=lambda item: item.candidate.rank)
        role = "current_state" if best.memory.type in {"state", "goal", "preference"} else "supporting_event"
        return [(best, EffectiveMemory(memory_id=best.memory.memory_id, role=role))]

    def _duration_memories(
        self, memories: Sequence[_TimedMemory], action: str
    ) -> tuple[_TimedMemory, _TimedMemory] | None:
        dated = [item for item in memories if item.effective_at is not None]
        if len(dated) < 2:
            return None

        terminal = max(dated, key=lambda item: self._terminal_score(item, action))
        if self._terminal_score(terminal, action)[0] < 5:
            return None
        earlier = [
            item
            for item in dated
            if item.memory.memory_id != terminal.memory.memory_id
            and item.memory.subject.strip().casefold() == terminal.memory.subject.strip().casefold()
            and item.effective_at < terminal.effective_at
        ]
        if not earlier:
            return None
        start = max(earlier, key=self._start_score)
        if self._start_score(start)[0] < 5:
            return None
        return start, terminal

    def _terminal_score(
        self, item: _TimedMemory, action: str
    ) -> tuple[int, int, datetime]:
        memory = item.memory
        text = " ".join(filter(None, [memory.attribute, memory.value, memory.content])).casefold()
        action_words = set(_WORD.findall(action.casefold()))
        memory_words = set(_WORD.findall(text))
        score = 2 * len(action_words & memory_words)
        if "lifecycle" in text:
            score += 4
        if any(word in text for word in ("opening", "opened", "launch")):
            score += 5
        if memory.type == "event":
            score += 1
        return score, -item.candidate.rank, item.effective_at or datetime.min

    def _start_score(self, item: _TimedMemory) -> tuple[int, int, float]:
        memory = item.memory
        evidence = " ".join(ref.quote or "" for ref in memory.evidence)
        text = f"{memory.content} {memory.value or ''} {evidence}".casefold()
        score = 0
        if any(word in text for word in ("start", "starting", "began", "lost my job", "lost his job")):
            score += 5
        if memory.type in {"event", "goal"}:
            score += 1
        return score, -item.candidate.rank, -(item.effective_at or datetime.max).timestamp()

    def _answer(
        self,
        question: str,
        effective: Sequence[tuple[_TimedMemory, EffectiveMemory]],
    ) -> str | None:
        if not effective:
            return None

        duration_match = _DURATION_QUESTION.match(question)
        if duration_match and len(effective) == 2:
            start = effective[0][0].effective_at
            end = effective[1][0].effective_at
            if start is None or end is None or end < start:
                return None
            months = (end.year - start.year) * 12 + end.month - start.month + 1
            if months <= 0:
                return None
            duration = f"{self._number_word(months)} months" if months != 1 else "one month"
            subject = duration_match.group(1).strip()
            action = duration_match.group(2).strip().rstrip("?")
            return f"It took {subject} {duration} to {action}."

        if question_type(question) == "change":
            return " → ".join(item.memory.content for item, _ in effective)
        if self._asks_for_time(question) and effective[0][0].effective_at is not None:
            return effective[0][0].effective_at.strftime("%d %B, %Y")
        return effective[0][0].memory.content

    def _evidence(
        self,
        effective: Sequence[tuple[_TimedMemory, EffectiveMemory]],
    ) -> list[AnswerEvidenceRef]:
        evidence: list[AnswerEvidenceRef] = []
        seen: set[tuple[str, str]] = set()
        for item, effective_memory in effective:
            refs = item.memory.evidence
            if not refs:
                continue
            ref = refs[-1] if effective_memory.role in {"end_time", "opening_time"} else refs[0]
            key = (ref.session_id, ref.dia_id)
            if key not in seen:
                evidence.append(AnswerEvidenceRef(session_id=ref.session_id, dia_id=ref.dia_id))
                seen.add(key)
        return evidence

    def _timed(self, candidate: CandidateMemory) -> _TimedMemory:
        memory = candidate.memory
        declared_effective = getattr(memory.time, "effective_at", None)
        effective_at = self._parse_date(declared_effective) or self._parse_date(memory.content)
        observed_at = self._parse_date(memory.time.date_time)
        session_match = _SESSION_NUMBER.search(memory.time.session_id)
        session_order = int(session_match.group(1)) if session_match else None
        return _TimedMemory(candidate, effective_at, observed_at, session_order)

    @staticmethod
    def _compare_time(first: _TimedMemory, second: _TimedMemory) -> int | None:
        for left, right in (
            (first.effective_at, second.effective_at),
            (first.observed_at, second.observed_at),
        ):
            if left is not None and right is not None:
                return (right > left) - (right < left)
        if first.session_order is not None and second.session_order is not None:
            return (second.session_order > first.session_order) - (
                second.session_order < first.session_order
            )
        return None

    @staticmethod
    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        iso_match = _ISO_DATE.search(value)
        if iso_match:
            try:
                return datetime.strptime(iso_match.group(1), "%Y-%m-%d")
            except ValueError:
                pass
        text_match = _TEXT_DATE.search(value)
        if text_match:
            day, month, year = text_match.groups()
            try:
                return datetime.strptime(f"{day} {month} {year}", "%d %B %Y")
            except ValueError:
                pass
        return None

    @staticmethod
    def _normalise(value: str | None) -> str:
        return " ".join(_WORD.findall((value or "").casefold()))

    @staticmethod
    def _namespace(attribute: str) -> str:
        return attribute.split(".", 1)[0] if "." in attribute else ""

    @staticmethod
    def _number_word(value: int) -> str:
        words = {
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            5: "five",
            6: "six",
            7: "seven",
            8: "eight",
            9: "nine",
            10: "ten",
            11: "eleven",
            12: "twelve",
        }
        return words.get(value, str(value))
