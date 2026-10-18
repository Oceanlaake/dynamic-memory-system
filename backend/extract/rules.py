"""离线规则抽取（无 API key / 单测时使用）。

数据来源是 LoCoMo 自带的人工标注 ``observation``：每条 observation 已经是
“一句话事实 + 出处 turn”，因此非常适合作为确定性基线。规则只负责：

1. 判断 memory type；
2. 生成稳定的 snake_case ``attribute`` / ``value``；
3. 解析可确定的 ``effective_at``。

它不追求覆盖全部对话，追求的是“零依赖、可复现、schema 合法”，
LLM 模式才是正式产出。
"""

from __future__ import annotations

import re
from typing import Any

from backend.extract.locomo import Observation, Sample, Session, Turn, resolve_effective_date

_TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "goal",
        (
            "planning to", "plans to", "plan to", "is going to", "wants to", "want to",
            "hopes to", "hope to", "intends to", "aims to", "looking forward to",
            "dreams of", "thinking about", "will start", "will open", "will begin",
        ),
    ),
    (
        "preference",
        (
            "favorite", "favourite", "loves", "love to", "likes", "like to", "enjoys",
            "enjoy", "prefers", "interested in", "fan of", "hates", "dislikes",
            "passionate about", "good at", "proud of",
        ),
    ),
    (
        "requirement",
        (
            "needs to", "need to", "has to", "have to", "must ", "requires", "required to",
            "needs a", "needs more", "needs help",
        ),
    ),
    (
        "event",
        (
            "attended", "went to", "visited", "took ", "ran a", "joined", "painted",
            "started", "bought", "moved to", "celebrated", "competed", "hosted",
            "organized", "met with", "met up", "gave a", "spoke at", "cooked",
            "traveled", "travelled", "registered", "signed up", "finished", "graduated",
            "adopted", "performed", "won ", "lost ", "quit", "began", "took part",
            "shared a", "went on", "flew to", "drove to", "volunteered",
        ),
    ),
)

_PAST_TENSE_RE = re.compile(
    r"\b(got|went|saw|made|took|gave|ran|won|lost|met|bought|ate|drank|wrote|read|started|"
    r"joined|attended|visited|painted|moved|finished|graduated|adopted|performed|registered|"
    r"signed|celebrated|cooked|traveled|travelled|volunteered|quit|began|spoke|shared|hosted|"
    r"organized|competed|flew|drove)\b"
)

_ATTRIBUTE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("employment_status", ("job", "work", "career", "employ", "business", "company", "banker", "colleague", "boss", "interview", "office")),
    ("education", ("school", "study", "college", "university", "degree", "course", "class", "learn", "certification", "research", "student")),
    ("residence", ("live", "lives", "moved", "city", "apartment", "house", "hometown", "neighborhood", "country", "sweden", "moved from")),
    ("family", ("kid", "kids", "child", "children", "son", "daughter", "family", "husband", "wife", "partner", "mother", "father", "brother", "sister", "parent", "grandma", "grandpa")),
    ("relationships", ("friend", "friends", "relationship", "dating", "married", "single", "divorce", "mentor", "community", "support group")),
    ("health", ("health", "doctor", "therapy", "therapist", "anxiety", "depression", "sick", "injury", "fitness", "exercise", "recovery", "mental")),
    ("hobby", ("paint", "pottery", "camp", "swim", "run", "dance", "book", "read", "cook", "music", "violin", "guitar", "hike", "yoga", "garden", "travel", "photograph", "write", "writing", "charity race", "museum")),
    ("identity", ("transgender", "lgbtq", "identity", "religion", "religious", "culture", "immigrant", "activist")),
    ("finance", ("money", "finance", "financial", "invest", "loan", "budget", "debt", "salary", "cost", "fund")),
    ("pets", ("dog", "cat", "pet", "puppy", "kitten")),
    ("future_plan", ("plan", "planning", "goal", "hope", "dream", "future")),
)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "at", "for", "with",
    "from", "by", "as", "is", "are", "was", "were", "be", "been", "being", "has", "have",
    "had", "do", "does", "did", "will", "would", "can", "could", "should", "she", "he",
    "they", "it", "her", "his", "their", "them", "this", "that", "these", "those",
    "very", "really", "also", "just", "now", "then", "her", "him", "s", "t",
}


