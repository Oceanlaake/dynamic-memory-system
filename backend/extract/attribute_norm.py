"""词表归一（每个样本一次 LLM 调用）。

逐 session 抽取时，模型看不到其它 session 已经用过的 ``attribute`` / ``value``，于是同一个
维度会出现 ``plan`` / ``travel_plan`` / ``future_plan``，同一个状态会出现
``owns_dance_studio`` / ``runs_dance_studio``。

B 的状态解析按 ``(subject, attribute)`` 对齐，属性名不一致会直接漏掉 SUPERSEDE / RETAIN，
所以这里在每个样本抽取完成后做一次属性词表对齐。

不在此处自动合并 ``value``：同一状态的不同措辞（``owns_dance_studio`` /
``runs_dance_studio``）由 B 的关系判断负责，而一次误合并（``starting_a_dance_studio`` 并到
``dance_studio``）反而会掩盖真实的状态变化。value 只保留“儿乎相同写法”的高阈值安全网。

所有映射都要经过严格校验（必须出现在输入里、必须是合法 snake_case、不允许链式映射），
模型输出格式错误时整条映射被忽略，原始数据保持不变。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Sequence

from backend.extract.llm import ExtractionClient, ExtractionError
from backend.extract.locomo import Sample

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)?$")

SYSTEM_PROMPT = """You normalise the attribute vocabulary of a structured memory store.

You receive, for each person, the attribute names that were produced independently while reading
different conversation sessions. The same dimension of the same person is sometimes named differently
("pets" / "pet" / "pet_ownership", "plan" / "travel_plan").

TASK: group attribute names that describe the SAME dimension of the SAME person.

HARD RULES
- Never merge across different people or different topics.
  "attitude_toward_sports" and "attitude_toward_work" stay separate;
  "favorite_genre" and "favorite_author" stay separate.
- Never merge a dimension with a different dimension that merely shares a word.
- Canonical names: lowercase snake_case, at most three underscore-separated words, optionally one dot
  for a namespace ("pet_ownership.vaccination"). Prefer the most frequent existing spelling.
- Omit any name that needs no change. When unsure, omit it.

OUTPUT (JSON object, nothing else):
{"attributes": {"<person>": {"old_attribute": "canonical_attribute"}}}
Return {"attributes": {}} when nothing should change."""


def build_prompt(sample: Sample, attributes: dict[str, list[str]]) -> str:
    payload = {
        "speakers": list(sample.speakers),
        "attributes": attributes,
    }
    return (
        "Normalise the attribute names below.\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\nAnswer with the JSON object only."
    )


def collect_vocabulary(
    memories: Sequence[dict[str, Any]],
) -> dict[str, list[str]]:
    """按 subject 汇总出现过的 attribute（按频次排序）。"""

    counts: dict[str, dict[str, int]] = {}
    for memory in memories:
        attribute = memory.get("attribute")
        if not attribute:
            continue
        bucket = counts.setdefault(memory["subject"], {})
        bucket[attribute] = bucket.get(attribute, 0) + 1

    return {
        subject: [name for name, _ in sorted(items.items(), key=lambda kv: (-kv[1], kv[0]))]
        for subject, items in counts.items()
    }


def _valid_canonical(value: object, original: str) -> str | None:
    if not isinstance(value, str):
        return None
    canonical = value.strip().lower()
    if canonical == original or not _SLUG_RE.match(canonical) or len(canonical) > 64:
        return None
    return canonical


def _apply_attributes(
    memories: list[dict[str, Any]],
    raw_attributes: object,
    known: dict[str, list[str]],
) -> int:
    if not isinstance(raw_attributes, dict):
        return 0
    applied = 0
    for subject, mapping in raw_attributes.items():
        if subject not in known or not isinstance(mapping, dict):
            continue
        allowed = set(known[subject])
        for old, new in mapping.items():
            if old not in allowed:
                continue
            canonical = _valid_canonical(new, old)
            if canonical is None or canonical in mapping:
                continue  # 跳过非法值与链式映射
            for memory in memories:
                if memory["subject"] == subject and memory.get("attribute") == old:
                    memory["attribute"] = canonical
                    applied += 1
    return applied


def normalize_vocabulary(
    sample: Sample,
    memories: list[dict[str, Any]],
    client: ExtractionClient,
    *,
    max_attributes_per_subject: int = 200,
) -> tuple[dict[str, int], str | None]:
    """就地归一 ``memories`` 的 ``attribute``；返回 (改动统计, 错误信息)。"""

    attributes = collect_vocabulary(memories)
    if not attributes:
        return {"attributes": 0}, None

    attributes = {
        subject: names[:max_attributes_per_subject] for subject, names in attributes.items()
    }

    try:
        payload = client.extract_json(SYSTEM_PROMPT, build_prompt(sample, attributes))
    except ExtractionError as exc:
        return {"attributes": 0}, f"vocabulary normalization failed: {exc}"

    if not isinstance(payload, dict):
        return {"attributes": 0}, "vocabulary normalization returned a non-object"

    attribute_changes = _apply_attributes(memories, payload.get("attributes"), attributes)
    return {"attributes": attribute_changes}, None
