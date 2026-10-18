"""LoCoMo 原始数据的解析与规范化。

原始文件 ``data/raw/locomo10.json`` 的结构：

```
[
  {
    "sample_id": "conv-26",
    "conversation": {
      "speaker_a": "Caroline",
      "speaker_b": "Melanie",
      "session_1_date_time": "1:56 pm on 8 May, 2023",
      "session_1": [{"speaker": "...", "dia_id": "D1:1", "text": "..."}, ...],
      ...
    },
    "observation": {"session_1_observation": {"Caroline": [["...", "D1:3"], ...]}},
    "session_summary": {...},
    "event_summary": {...},
    "qa": [{"question": "...", "answer": "...", "evidence": ["D1:3"], "category": 2}]
  },
  ...
]
```

本模块只做“读 + 规范化”，不做任何抽取判断，方便单独测试。
"""

from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

SESSION_KEY_RE = re.compile(r"^session_(\d+)$")
DIA_ID_RE = re.compile(r"^D(\d+):(\d+)$")
DATE_RE = re.compile(
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<ampm>am|pm)\s+on\s+"
    r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+),?\s*(?P<year>\d{4})",
    re.IGNORECASE,
)
MONTHS = {name.lower(): index for index, name in enumerate(calendar.month_name) if name}

DEFAULT_RAW_PATH = Path("data/raw/locomo10.json")


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Turn:
    """一轮对话（LoCoMo 的一个 ``dia_id``）。"""

    session_id: str
    dia_id: str
    speaker: str
    text: str
    caption: str | None = None
    order: int = 0

    @property
    def searchable_text(self) -> str:
        """用于校验 evidence quote 的全文（对话正文 + 图片描述）。"""

        if self.caption:
            return f"{self.text} {self.caption}"
        return self.text

    def render(self) -> str:
        """给 LLM 看的单行表示。"""

        line = f"{self.dia_id} {self.speaker}: {self.text}"
        if self.caption:
            line += f" [shared image: {self.caption}]"
        return line


@dataclass
class Session:
    """一段 session。部分 session 只有日期没有对话内容（例如 conv-26 的 D21+）。"""

    session_id: str
    index: int
    date_time: str | None
    date: date | None
    turns: list[Turn] = field(default_factory=list)

    @property
    def has_turns(self) -> bool:
        return bool(self.turns)

    def date_label(self) -> str:
        if self.date:
            return self.date.isoformat()
        return "unknown"


@dataclass
class Observation:
    """LoCoMo 自带的人工标注 observation（一条 = 一句事实 + 出处）。"""

    session_id: str
    speaker: str
    text: str
    dia_id: str | None


@dataclass
class Sample:
    sample_id: str
    speakers: tuple[str, ...]
    sessions: list[Session]
    observations: dict[str, list[Observation]]
    qa: list[dict[str, Any]]
    raw: dict[str, Any] = field(default_factory=dict)

    def session(self, session_id: str) -> Session | None:
        for item in self.sessions:
            if item.session_id == session_id:
                return item
        return None

    def turn(self, dia_id: str) -> Turn | None:
        for session in self.sessions:
            for turn in session.turns:
                if turn.dia_id == dia_id:
                    return turn
        return None

    def dialogue_sessions(self) -> list[Session]:
        return [session for session in self.sessions if session.has_turns]

    def all_turns(self) -> list[Turn]:
        return [turn for session in self.sessions for turn in session.turns]

    def observation_index(self) -> dict[str, list[Observation]]:
        """dia_id -> 该 turn 上的人工标注。"""

        index: dict[str, list[Observation]] = {}
        for items in self.observations.values():
            for item in items:
                if item.dia_id:
                    index.setdefault(item.dia_id, []).append(item)
        return index

    def qa_evidence_dia_ids(self) -> list[str]:
        """所有 QA 标注的 evidence turn（去重、保序）。"""

        seen: dict[str, None] = {}
        for qa in self.qa:
            for dia_id in parse_evidence(qa.get("evidence")):
                if self.turn(dia_id) is not None:
                    seen.setdefault(dia_id, None)
        return list(seen)


# --------------------------------------------------------------------------- #
# 解析工具
# --------------------------------------------------------------------------- #
def parse_session_date(value: object) -> date | None:
    """解析 ``"1:56 pm on 8 May, 2023"`` 形式的 session 时间。"""

    if not isinstance(value, str):
        return None
    match = DATE_RE.search(value)
    if not match:
        return None
    month = MONTHS.get(match.group("month").lower())
    if month is None:
        return None
    try:
        return date(int(match.group("year")), month, int(match.group("day")))
    except ValueError:
        return None


def session_id_from_dia_id(dia_id: str) -> str | None:
    """``"D3:12"`` -> ``"session_3"``。"""

    match = DIA_ID_RE.match(dia_id.strip())
    if not match:
        return None
    return f"session_{int(match.group(1))}"


def dia_sort_key(dia_id: str) -> tuple[int, int]:
    match = DIA_ID_RE.match(dia_id.strip())
    if not match:
        return (10**6, 10**6)
    return (int(match.group(1)), int(match.group(2)))


def parse_evidence(items: object) -> list[str]:
    """QA evidence 可能写作 ``["D1:2", "D9:17"]``，也可能挤在一格里 ``"D8:6; D9:17"``。"""

    if not items:
        return []
    if isinstance(items, str):
        items = [items]
    dia_ids: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        for part in item.replace(",", ";").split(";"):
            cleaned = part.strip()
            if cleaned:
                dia_ids.append(cleaned)
    return dia_ids


