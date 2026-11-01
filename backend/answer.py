"""Reusable LLM QA answer generation over an arbitrary context.

The dynamic-state resolver currently produces template/extractive answers.
Full Text and Vector RAG baselines have no answer generation logic at all, so
this module provides the missing ``AnswerGenerator`` boundary and OpenAI /
DeepSeek adapters. All compared methods in ``evaluation/final/qa_compare.py``
share one generator and differ only in the context they receive.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

MAX_ANSWER_TOKENS = 160


class AnswerDecision(BaseModel):
    """The only data an LLM may return for a QA answer."""

    model_config = ConfigDict(extra="forbid")

    answer: str | None = Field(
        description="Short answer, or null when the context cannot answer the question.",
    )


@runtime_checkable
class AnswerGenerator(Protocol):
    def answer(self, question: str, context: str) -> str | None:
        """Return a short answer, or None to refuse."""

        ...


class OpenAIAnswerGenerator:
    """OpenAI Responses API adapter with strict structured output."""

    _INSTRUCTIONS = (
        "Answer the question using only the supplied context. Give a short, "
        "specific answer; do not explain and do not invent information. If the "
        "context cannot answer the question, set answer to null."
    )

    def __init__(self, *, model: str, client: Any | None = None) -> None:
        if not model.strip():
            raise ValueError("model must not be empty")
        self.model = model
        self._client = client

    def _client_or_create(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def answer(self, question: str, context: str) -> str | None:
        try:
            response = self._client_or_create().responses.create(
                model=self.model,
                instructions=self._INSTRUCTIONS,
                input=f"Context:\n{context}\n\nQuestion: {question}",
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "answer_decision",
                        "strict": True,
                        "schema": AnswerDecision.model_json_schema(),
                    }
                },
                max_output_tokens=MAX_ANSWER_TOKENS,
                store=False,
            )
            if getattr(response, "status", None) != "completed":
                logger.warning("LLM answer generator did not complete; returning None")
                return None
            output_text = getattr(response, "output_text", "")
            if not output_text:
                logger.warning("LLM answer generator returned no output; returning None")
                return None
            decision = AnswerDecision.model_validate_json(output_text)
            answer = decision.answer
            return answer.strip() if answer and answer.strip() else None
        except Exception as exc:
            logger.warning("LLM answer generator failed; returning None: %s", exc)
            return None


class DeepSeekAnswerGenerator:
    """DeepSeek Chat Completions adapter using its JSON mode."""

    _INSTRUCTIONS = OpenAIAnswerGenerator._INSTRUCTIONS + (
        '\n\nReturn JSON only in this exact shape: {"answer": "short answer" or null}. '
        "Do not wrap the JSON in Markdown."
    )

    def __init__(
        self,
        *,
        model: str = "deepseek-flash",
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com",
        client: Any | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("model must not be empty")
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self._client = client

    def _client_or_create(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def answer(self, question: str, context: str) -> str | None:
        try:
            response = self._client_or_create().chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._INSTRUCTIONS},
                    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
                ],
                response_format={"type": "json_object"},
                max_tokens=MAX_ANSWER_TOKENS,
                extra_body={"thinking": {"type": "disabled"}},
            )
            choice = response.choices[0]
            if choice.finish_reason != "stop" or not choice.message.content:
                logger.warning("DeepSeek answer generator returned incomplete output; returning None")
                return None
            decision = AnswerDecision.model_validate_json(choice.message.content)
            answer = decision.answer
            return answer.strip() if answer and answer.strip() else None
        except Exception as exc:
            logger.warning("DeepSeek answer generator failed; returning None: %s", exc)
            return None


def build_answer_generator(
    *,
    provider: str | None = None,
    model: str | None = None,
    generator: AnswerGenerator | None = None,
) -> AnswerGenerator:
    """Build the LLM answer generator; reuse the resolver's provider/model env."""

    if generator is not None:
        return generator

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    selected_provider = (provider or os.getenv("DMS_LLM_PROVIDER", "openai")).strip().casefold()
    if selected_provider == "openai":
        selected_model = (model or os.getenv("DMS_LLM_MODEL", "")).strip()
        if not selected_model:
            raise ValueError("DMS_LLM_MODEL is required for the OpenAI answer generator")
        return OpenAIAnswerGenerator(model=selected_model)
    if selected_provider == "deepseek":
        from backend.dynamic_state.factory import _deepseek_api_key

        selected_model = (model or os.getenv("DMS_LLM_MODEL", "deepseek-flash")).strip()
        return DeepSeekAnswerGenerator(
            model=selected_model,
            api_key=_deepseek_api_key(),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
    raise ValueError("DMS_LLM_PROVIDER must be 'openai' or 'deepseek'")
