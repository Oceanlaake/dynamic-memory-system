"""抽取用的提示词模板。

提示词只描述“抽什么、怎么填字段”，不包含任何 B 部分（检索/状态）的逻辑。
所有输出都被要求是单个 JSON 对象，便于 `json.loads` 直接解析。
"""

from __future__ import annotations

import json
from typing import Sequence

from backend.extract.locomo import Observation, Sample, Session, Turn

MEMORY_TYPES = ("state", "event", "goal", "preference", "requirement")

SYSTEM_PROMPT = f"""You are a meticulous information-extraction engine for a long-term conversational memory system.
You read one session of a two-person conversation and turn it into atomic, self-contained memories.

MEMORY TYPES (choose exactly one):
- "state": a current, ongoing fact about a person: identity, job, residence, relationship, health,
  possession, capability, status, or a state that holds over a period.
- "event": something that happened or will happen at a specific time: a trip, a purchase, a
  performance, a meeting, a medical visit, a competition, a celebration.
- "goal": an intention, plan, aspiration or desired future state that is not yet achieved.
- "preference": a like, dislike, favourite, taste, opinion, or habitual choice.
- "requirement": a need, obligation, constraint, or something the person must have/do.

FIELD RULES:
1. "subject": exactly one of the two speaker names given to you. Never use a pronoun, never invent names.
   A fact about another person (a child, a friend) is still stored with the SPEAKER as subject, and the
   other person is named inside "content".
2. "content": one complete English sentence, understandable on its own, always naming the subject
   explicitly. No pronouns standing for the subject, no "he said that", no hedges such as "might".
3. "attribute": a short snake_case key naming the dimension being described, reusable across memories
   of the same kind, e.g. "employment_status", "residence_city", "dance_studio.lifecycle_stage",
   "favorite_dance_style", "children_interest", "health_condition". Required for every type except
   "event" (for "event" it may be null).
4. "value": the concrete value of that attribute, snake_case or a short lowercase phrase, e.g.
   "unemployed", "sweden", "searching_for_location", "contemporary". Required for every type except
   "event" (for "event" it may be null).
5. "effective_at": "YYYY-MM-DD" ONLY when the dialogue states an absolute date, or a date that can be
   computed unambiguously from the session date ("yesterday", "last Saturday", "the week before
   9 June 2023"). Otherwise null. Never guess a date from vague wording such as "a few years ago".
6. "evidence": 1 to 3 items, each {{"dia_id": "...", "quote": "..."}}. "dia_id" must be one of the ids
   shown to you. "quote" must be copied VERBATIM from that turn's text (or from its image caption) —
   no paraphrase, no ellipsis, no joining of two turns. Prefer the shortest span that proves the memory.
7. "confidence": number between 0 and 1; use >= 0.9 only when the fact is stated explicitly.

PREFERRED ATTRIBUTE NAMES (reuse these exact names whenever they fit; consistency across sessions
matters more than precision of naming):
employment_status, career_goal, business_venture, business_status, education, residence, relationships,
family, health_condition, hobby, favorite_activity, pet_ownership, finance, identity, possession,
future_plan, travel_plan, emotional_state, social_support, skill, daily_routine, volunteering, diet,
media_preference, sport, creative_project.
Only when none of them fits, invent a new snake_case name of at most three words (e.g.
"dance_studio.lifecycle_stage") and reuse that same name for the same dimension inside this session.

WHAT TO EXTRACT:
- Durable facts about either speaker: states, completed events, plans, preferences, requirements.
- Facts revealed through stories, photo captions, and answers to questions.
- A later statement in the same session can refine an earlier one; keep BOTH only if they describe
  different attributes or genuinely different moments. If it is the same fact restated, emit ONE memory
  with several evidence refs.

WHAT TO SKIP:
- Greetings, small talk, jokes, questions, acknowledgements, and pure conversational filler.
- Facts about the world in general (definitions, trivia) unless a speaker states it about themselves.
- Anything you cannot ground in a quoted turn.

OUTPUT FORMAT (JSON object, nothing else):
{{"memories": [
  {{
    "subject": "Caroline",
    "type": "state",
    "attribute": "employment_status",
    "value": "unemployed_and_job_hunting",
    "content": "Caroline is unemployed and looking for a new job in counseling.",
    "effective_at": null,
    "evidence": [{{"dia_id": "D3:4", "quote": "I quit my job last month and I'm job hunting now."}}],
    "confidence": 0.95
  }}
]}}
Return {{"memories": []}} when the session contains no extractable memory.
"""


