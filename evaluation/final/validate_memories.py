"""Validate the frozen final-test memories for the six self-defined segments.

Checks schema loading, memory-id uniqueness, evidence linkage to raw turns,
and reports empty attributes / missing time fields / evidence coverage.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.schemas import Memory


def raw_turns(raw_samples: list[dict]) -> dict[str, set[tuple[str, str]]]:
    turns: dict[str, set[tuple[str, str]]] = {}
    for sample in raw_samples:
        sample_id = sample.get("sample_id")
        conversation = sample.get("conversation")
        found: set[tuple[str, str]] = set()
        if isinstance(conversation, dict):
            for key, value in conversation.items():
                if not isinstance(value, list):
                    continue
                for turn in value:
                    if isinstance(turn, dict) and turn.get("dia_id"):
                        found.add((key, turn["dia_id"]))
        turns[sample_id] = found
    return turns


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-dir", type=Path, default=Path("outputs/final-test-v1/memories"))
    parser.add_argument("--raw", type=Path, default=Path("data/raw/locomo10.json"))
    parser.add_argument("--json-out", type=Path, required=True)
    args = parser.parse_args()

    raw_samples = json.loads(args.raw.read_text(encoding="utf-8"))
    turns_by_sample = raw_turns(raw_samples)
    report: dict = {"memory_dir": str(args.memory_dir), "samples": []}
    totals = {
        "memory_count": 0, "unique_memory_ids": 0, "missing_evidence_refs": 0,
        "empty_attribute": 0, "missing_time": 0, "evidence_refs": 0,
    }

    for path in sorted(args.memory_dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        sample_id = document["sample_id"]
        memories = [Memory.model_validate(item) for item in document["memories"]]
        known_turns = turns_by_sample.get(sample_id, set())
        row = {
            "sample_id": sample_id,
            "memory_count": len(memories),
            "unique_memory_ids": len({memory.memory_id for memory in memories}),
            "missing_evidence_refs": 0,
            "empty_attribute": 0,
            "missing_time": 0,
            "evidence_refs": 0,
        }
        for memory in memories:
            row["evidence_refs"] += len(memory.evidence)
            if not memory.attribute:
                row["empty_attribute"] += 1
            if not memory.time.date_time and not memory.time.effective_at:
                row["missing_time"] += 1
            for ref in memory.evidence:
                if (ref.session_id, ref.dia_id) not in known_turns:
                    row["missing_evidence_refs"] += 1
        report["samples"].append(row)
        for key in ("memory_count", "unique_memory_ids", "missing_evidence_refs",
                    "empty_attribute", "missing_time", "evidence_refs"):
            totals[key] += row[key]

    report["totals"] = totals
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"totals": totals, "per_sample": report["samples"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
