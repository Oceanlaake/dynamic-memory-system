"""LLM 响应缓存。

抽取结果需要可复现、可复查：同样的提示词直接命中缓存，不再产生 API 调用。
缓存按提示词内容的 SHA-1 存成一个 JSON 文件，放在 ``.cache/extract/``（已被 .gitignore 忽略）。
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(".cache/extract")


class ResponseCache:
    def __init__(self, directory: Path | str | None = DEFAULT_CACHE_DIR) -> None:
        self.directory = Path(directory) if directory else None
        self.hits = 0
        self.misses = 0
        self.writes = 0

    @property
    def enabled(self) -> bool:
        return self.directory is not None

    @staticmethod
    def key(system_prompt: str, user_prompt: str) -> str:
        digest = hashlib.sha1()
        digest.update(system_prompt.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(user_prompt.encode("utf-8"))
        return digest.hexdigest()

    def _path(self, key: str) -> Path:
        assert self.directory is not None
        return self.directory / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        path = self._path(key)
        if not path.exists():
            self.misses += 1
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("ignoring broken cache entry %s: %s", path, exc)
            self.misses += 1
            return None
        if not isinstance(payload, dict):
            self.misses += 1
            return None
        self.hits += 1
        return payload

    def set(self, key: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.writes += 1

    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "writes": self.writes}


class CachedExtractionClient:
    """给任意 :class:`ExtractionClient` 套一层缓存。"""

    def __init__(self, inner: Any, cache: ResponseCache) -> None:
        self.inner = inner
        self.cache = cache
        self.name = getattr(inner, "name", "client")
        self.is_cached = True

    def extract_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        key = self.cache.key(system_prompt, user_prompt)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        payload = self.inner.extract_json(system_prompt, user_prompt)
        self.cache.set(key, payload)
        return payload
