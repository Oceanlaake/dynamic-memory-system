"""从 LoCoMo 的 qa 与 Memory JSON 自动生成 Recall@K 用例。

映射规则：一条 Memory 的 evidence[].dia_id 命中该题 qa.evidence 中任一 turn，
这条 Memory 就算“答案所需”。一条 Memory 常引用多个 turn，任一命中即可。

用法：
    python -m evaluation.build_cases
    python -m evaluation.build_cases --out evaluation/cases/generated.json
    python -m evaluation.build_cases --include-categories 1,2,3,4
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.schemas import Memory
from backend.store import DEFAULT_MEMORY_DIR, MemoryStore

DEFAULT_RAW = Path("data/raw/locomo10.json")
DEFAULT_OUT = Path("evaluation/cases/generated.json")


def parse_evidence(items: object) -> list[str]:
    """qa.evidence 可能写作 ["D1:2", "D9:17"]，也可能挤在一格里 "D8:6; D9:17"。"""
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


def index_memories(memories: list[Memory]) -> dict[str, list[str]]:
    """dia_id -> 引用该 turn 的 memory_id 列表。"""
    index: dict[str, list[str]] = {}
    for memory in memories:
        for evidence in memory.evidence:
            index.setdefault(evidence.dia_id, []).append(memory.memory_id)
    return index


def build_cases(
    samples: list[dict],
    memories_by_sample: dict[str, list[Memory]],
    include_categories: set[int] | None = None,
) -> tuple[list[dict], dict]:
    cases: list[dict] = []
    stats = {"samples": 0, "qa_total": 0, "cases": 0, "skipped_category": 0, "skipped_no_memory": 0}
    skipped_examples: list[dict] = []

    for sample in samples:
        sample_id = sample.get("sample_id")
        memories = memories_by_sample.get(sample_id)
        if not memories:
            continue
        stats["samples"] += 1
        index = index_memories(memories)

        for qa in sample.get("qa", []):
            stats["qa_total"] += 1
            category = qa.get("category")
            if include_categories is not None and category not in include_categories:
                stats["skipped_category"] += 1
                continue

            evidence = parse_evidence(qa.get("evidence"))
            required = sorted({memory_id for dia_id in evidence for memory_id in index.get(dia_id, [])})
            if not required:
                stats["skipped_no_memory"] += 1
                if len(skipped_examples) < 5:
                    skipped_examples.append(
                        {"sample_id": sample_id, "question": qa.get("question"), "evidence": evidence}
                    )
                continue

            cases.append(
                {
                    "sample_id": sample_id,
                    "question": qa["question"],
                    "required_memory_ids": required,
                    "answer": qa.get("answer"),
                    "category": category,
                    "evidence": evidence,
                }
            )
            stats["cases"] += 1

    stats["skipped_examples"] = skipped_examples
    return cases, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--memory-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--include-categories",
        default="1,2,3,4",
        help="逗号分隔；默认排除 5（对抗题，本身不要求召回）",
    )
    args = parser.parse_args()

    categories = {int(value) for value in args.include_categories.split(",") if value.strip()}

    store = MemoryStore(args.memory_dir or DEFAULT_MEMORY_DIR)
    memories_by_sample = {sample_id: store.memories(sample_id) or [] for sample_id in store.sample_ids()}
    raw = json.loads(args.raw.read_text(encoding="utf-8"))

    cases, stats = build_cases(raw, memories_by_sample, categories)
    if not cases:
        raise SystemExit(
            "没有生成任何用例：请确认 data/memories/ 里的 sample_id 与 locomo10.json 一致，"
            "且 Memory 的 evidence 覆盖了 qa.evidence 中的 turn。"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "description": "由 evaluation/build_cases.py 自动生成，勿手改。",
        "source_raw": str(args.raw),
        "memory_dir": str(args.memory_dir or DEFAULT_MEMORY_DIR),
        "include_categories": sorted(categories),
        "stats": stats,
        "cases": cases,
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"samples={stats['samples']} qa_total={stats['qa_total']} cases={stats['cases']} "
        f"skipped_category={stats['skipped_category']} skipped_no_memory={stats['skipped_no_memory']}"
    )
    print(f"written: {args.out}")


if __name__ == "__main__":
    main()
