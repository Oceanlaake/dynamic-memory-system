"""检索排序指标。"""

from __future__ import annotations

from typing import Sequence


def rank_metrics(ranking: Sequence[str], required: Sequence[str], ks: Sequence[int]) -> dict:
    """ranking 为按相关度降序的 memory_id 列表，required 为答案所需的 memory_id。"""
    required_set = set(required)
    if not required_set:
        raise ValueError("required must not be empty")

    recall = {k: len(required_set & set(ranking[:k])) / len(required_set) for k in ks}
    first_hit = next(
        (index for index, memory_id in enumerate(ranking, start=1) if memory_id in required_set),
        None,
    )
    return {"recall": recall, "mrr": 1.0 / first_hit if first_hit else 0.0}


def macro_average(rows: Sequence[dict], ks: Sequence[int]) -> dict:
    if not rows:
        raise ValueError("rows must not be empty")
    return {
        "recall": {k: sum(row["recall"][k] for row in rows) / len(rows) for k in ks},
        "mrr": sum(row["mrr"] for row in rows) / len(rows),
    }