def _normalise_observation_entries(raw: object) -> list[Observation]:
    """兼容 observation 可能出现的几种写法。"""

    results: list[Observation] = []
    if isinstance(raw, dict):
        for speaker, entries in raw.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                text: str | None = None
                dia_id: str | None = None
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    text = str(entry[0]).strip()
                    dia_id = str(entry[1]).strip() or None
                elif isinstance(entry, dict):
                    text = str(entry.get("text") or entry.get("observation") or "").strip()
                    dia_id = str(entry.get("dia_id") or "").strip() or None
                elif isinstance(entry, str):
                    text = entry.strip()
                if text:
                    results.append(
                        Observation(
                            session_id="",
                            speaker=str(speaker),
                            text=text,
                            dia_id=dia_id,
                        )
                    )
    return results


def normalize_sample(raw: dict[str, Any]) -> Sample:
    """把一条原始 LoCoMo 样本规范化为 :class:`Sample`。"""

    sample_id = str(raw.get("sample_id") or "").strip()
    if not sample_id:
        raise ValueError("LoCoMo sample is missing sample_id")

    conversation = raw.get("conversation") or {}
    speakers = tuple(
        str(name).strip()
        for name in (conversation.get("speaker_a"), conversation.get("speaker_b"))
        if name
    )

    session_indexes = sorted(
        int(match.group(1))
        for key in conversation
        if (match := SESSION_KEY_RE.match(key))
    )

    sessions: list[Session] = []
    for index in session_indexes:
        session_id = f"session_{index}"
        date_time = conversation.get(f"{session_id}_date_time")
        date_time = str(date_time).strip() if isinstance(date_time, str) else None
        turns: list[Turn] = []
        for order, item in enumerate(conversation.get(session_id) or []):
            if not isinstance(item, dict):
                continue
            dia_id = str(item.get("dia_id") or "").strip()
            if not dia_id:
                continue
            text = str(item.get("text") or "").strip()
            caption_raw = item.get("blip_caption")
            caption = str(caption_raw).strip() if isinstance(caption_raw, str) and caption_raw.strip() else None
            if not text and not caption:
                continue
            turns.append(
                Turn(
                    session_id=session_id,
                    dia_id=dia_id,
                    speaker=str(item.get("speaker") or "").strip(),
                    text=text,
                    caption=caption,
                    order=order,
                )
            )
        sessions.append(
            Session(
                session_id=session_id,
                index=index,
                date_time=date_time,
                date=parse_session_date(date_time),
                turns=turns,
            )
        )

    observations: dict[str, list[Observation]] = {}
    for key, value in (raw.get("observation") or {}).items():
        match = re.match(r"^session_(\d+)_observation$", key)
        if not match:
            continue
        session_id = f"session_{int(match.group(1))}"
        items = _normalise_observation_entries(value)
        for item in items:
            item.session_id = session_id
        if items:
            observations[session_id] = items

    qa = [item for item in (raw.get("qa") or []) if isinstance(item, dict)]

    return Sample(
        sample_id=sample_id,
        speakers=speakers,
        sessions=sessions,
        observations=observations,
        qa=qa,
        raw=raw,
    )


def load_dataset(path: Path | str = DEFAULT_RAW_PATH) -> list[Sample]:
    """读取 LoCoMo 原始文件并返回规范化的样本列表。"""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("samples") or raw.get("data") or [raw]
    if not isinstance(raw, list):
        raise ValueError(f"Unsupported LoCoMo layout in {path}")
    return [normalize_sample(item) for item in raw if isinstance(item, dict)]


def load_sample(path: Path | str, sample_id: str) -> Sample:
    for sample in load_dataset(path):
        if sample.sample_id == sample_id:
            return sample
    raise KeyError(f"sample {sample_id!r} not found in {path}")


# --------------------------------------------------------------------------- #
# 相对时间解析（供规则抽取与后处理使用；LLM 也会自行给出 effective_at）
# --------------------------------------------------------------------------- #
_RELATIVE_DAY_WORDS = {
    "yesterday": -1,
    "today": 0,
    "tomorrow": 1,
    "the day before": -1,
    "the day after": 1,
}
_WEEKDAYS = {name.lower(): index for index, name in enumerate(calendar.day_name)}


def resolve_effective_date(text: str, session_date: date | None) -> date | None:
    """从一句话里解出 ``effective_at``；无法可靠解析时返回 None。

    只处理可以确定的表达：绝对日期、昨天/今天/明天、上周几。
    "last month"、"a few years ago" 这类模糊表达不猜测。
    """

    if session_date is None:
        return None
    lowered = text.lower()

    absolute = re.search(
        r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+),?\s*(?P<year>\d{4})", text
    )
    if absolute:
        month = MONTHS.get(absolute.group("month").lower())
        if month:
            try:
                return date(int(absolute.group("year")), month, int(absolute.group("day")))
            except ValueError:
                return None

    for phrase, offset in _RELATIVE_DAY_WORDS.items():
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            return session_date + timedelta(days=offset)

    weekday = re.search(r"\b(?:last|previous)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lowered)
    if weekday:
        target = _WEEKDAYS[weekday.group(1)]
        delta = (session_date.weekday() - target) % 7
        delta = delta or 7
        return session_date - timedelta(days=delta)

    return None


def iter_session_chunks(turns: Iterable[Turn], size: int) -> Iterable[list[Turn]]:
    """按固定长度切分 turn，用于 gap-fill 时控制单次请求大小。"""

    chunk: list[Turn] = []
    for turn in turns:
        chunk.append(turn)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