GAP_SYSTEM_PROMPT = f"""You are a meticulous information-extraction engine for a long-term conversational memory system.
You receive a few conversation turns that a first extraction pass did not cover, plus neighbouring turns
for context. Extract only the memories that are grounded in the TARGET turns.

Use exactly the same schema and rules as a full-session extraction:
{MEMORY_TYPES}

Rules recap:
- "subject" is exactly one of the two speakers; "content" is one self-contained English sentence naming
  the subject explicitly.
- "attribute"/"value" are short snake_case keys; they may be null only for type "event".
- "effective_at" is "YYYY-MM-DD" only when unambiguous, otherwise null.
- "evidence" contains 1-3 items with a "dia_id" from the turns shown and a VERBATIM "quote".
- Skip small talk; never invent facts.

OUTPUT FORMAT (JSON object, nothing else):
{{"memories": [{{"subject": "...", "type": "event", "attribute": null, "value": null,
 "content": "...", "effective_at": null,
 "evidence": [{{"dia_id": "D4:2", "quote": "..."}}], "confidence": 0.9}}]}}
"""


def _render_observations(observations: Sequence[Observation], limit: int = 80) -> str:
    if not observations:
        return "(none)"
    lines = []
    for item in observations[:limit]:
        dia = f"[{item.dia_id}] " if item.dia_id else ""
        lines.append(f"- {dia}{item.speaker}: {item.text}")
    return "\n".join(lines)


def build_session_prompt(sample: Sample, session: Session) -> str:
    """整段 session 的抽取请求。"""

    observations = sample.observations.get(session.session_id, [])
    dialogue = "\n".join(turn.render() for turn in session.turns)
    payload = {
        "sample_id": sample.sample_id,
        "speakers": list(sample.speakers),
        "session_id": session.session_id,
        "session_date_time": session.date_time,
        "session_date": session.date_label(),
        "turn_count": len(session.turns),
    }
    return (
        f"SESSION INFO\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        f"ANNOTATED HINTS (human-written notes from the dataset; useful but incomplete, "
        f"never copy a hint that the dialogue does not support)\n{_render_observations(observations)}\n\n"
        f"DIALOGUE\n{dialogue}\n\n"
        f"Extract every durable memory from this session. Answer with the JSON object only."
    )


def build_gap_prompt(sample: Sample, session: Session, targets: Sequence[Turn], context: Sequence[Turn]) -> str:
    """只针对未被覆盖的 turn 做补抽。"""

    payload = {
        "sample_id": sample.sample_id,
        "speakers": list(sample.speakers),
        "session_id": session.session_id,
        "session_date_time": session.date_time,
        "session_date": session.date_label(),
    }
    target_ids = {turn.dia_id for turn in targets}
    target_lines = "\n".join(turn.render() for turn in targets)
    context_lines = "\n".join(
        turn.render() for turn in context if turn.dia_id not in target_ids
    ) or "(none)"
    return (
        f"SESSION INFO\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        f"TARGET TURNS (extract memories grounded in these)\n{target_lines}\n\n"
        f"NEIGHBOURING CONTEXT (read-only, do not extract unless needed to disambiguate a target)\n"
        f"{context_lines}\n\n"
        f"Answer with the JSON object only."
    )
