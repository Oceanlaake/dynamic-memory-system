#!/usr/bin/env python3
"""Build a tiny, deterministic LoCoMo -> Memory JSON demonstration.

The memories in this file are intentionally hand-curated. The script copies
selected real turns from LoCoMo, checks every evidence ID, and materializes two
easy-to-present JSON files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SAMPLE_ID = "conv-30"
QA_QUESTION = "How long did it take for Jon to open his studio?"
SELECTED_TURNS = {
    "session_1": ["D1:2", "D1:4", "D1:6", "D1:8"],
    "session_15": ["D15:3", "D15:5", "D15:6", "D15:13"],
    "session_18": ["D18:1", "D18:2", "D18:8", "D18:10"],
}

# This is the deliberately manual part of the demo. Each source ref is checked
# against the raw data below, so a memory can always be traced back to a turn.
MEMORIES: list[dict[str, Any]] = [
    {
        "memory_id": "mem-conv30-001",
        "subject": "Jon",
        "type": "event",
        "attribute": "employment_event",
        "value": "lost_banking_job",
        "content": "Jon lost his job as a banker on 19 January 2023.",
        "status": "historical",
        "confidence": 0.99,
        "time": {"resolved_date": "2023-01-19", "basis": "session time minus one day"},
        "source_refs": [{"session_id": "session_1", "dia_id": "D1:2"}],
    },
    {
        "memory_id": "mem-conv30-002",
        "subject": "Jon",
        "type": "goal",
        "attribute": "dance_studio.lifecycle_stage",
        "value": "planned",
        "content": "Jon plans to open a dance studio to share his lifelong passion for dance with others.",
        "status": "superseded",
        "confidence": 0.99,
        "source_refs": [
            {"session_id": "session_1", "dia_id": "D1:4"},
            {"session_id": "session_1", "dia_id": "D1:6"},
        ],
    },
    {
        "memory_id": "mem-conv30-003",
        "subject": "Jon",
        "type": "preference",
        "attribute": "favorite_dance_style",
        "value": "contemporary",
        "content": "Jon's favorite dance style is contemporary dance.",
        "status": "current",
        "confidence": 0.99,
        "source_refs": [{"session_id": "session_1", "dia_id": "D1:8"}],
    },
    {
        "memory_id": "mem-conv30-004",
        "subject": "Jon",
        "type": "event",
        "attribute": "dance_studio.lifecycle_stage",
        "value": "opening_scheduled",
        "content": "Jon scheduled the official opening of his dance studio for 20 June 2023.",
        "status": "historical",
        "confidence": 0.99,
        "time": {"resolved_date": "2023-06-20", "basis": "tomorrow relative to session time"},
        "source_refs": [
            {"session_id": "session_15", "dia_id": "D15:3"},
            {"session_id": "session_15", "dia_id": "D15:5"},
            {"session_id": "session_15", "dia_id": "D15:6"},
            {"session_id": "session_15", "dia_id": "D15:13"},
        ],
    },
    {
        "memory_id": "mem-conv30-005",
        "subject": "Jon",
        "type": "state",
        "attribute": "dance_studio.business_health",
        "value": "financially_tenuous",
        "content": "Jon's dance studio is on tenuous financial ground; he took a temporary job, is seeking investors, and is revising his business plan and investor pitch.",
        "status": "current",
        "confidence": 0.99,
        "source_refs": [
            {"session_id": "session_18", "dia_id": "D18:2"},
            {"session_id": "session_18", "dia_id": "D18:8"},
            {"session_id": "session_18", "dia_id": "D18:10"},
        ],
    },
]


def load_sample(raw_path: Path) -> dict[str, Any]:
    with raw_path.open(encoding="utf-8") as file:
        dataset = json.load(file)
    try:
        return next(item for item in dataset if item.get("sample_id") == SAMPLE_ID)
    except StopIteration as exc:
        raise ValueError(f"Sample {SAMPLE_ID!r} was not found in {raw_path}") from exc


def build_demo(sample: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    conversation = sample["conversation"]
    turn_index: dict[tuple[str, str], dict[str, Any]] = {}
    sessions = []

    for session_id, selected_ids in SELECTED_TURNS.items():
        raw_turns = conversation[session_id]
        raw_by_id = {turn["dia_id"]: turn for turn in raw_turns}
        missing = set(selected_ids) - raw_by_id.keys()
        if missing:
            raise ValueError(f"Missing turns in {session_id}: {sorted(missing)}")

        turns = []
        for dia_id in selected_ids:
            source_turn = raw_by_id[dia_id]
            turn = {
                "dia_id": dia_id,
                "speaker": source_turn["speaker"],
                "text": source_turn["text"],
            }
            turns.append(turn)
            turn_index[(session_id, dia_id)] = turn

        number = session_id.removeprefix("session_")
        sessions.append(
            {
                "session_id": session_id,
                "date_time": conversation[f"session_{number}_date_time"],
                "selected_turns": turns,
            }
        )

    memory_records = []
    for memory in MEMORIES:
        record = dict(memory)
        evidence = []
        for ref in record.pop("source_refs"):
            key = (ref["session_id"], ref["dia_id"])
            if key not in turn_index:
                raise ValueError(
                    f"Memory {record['memory_id']} cites unselected turn {key}"
                )
            evidence.append({**ref, "quote": turn_index[key]["text"]})
        record["evidence"] = evidence
        record["extraction"] = {"method": "manual", "reviewed": True}
        memory_records.append(record)

    try:
        qa = next(item for item in sample["qa"] if item["question"] == QA_QUESTION)
    except StopIteration as exc:
        raise ValueError(f"Question {QA_QUESTION!r} was not found in {SAMPLE_ID}") from exc
    selected_dia_ids = {dia_id for _, dia_id in turn_index}
    missing_evidence = set(qa["evidence"]) - selected_dia_ids
    if missing_evidence:
        raise ValueError(f"QA evidence was not selected: {sorted(missing_evidence)}")

    selected = {
        "dataset": "LoCoMo",
        "source_file": "data/raw/locomo10.json",
        "sample_id": SAMPLE_ID,
        "participants": [conversation["speaker_a"], conversation["speaker_b"]],
        "selection_note": "Three sessions across the timeline; only demo-relevant turns are retained.",
        "sessions": sessions,
        "qa": {
            "question": qa["question"],
            "answer": qa["answer"],
            "evidence": qa["evidence"],
            "category": qa["category"],
        },
    }
    memories = {
        "sample_id": SAMPLE_ID,
        "schema_version": "demo-1.0",
        "memory_count": len(memory_records),
        "memories": memory_records,
    }
    return selected, memories


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw",
        type=Path,
        default=Path("data/raw/locomo10.json"),
        help="Path to the downloaded LoCoMo JSON file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/demo"),
        help="Directory for generated demo JSON files",
    )
    args = parser.parse_args()

    selected, memories = build_demo(load_sample(args.raw))
    write_json(args.output_dir / "selected_sessions.json", selected)
    write_json(args.output_dir / "memories.json", memories)
    print(
        f"Built demo from {len(selected['sessions'])} sessions: "
        f"{sum(len(s['selected_turns']) for s in selected['sessions'])} selected turns "
        f"-> {memories['memory_count']} memories"
    )


if __name__ == "__main__":
    main()