def classify_type(text: str) -> str:
    """按关键词给一句话归类；顺序保证“计划/偏好”优先于“事件”。"""

    lowered = f" {text.lower().strip()} "
    for memory_type, keywords in _TYPE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return memory_type
    if _PAST_TENSE_RE.search(lowered):
        return "event"
    return "state"


def infer_attribute(text: str, memory_type: str) -> str:
    if memory_type == "event":
        return "life_event"
    lowered = text.lower()
    for attribute, keywords in _ATTRIBUTE_RULES:
        if any(keyword in lowered for keyword in keywords):
            return attribute
    if memory_type == "goal":
        return "future_plan"
    if memory_type == "preference":
        return "personal_preference"
    if memory_type == "requirement":
        return "personal_requirement"
    if memory_type == "event":
        return "life_event"
    return "general_state"


def slug_value(text: str, subject: str, *, max_words: int = 5, max_chars: int = 48) -> str:
    """从句子生成一个稳定、可比较的 value。"""

    cleaned = re.sub(r"[^A-Za-z0-9\s']", " ", text)
    words = [word for word in cleaned.split() if word]
    result: list[str] = []
    for word in words:
        lowered = word.lower().strip("'")
        if not lowered or lowered in _STOPWORDS:
            continue
        if lowered == subject.lower():
            continue
        result.append(lowered)
        if len(result) >= max_words:
            break
    slug = "_".join(result)[:max_chars].strip("_")
    return slug or "unspecified"


def _ensure_sentence(text: str, subject: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return cleaned
    if cleaned[0].islower() and cleaned.lower().startswith(subject.lower()):
        cleaned = cleaned[0].upper() + cleaned[1:]
    if not cleaned.endswith((".", "!", "?")):
        cleaned += "."
    return cleaned


def _resolve_subject(observation: Observation, sample: Sample) -> str | None:
    speaker = observation.speaker.strip()
    if speaker in sample.speakers:
        return speaker
    for name in sample.speakers:
        if name and name.lower() in observation.text.lower():
            return name
    return None


def _observation_to_raw(
    observation: Observation,
    sample: Sample,
    session: Session,
    turn: Turn,
) -> dict[str, Any] | None:
    subject = _resolve_subject(observation, sample)
    if subject is None:
        return None
    memory_type = classify_type(observation.text)
    attribute = infer_attribute(observation.text, memory_type)
    return {
        "subject": subject,
        "type": memory_type,
        "attribute": attribute,
        "value": slug_value(observation.text, subject),
        "content": _ensure_sentence(observation.text, subject),
        "effective_at": (
            resolve_effective_date(observation.text, session.date).isoformat()
            if resolve_effective_date(observation.text, session.date)
            else None
        ),
        "evidence": [{"dia_id": turn.dia_id, "quote": turn.text or turn.caption}],
        "confidence": 0.75,
    }


def extract_session_rules(sample: Sample, session: Session) -> list[dict[str, Any]]:
    """用 observation 标注生成该 session 的原始 memory 列表。"""

    turns = {turn.dia_id: turn for turn in session.turns}
    raw_memories: list[dict[str, Any]] = []
    for observation in sample.observations.get(session.session_id, []):
        if not observation.dia_id:
            continue
        turn = turns.get(observation.dia_id)
        if turn is None:
            continue
        memory = _observation_to_raw(observation, sample, session, turn)
        if memory is not None:
            raw_memories.append(memory)
    return raw_memories
