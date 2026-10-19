"""Memory 存储：按样本读取符合 memory_schema.json 的 JSON 文件。

默认读取 A 抽取产出的 `outputs/memories/`；该目录不存在时退回 `data/memories/`
（测试与演示用的最小样本）。可用 DMS_MEMORY_DIR 覆盖。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from backend.schemas import Memory, SampleSummary

DEFAULT_MEMORY_DIR = Path("outputs/memories")
FALLBACK_MEMORY_DIR = Path("data/memories")


def default_memory_dir() -> Path:
    configured = os.environ.get("DMS_MEMORY_DIR")
    if configured:
        return Path(configured)
    if DEFAULT_MEMORY_DIR.is_dir():
        return DEFAULT_MEMORY_DIR
    return FALLBACK_MEMORY_DIR


class MemoryStore:
    def __init__(self, directory: Path | str | None = None) -> None:
        self.directory = Path(directory) if directory else default_memory_dir()
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
