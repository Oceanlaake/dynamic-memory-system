"""Memory 存储：按样本读取符合 memory_schema.json 的 JSON 文件。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from backend.schemas import Memory, SampleSummary

DEFAULT_MEMORY_DIR = Path("data/memories")


class MemoryStore:
    def __init__(self, directory: Path | str | None = None) -> None:
        self.directory = Path(directory or os.environ.get("DMS_MEMORY_DIR") or DEFAULT_MEMORY_DIR)
        self._by_sample: dict[str, list[Memory]] = {}
        self._load()

    def _load(self) -> None:
        if not self.directory.is_dir():
            return
        for path in sorted(self.directory.glob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            sample_id = document["sample_id"]
            self._by_sample[sample_id] = [
                Memory.model_validate(item) for item in document["memories"]
            ]

    def sample_ids(self) -> list[str]:
        return sorted(self._by_sample)

    def summaries(self) -> list[SampleSummary]:
        return [
            SampleSummary(sample_id=sample_id, memory_count=len(memories))
            for sample_id, memories in sorted(self._by_sample.items())
        ]

    def memories(self, sample_id: str) -> list[Memory] | None:
        return self._by_sample.get(sample_id)
