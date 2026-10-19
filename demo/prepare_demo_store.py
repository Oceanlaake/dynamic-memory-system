#!/usr/bin/env python3
"""Build a 15-memory presentation store from existing repository data.

The five curated Jon memories preserve the deterministic end-to-end story.
Ten real Gina memories from the formal extraction output act as distractors,
so Top-K retrieval selects from a meaningful pool instead of returning all data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CURATED_PATH = REPO_ROOT / "data" / "memories" / "conv-30.json"
FORMAL_PATH = REPO_ROOT / "outputs" / "memories" / "conv-30.json"
OUTPUT_PATH = REPO_ROOT / "data" / "demo_memories" / "conv-30.json"

DISTRACTOR_IDS = [
    "mem-conv30-021",  # Gina's clothing store
    "mem-conv30-038",  # wholesaler reply
    "mem-conv30-040",  # store design
    "mem-conv30-065",  # online store and local artist
    "mem-conv30-072",  # tattoo and personal values
    "mem-conv30-114",  # fashion customer-base goal
    "mem-conv30-166",  # fashion internship
    "mem-conv30-182",  # fashion video presentation
    "mem-conv30-227",  # limited-edition clothing line
    "mem-conv30-241",  # recognition by fashion editors
]


def load_document(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    curated = load_document(CURATED_PATH)
    formal = load_document(FORMAL_PATH)
    formal_by_id = {item["memory_id"]: item for item in formal["memories"]}

    missing = [memory_id for memory_id in DISTRACTOR_IDS if memory_id not in formal_by_id]
    if missing:
        raise ValueError(f"Formal extraction is missing distractors: {missing}")

    memories = [*curated["memories"], *(formal_by_id[item] for item in DISTRACTOR_IDS)]
    memory_ids = [item["memory_id"] for item in memories]
    if len(memory_ids) != len(set(memory_ids)):
        raise ValueError("Demo store contains duplicate memory IDs")

    document = {
        "sample_id": curated["sample_id"],
        "memories": memories,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Built {OUTPUT_PATH.relative_to(REPO_ROOT)}: "
        f"{len(curated['memories'])} relevant + {len(DISTRACTOR_IDS)} distractor memories"
    )


if __name__ == "__main__":
    main()
