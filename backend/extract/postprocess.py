"""把 LLM / 规则产出的“原始记忆”规范化成 memory_schema.json 的合法文档。

这里是 A 与 B 的契约边界：输出只包含 schema 允许的字段，且每条 memory 的
evidence 都能回到 LoCoMo 的原始 turn（dia_id 存在、quote 是原文子串）。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

from backend.extract.locomo import (
    Sample,
    Session,
    Turn,
    dia_sort_key,
    resolve_effective_date,
    session_id_from_dia_id,
)
from backend.extract.rules import classify_type, infer_attribute, slug_value

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "APIs" / "memory_schema.json"
MEMORY_TYPES = ("state", "event", "goal", "preference", "requirement")

_WS_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9._]+")
_GENERIC_ATTRIBUTES = {
    "goal",
    "state",
    "event",
    "preference",
    "requirement",
    "thing",
    "fact",
    "information",
    "memory",
    "detail",
    "other",
    "value",
}
_GOAL_LIKE_RE = re.compile(
    r"\b(plans? to|planning to|intends? to|hopes? to|wants? to|would like to|looking forward to)\b",
    re.IGNORECASE,
)
_VALUE_STOPWORDS = {"and", "the", "a", "an", "with", "of", "in", "on", "to", "for", "by", "at"}
_CONTENT_STOPWORDS = _VALUE_STOPWORDS | {
    "is", "are", "was", "were", "has", "have", "had", "its", "his", "her", "their",
    "they", "he", "she", "it", "that", "this", "will", "would", "be", "been", "being",
    "says", "said", "also", "very", "really", "just", "now", "then", "into", "about",
}


@dataclass
class RejectedMemory:
    reason: str
    detail: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizeStats:
    received: int = 0
    accepted: int = 0
    repaired: int = 0
    merged: int = 0
    canonicalized_values: int = 0
    canonicalized_attributes: int = 0
    rejected: list[RejectedMemory] = field(default_factory=list)
    invalid_quotes: int = 0
    invalid_dates: int = 0

    def reject(self, reason: str, detail: str, raw: dict[str, Any]) -> None:
        self.rejected.append(RejectedMemory(reason=reason, detail=detail, raw=raw))

    def as_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self.rejected:
            counts[item.reason] = counts.get(item.reason, 0) + 1
        return {
            "received": self.received,
            "accepted": self.accepted,
            "repaired": self.repaired,
            "merged": self.merged,
            "canonicalized_values": self.canonicalized_values,
            "canonicalized_attributes": self.canonicalized_attributes,
            "rejected": len(self.rejected),
            "rejected_by_reason": counts,
            "invalid_quotes": self.invalid_quotes,
            "invalid_dates": self.invalid_dates,
            "rejected_examples": [
                {"reason": item.reason, "detail": item.detail} for item in self.rejected[:5]
            ],
        }


# --------------------------------------------------------------------------- #
# 基础清洗
# --------------------------------------------------------------------------- #
def clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return _WS_RE.sub(" ", value).strip().strip('"').strip()


def slugify(value: object, *, max_chars: int = 64) -> str | None:
    """``"Searching for Location"`` -> ``"searching_for_location"``。"""

    text = clean_text(value).lower().replace("-", "_").replace(" ", "_")
    text = _SLUG_RE.sub("_", text)
    text = re.sub(r"_+", "_", text).strip("_. ")
    if not text:
        return None
    return text[:max_chars].strip("_")


def _normalize_content(content: str, subject: str) -> str:
    text = clean_text(content)
    if text and text[0].islower() and text.lower().startswith(subject.lower()):
        text = text[0].upper() + text[1:]
    if text and not text.endswith((".", "!", "?")):
        text += "."
    return text


def _coerce_subject(raw_subject: object, sample: Sample) -> str | None:
    subject = clean_text(raw_subject)
    if not subject:
        return None
    if subject in sample.speakers:
        return subject
    lowered = subject.lower()
    for name in sample.speakers:
        if name.lower() == lowered:
            return name
        # "Caroline's kids" / "Melanie and her family" -> 归到发言者
        if name.lower() in lowered:
            return name
    return None


def _valid_date(value: object) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return None


def _normalize_quote(quote: object, turn: Turn) -> str | None:
    """quote 必须是该 turn 原文（或图片描述）的连续子串，否则置空。"""

    text = clean_text(quote)
    if not text:
        return None
    haystacks = [clean_text(turn.text), clean_text(turn.searchable_text)]
    if turn.caption:
        haystacks.append(clean_text(turn.caption))
    for haystack in haystacks:
        if haystack and text.lower() in haystack.lower():
            return text
    return None


# --------------------------------------------------------------------------- #
# 单条记忆规范化
# --------------------------------------------------------------------------- #
def normalize_memory(
    raw: dict[str, Any],
    sample: Sample,
    *,
    default_session: Session | None = None,
    default_confidence: float = 0.85,
    stats: NormalizeStats | None = None,
) -> dict[str, Any] | None:
    """校验并补全一条原始记忆；不合法时返回 None 并记录原因。"""

    stats = stats if stats is not None else NormalizeStats()
    stats.received += 1

    if not isinstance(raw, dict):
        stats.reject("not_an_object", type(raw).__name__, {})
        return None

    subject = _coerce_subject(raw.get("subject"), sample)
    if subject is None:
        stats.reject("bad_subject", str(raw.get("subject"))[:80], raw)
        return None

    content = _normalize_content(clean_text(raw.get("content")), subject)
    if len(content) < 8:
        stats.reject("empty_content", content[:80], raw)
        return None

    memory_type = clean_text(raw.get("type")).lower()
    if memory_type not in MEMORY_TYPES:
        # 模型偶尔把属性名或大写类型塞进 type；用规则从 content 推断，避免整条丢弃
        memory_type = classify_type(content)
        stats.repaired += 1

    # evidence：dia_id 必须真实存在；quote 必须是原文子串
    evidence: list[dict[str, Any]] = []
    seen_evidence: set[tuple[str, str | None]] = set()
    raw_evidence = raw.get("evidence")
    if isinstance(raw_evidence, dict):
        raw_evidence = [raw_evidence]
    for item in raw_evidence or []:
        if not isinstance(item, dict):
            continue
        dia_id = clean_text(item.get("dia_id"))
        if not dia_id:
            continue
        turn = sample.turn(dia_id)
        if turn is None:
            continue
        quote = _normalize_quote(item.get("quote"), turn)
        if quote is None and clean_text(item.get("quote")):
            stats.invalid_quotes += 1
        key = (dia_id, quote)
        if key in seen_evidence:
            continue
        seen_evidence.add(key)
        evidence.append({"session_id": turn.session_id, "dia_id": dia_id, "quote": quote})

    if not evidence:
        stats.reject("no_valid_evidence", content[:80], raw)
        return None

    # time：以 evidence 的第一个 turn 为准，避免 LLM 写错 session
    first_turn = sample.turn(evidence[0]["dia_id"])
    assert first_turn is not None
    session = sample.session(first_turn.session_id) or default_session
    if session is None:
        stats.reject("no_session", first_turn.session_id, raw)
        return None

    raw_effective = raw.get("effective_at")
    if raw_effective is None and isinstance(raw.get("time"), dict):
        raw_effective = raw["time"].get("effective_at")
    effective_at = _valid_date(raw_effective)
    if raw_effective and effective_at is None:
        stats.invalid_dates += 1
    if effective_at is None:
        # 先看 content，再看证据原文："I went there yesterday" 只有在引文里才有时效信息
        candidates = [content, *(clean_text(item.get("quote")) for item in evidence)]
        for candidate in candidates:
            if not candidate:
                continue
            resolved = resolve_effective_date(candidate, session.date)
            if resolved:
                effective_at = resolved.isoformat()
                break

    attribute = slugify(raw.get("attribute"))
    value = slugify(raw.get("value"))

    # 类型自纠错："plans to attend ..." 被标成 event 时归为 goal
    if memory_type == "event" and _GOAL_LIKE_RE.search(content):
        memory_type = "goal"

    # 过泛的属性名对 B 没有区分度，用内容关键词重建
    if attribute in _GENERIC_ATTRIBUTES:
        attribute = infer_attribute(content, memory_type)
        stats.repaired += 1

    if memory_type != "event" and (attribute is None or value is None):
        # 修复而不是丢弃：属性对 B 的状态判断是必需的
        if attribute is None:
            attribute = infer_attribute(content, memory_type)
        if value is None:
            value = slug_value(content, subject)
        stats.repaired += 1

    if memory_type == "event":
        # event 允许 null，但如果模型给了就用（便于同属性事件比较）
        pass

    try:
        confidence = float(raw.get("confidence")) if raw.get("confidence") is not None else default_confidence
    except (TypeError, ValueError):
        confidence = default_confidence
    confidence = max(0.0, min(1.0, confidence))

    stats.accepted += 1
    return {
        "subject": subject,
        "type": memory_type,
        "attribute": attribute,
        "value": value,
        "content": content,
        "time": {
            "session_id": session.session_id,
            "date_time": session.date_time,
            "effective_at": effective_at,
        },
        "evidence": evidence,
        "confidence": round(confidence, 3),
    }


# --------------------------------------------------------------------------- #
# 文档级组装
# --------------------------------------------------------------------------- #
def memory_id_prefix(sample_id: str) -> str:
    """``conv-30`` -> ``mem-conv30``（与 APIs/memory_sechema.md 的示例一致）。"""

    compact = re.sub(r"[^A-Za-z0-9]", "", sample_id).lower()
    return f"mem-{compact}"


def _first_dia(memory: dict[str, Any]) -> tuple[int, int]:
    return dia_sort_key(memory["evidence"][0]["dia_id"])


def _stem(token: str) -> str:
    """极轻量的复数/词形归一，避免 ``owns`` 与 ``own`` 被视为不同值。"""

    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _value_tokens(value: str) -> set[str]:
    return {
        _stem(token)
        for token in re.split(r"[._]", value)
        if token and token not in _VALUE_STOPWORDS
    }


def _content_tokens(content: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9']+", content.lower())
        if token not in _CONTENT_STOPWORDS
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _cluster_mapping(values: Sequence[str], threshold: float) -> dict[str, str]:
    """把高相似度的写法聚成一类，返回 ``{旧写法: 代表写法}``。"""

    counts = Counter(values)
    clusters: list[dict[str, Any]] = []
    # 高频值先当代表，保证最常用的写法胜出
    for value, _ in sorted(counts.items(), key=lambda item: (-item[1], len(item[0]), item[0])):
        tokens = _value_tokens(value)
        for cluster in clusters:
            if _jaccard(tokens, cluster["tokens"]) >= threshold:
                cluster["members"].append(value)
                cluster["tokens"] |= tokens
                break
        else:
            clusters.append({"tokens": set(tokens), "members": [value]})

    mapping: dict[str, str] = {}
    for cluster in clusters:
        representative = max(cluster["members"], key=lambda v: (counts[v], -len(v), v))
        for member in cluster["members"]:
            if member != representative:
                mapping[member] = representative
    return mapping


def canonicalize_attributes(memories: Sequence[dict[str, Any]], threshold: float = 0.5) -> int:
    """同一 subject 下把 ``pets`` / ``pet`` / ``pet_ownership`` 这类属性名归一。"""

    groups: dict[str, list[str]] = {}
    for memory in memories:
        if memory["attribute"]:
            groups.setdefault(memory["subject"], []).append(memory["attribute"])

    mappings = {
        subject: mapping
        for subject, attributes in groups.items()
        if (mapping := _cluster_mapping(attributes, threshold))
    }

    changed = 0
    for memory in memories:
        mapping = mappings.get(memory["subject"])
        if mapping and memory["attribute"] in mapping:
            memory["attribute"] = mapping[memory["attribute"]]
            changed += 1
    return changed


def canonicalize_values(memories: Sequence[dict[str, Any]], threshold: float = 0.75) -> int:
    """同一 (subject, attribute) 下把措辞略有差异的 value 归并到同一个 canonical value。

    这是 LLM 词表归一失败时的安全网：阈值较高，只合并几乎相同的写法，
    避免把 ``starting_a_dance_studio`` 与 ``owns_dance_studio`` 这种不同阶段合到一起。
    """

    groups: dict[tuple[str, str], list[str]] = {}
    for memory in memories:
        if memory["attribute"] and memory["value"]:
            groups.setdefault((memory["subject"], memory["attribute"]), []).append(memory["value"])

    mappings = {
        key: mapping
        for key, values in groups.items()
        if (mapping := _cluster_mapping(values, threshold))
    }

    changed = 0
    for memory in memories:
        mapping = mappings.get((memory["subject"], memory["attribute"]))
        if mapping and memory["value"] in mapping:
            memory["value"] = mapping[memory["value"]]
            changed += 1
    return changed


def _absorb(target: dict[str, Any], duplicate: dict[str, Any], *, max_evidence: int = 8) -> None:
    target["evidence"] = _merge_evidence(target["evidence"], duplicate["evidence"])[:max_evidence]
    target["confidence"] = max(target["confidence"], duplicate["confidence"])
    if target["time"].get("effective_at") is None and duplicate["time"].get("effective_at"):
        target["time"]["effective_at"] = duplicate["time"]["effective_at"]


def _state_changed_between(
    earlier: dict[str, Any],
    later: dict[str, Any],
    timeline: dict[tuple[str, str], list[tuple[tuple[int, int], str | None]]],
) -> bool:
    """A -> B -> A 的情况下，不能把第二个 A 合并进第一个 A。"""

    entries = timeline.get((later["subject"], later["attribute"]), [])
    start, end = _first_dia(earlier), _first_dia(later)
    return any(
        start < dia < end and value != earlier["value"] for dia, value in entries
    )


def merge_same_state(
    memories: Sequence[dict[str, Any]], stats: NormalizeStats
) -> list[dict[str, Any]]:
    """合并 (subject, type, attribute, value) 完全相同的记忆，保留首末证据。"""

    ordered = sorted(memories, key=_first_dia)
    timeline: dict[tuple[str, str], list[tuple[tuple[int, int], str | None]]] = {}
    for memory in ordered:
        if memory["attribute"]:
            timeline.setdefault((memory["subject"], memory["attribute"]), []).append(
                (_first_dia(memory), memory["value"])
            )

    index: dict[tuple[Any, ...], dict[str, Any]] = {}
    result: list[dict[str, Any]] = []
    for memory in ordered:
        if memory["attribute"] is None:
            result.append(memory)
            continue
        key = (memory["subject"], memory["type"], memory["attribute"], memory["value"])
        target = index.get(key)
        if target is not None and not _state_changed_between(target, memory, timeline):
            _absorb(target, memory)
            stats.merged += 1
            continue
        index[key] = memory
        result.append(memory)
    return result


def merge_similar_events(
    memories: Sequence[dict[str, Any]], stats: NormalizeStats, threshold: float = 0.65
) -> list[dict[str, Any]]:
    """同一 session、同一 effective_at 下措辞不同但内容相近的 event 合并。"""

    result: list[dict[str, Any]] = []
    for memory in memories:
        if memory["type"] != "event":
            result.append(memory)
            continue
        tokens = _content_tokens(memory["content"])
        for candidate in result:
            if (
                candidate["type"] == "event"
                and candidate["subject"] == memory["subject"]
                and candidate["time"]["session_id"] == memory["time"]["session_id"]
                and candidate["time"].get("effective_at") == memory["time"].get("effective_at")
                and _jaccard(tokens, _content_tokens(candidate["content"])) >= threshold
            ):
                _absorb(candidate, memory)
                stats.merged += 1
                break
        else:
            result.append(memory)
    return result


def normalize_all(
    sample: Sample,
    raw_memories: Iterable[dict[str, Any]],
    *,
    default_confidence: float = 0.85,
    stats: NormalizeStats | None = None,
) -> list[dict[str, Any]]:
    """把原始记忆逐条规范化（不做跨记忆合并）。"""

    stats = stats if stats is not None else NormalizeStats()
    normalized: list[dict[str, Any]] = []
    for raw in raw_memories:
        memory = normalize_memory(raw, sample, default_confidence=default_confidence, stats=stats)
        if memory is not None:
            normalized.append(memory)
    return normalized


def finalize_document(
    sample: Sample,
    normalized: Sequence[dict[str, Any]],
    *,
    stats: NormalizeStats | None = None,
) -> dict[str, Any]:
    """词表归一 + 去重合并 + 排序 + 分配 memory_id。"""

    stats = stats if stats is not None else NormalizeStats()
    stats.canonicalized_attributes += canonicalize_attributes(normalized)
    stats.canonicalized_values = canonicalize_values(normalized)
    consolidated = merge_same_state(normalized, stats)
    consolidated = merge_similar_events(consolidated, stats)

    ordered = sorted(
        consolidated,
        key=lambda item: (
            _first_dia(item),
            MEMORY_TYPES.index(item["type"]),
            item["attribute"] or "",
        ),
    )

    prefix = memory_id_prefix(sample.sample_id)
    memories: list[dict[str, Any]] = []
    for index, memory in enumerate(ordered, start=1):
        memories.append({"memory_id": f"{prefix}-{index:03d}", **memory})

    return {"sample_id": sample.sample_id, "memories": memories}


def build_document(
    sample: Sample,
    raw_memories: Iterable[dict[str, Any]],
    *,
    default_confidence: float = 0.85,
    stats: NormalizeStats | None = None,
) -> tuple[dict[str, Any], NormalizeStats]:
    """一次性完成规范化与合并（不经过 LLM 词表归一时使用）。"""

    stats = stats if stats is not None else NormalizeStats()
    normalized = normalize_all(
        sample, raw_memories, default_confidence=default_confidence, stats=stats
    )
    document = finalize_document(sample, normalized, stats=stats)
    return document, stats


def _merge_evidence(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {(item["dia_id"], item.get("quote")) for item in left}
    for item in right:
        key = (item["dia_id"], item.get("quote"))
        if key not in seen:
            seen.add(key)
            left.append(item)
    return left


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def load_schema(path: str | None = None) -> dict[str, Any]:
    return json.loads(Path(path or SCHEMA_PATH).read_text(encoding="utf-8"))


def validate_document(document: dict[str, Any], sample: Sample | None = None) -> list[str]:
    """返回错误列表；空列表表示合法。"""

    import jsonschema

    from datetime import datetime

    errors: list[str] = []
    validator = jsonschema.Draft202012Validator(load_schema())
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{location}: {error.message}")

    # 额外的一致性检查（schema 表达不了的约束）
    seen_ids: set[str] = set()
    for index, memory in enumerate(document.get("memories", [])):
        where = f"memories[{index}]"
        memory_id = memory.get("memory_id")
        if memory_id in seen_ids:
            errors.append(f"{where}: duplicate memory_id {memory_id!r}")
        seen_ids.add(memory_id)

        effective_at = memory.get("time", {}).get("effective_at")
        if effective_at:
            try:
                datetime.strptime(effective_at, "%Y-%m-%d")
            except ValueError:
                errors.append(f"{where}: effective_at is not a valid date: {effective_at!r}")

        if sample is not None:
            for evidence in memory.get("evidence", []):
                dia_id = evidence.get("dia_id")
                if sample.turn(dia_id) is None:
                    errors.append(f"{where}: evidence dia_id {dia_id!r} not found in sample")
                elif evidence.get("session_id") != session_id_from_dia_id(dia_id):
                    errors.append(f"{where}: evidence session_id does not match dia_id {dia_id!r}")
    return errors
