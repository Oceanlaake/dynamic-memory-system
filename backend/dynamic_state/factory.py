"""Configuration boundary for the B2 dynamic-state resolver."""

from __future__ import annotations

import os
import subprocess

from backend.dynamic_state.base import DynamicStateResolver
from backend.dynamic_state.llm import DeepSeekRelationJudge, OpenAIRelationJudge, RelationJudge
from backend.dynamic_state.resolver import RuleBasedDynamicStateResolver

_DEEPSEEK_KEYCHAIN_ACCOUNT = "dynamic-memory-system"
_DEEPSEEK_KEYCHAIN_SERVICE = "dynamic-memory-system.deepseek-api-key"


def _deepseek_api_key() -> str | None:
    configured = os.getenv("DEEPSEEK_API_KEY")
    if configured:
        return configured
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                _DEEPSEEK_KEYCHAIN_ACCOUNT,
                "-s",
                _DEEPSEEK_KEYCHAIN_SERVICE,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    key = result.stdout.strip()
    return key or None


def build_dynamic_state_resolver(
    *,
    mode: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    judge: RelationJudge | None = None,
) -> DynamicStateResolver:
    """Build the rules-only default or the explicitly enabled hybrid resolver."""

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    selected = (mode or os.getenv("DMS_STATE_RESOLVER", "rules")).strip().casefold()
    if selected == "rules":
        return RuleBasedDynamicStateResolver()
    if selected != "hybrid":
        raise ValueError("DMS_STATE_RESOLVER must be 'rules' or 'hybrid'")

    if judge is None:
        selected_provider = (provider or os.getenv("DMS_LLM_PROVIDER", "openai")).strip().casefold()
        if selected_provider == "deepseek":
            selected_model = (model or os.getenv("DMS_LLM_MODEL", "deepseek-flash")).strip()
            judge = DeepSeekRelationJudge(
                model=selected_model,
                api_key=_deepseek_api_key(),
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            )
        elif selected_provider == "openai":
            selected_model = (model or os.getenv("DMS_LLM_MODEL", "")).strip()
            if not selected_model:
                raise ValueError("DMS_LLM_MODEL is required for the OpenAI hybrid resolver")
            judge = OpenAIRelationJudge(model=selected_model)
        else:
            raise ValueError("DMS_LLM_PROVIDER must be 'openai' or 'deepseek'")
    return RuleBasedDynamicStateResolver(relation_judge=judge)
