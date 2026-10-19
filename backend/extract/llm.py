"""抽取用的 LLM 客户端。

沿用 B 部分已有的约定（`DMS_LLM_PROVIDER` / `DMS_LLM_MODEL` / `DEEPSEEK_API_KEY`），
不引入新的配置项。OpenAI SDK 是懒加载的，因此只跑规则模式时完全离线。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_OPENAI_BASE_URL = None


class ExtractionError(RuntimeError):
    """LLM 调用或输出解析失败。"""


@runtime_checkable
class ExtractionClient(Protocol):
    """只暴露一个方法，方便测试时替换为假客户端。"""

    name: str

    def extract_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """返回模型输出的 JSON 对象。"""


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv 是可选依赖
        return
    load_dotenv()


def _strip_code_fence(text: str) -> str:
    """模型偶尔会包一层 ```json ... ```，这里剥掉。"""

    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


class ChatCompletionsClient:
    """OpenAI 兼容的 Chat Completions 客户端（DeepSeek / OpenAI 通用）。"""

    def __init__(
        self,
        *,
        model: str,
        base_url: str | None,
        api_key: str | None,
        provider: str,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        timeout: float = 120.0,
        max_retries: int = 4,
        client: Any | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("model must not be empty")
        if not api_key and client is None:
            raise ValueError(f"{provider}: API key is missing")
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.provider = provider
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = client
        self.name = f"{provider}:{model}"

    def _client_or_create(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=0,
            )
        return self._client

    def _request(self, system_prompt: str, user_prompt: str) -> str:
        extra_body = {"thinking": {"type": "disabled"}} if self.provider == "deepseek" else {}
        response = self._client_or_create().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
            extra_body=extra_body or None,
        )
        choice = response.choices[0]
        content = choice.message.content
        if not content:
            raise ExtractionError(f"{self.name}: empty response (finish_reason={choice.finish_reason})")
        return content

    def extract_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                raw = self._request(system_prompt, user_prompt)
                data = json.loads(_strip_code_fence(raw))
                if not isinstance(data, dict):
                    raise ExtractionError(f"{self.name}: expected a JSON object, got {type(data).__name__}")
                return data
            except Exception as exc:  # 网络、限流、截断、JSON 解析错误统一重试
                last_error = exc
                if attempt == self.max_retries:
                    break
                backoff = min(2 ** attempt, 16)
                logger.warning(
                    "%s attempt %s/%s failed (%s); retrying in %ss",
                    self.name, attempt, self.max_retries, exc, backoff,
                )
                time.sleep(backoff)
        raise ExtractionError(f"{self.name}: extraction failed after {self.max_retries} attempts: {last_error}")


class FakeClient:
    """测试用：返回预设的 JSON，并记录调用次数。"""

    def __init__(self, payloads: list[dict[str, Any]] | dict[str, Any] | None = None) -> None:
        self._payloads = payloads if isinstance(payloads, list) else [payloads or {"memories": []}]
        self.name = "fake"
        self.calls = 0

    def extract_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = self._payloads[min(self.calls, len(self._payloads) - 1)]
        self.calls += 1
        return payload


def build_client(provider: str | None = None) -> ExtractionClient:
    """按环境变量构造客户端；``provider="rules"`` 不应走到这里。"""

    _load_env()
    provider = (provider or os.environ.get("DMS_LLM_PROVIDER") or "deepseek").strip().lower()

    if provider == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key or "replace" in api_key.lower():
            raise ExtractionError(
                "DEEPSEEK_API_KEY is not configured; run with --provider rules or set the key in .env"
            )
        model = (
            os.environ.get("DMS_EXTRACT_MODEL")
            or os.environ.get("DMS_LLM_MODEL")
            or "deepseek-flash"
        ).strip()
        base_url = os.environ.get("DMS_LLM_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL).strip()
        return ChatCompletionsClient(
            provider=provider, model=model, base_url=base_url, api_key=api_key
        )

    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ExtractionError("OPENAI_API_KEY is not configured; run with --provider rules")
        model = (
            os.environ.get("DMS_EXTRACT_MODEL")
            or os.environ.get("DMS_LLM_MODEL")
            or "gpt-4o-mini"
        ).strip()
        base_url = os.environ.get("DMS_LLM_BASE_URL", DEFAULT_OPENAI_BASE_URL)
        return ChatCompletionsClient(
            provider=provider, model=model, base_url=base_url, api_key=api_key
        )

    raise ExtractionError(f"unknown LLM provider: {provider!r}")


def has_llm_credentials() -> bool:
    """``auto`` 模式下判断能否走 LLM。"""

    _load_env()
    provider = (os.environ.get("DMS_LLM_PROVIDER") or "deepseek").strip().lower()
    if provider == "deepseek":
        key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        return bool(key) and "replace" not in key.lower()
    if provider == "openai":
        return bool(os.environ.get("OPENAI_API_KEY", "").strip())
    return False
