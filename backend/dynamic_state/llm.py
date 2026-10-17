"""Optional LLM judge for ambiguous B2 memory relations."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas import Memory, RelationType

logger = logging.getLogger(__name__)


class RelationDecision(BaseModel):
    """The only data an LLM may contribute to relation resolution."""

    model_config = ConfigDict(extra="forbid")

    relation: RelationType
    reason: str = Field(min_length=1)


@runtime_checkable
class RelationJudge(Protocol):
    def judge(
        self,
        question: str,
        first: Memory,
        second: Memory,
    ) -> RelationDecision | None:
        """Classify ``first -> second`` or return None to use the rule fallback."""

        ...


class OpenAIRelationJudge:
    """OpenAI Responses API adapter with strict structured output.

    The SDK import and client creation are lazy, so the default rules-only mode
    remains offline and has no API-key requirement.
    """

    _INSTRUCTIONS = """You classify the relation from the first memory to the second memory.
Return exactly one label:
- RETAIN: the second memory confirms or preserves the same fact/state.
- UPDATE: the second memory adds compatible information without invalidating the first.
- SUPERSEDE: the second memory makes the first an older historical value of the same state.
- CONFLICT: the memories are incompatible and available evidence cannot safely order or reconcile them.

Use effective/event time when explicitly stated; otherwise use observation/session time. Never use
retrieval rank or score as truth, confidence, or recency. Judge only from the supplied memories and
question. Equivalent aliases or paraphrases (for example NYC and New York City, or planned and still
planned) are RETAIN. A later conversation can describe an older historical event, so observation order
alone does not imply SUPERSEDE. If the first memory is explicitly current and a later observation merely
adds an older historical state, classify UPDATE because the history is compatible but does not confirm or
replace the current state. Explicit correction, cancellation, completion, or a move from "used to" to
"now" normally indicates SUPERSEDE. A progression within the same lifecycle attribute, such as planned
to scheduled to opened/completed, is also SUPERSEDE because the earlier stage becomes historical; this is
different from phrases such as "still planned", which RETAIN the same stage. Keep the reason short and
evidence-based."""

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

    def judge(
        self,
        question: str,
        first: Memory,
        second: Memory,
    ) -> RelationDecision | None:
        payload = {
            "question": question,
            "first_memory": first.model_dump(mode="json", by_alias=True),
            "second_memory": second.model_dump(mode="json", by_alias=True),
        }
        try:
            response = self._client_or_create().responses.create(
                model=self.model,
                instructions=self._INSTRUCTIONS,
                input=json.dumps(payload, ensure_ascii=False),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "relation_decision",
                        "strict": True,
                        "schema": RelationDecision.model_json_schema(),
                    }
                },
                store=False,
            )
            if getattr(response, "status", None) != "completed":
                logger.warning("LLM relation judge did not complete; using rule fallback")
                return None
            output_text = getattr(response, "output_text", "")
            if not output_text:
                logger.warning("LLM relation judge returned no structured output; using rule fallback")
                return None
            return RelationDecision.model_validate_json(output_text)
        except Exception as exc:  # API, refusal, incomplete output, and validation all degrade safely.
            logger.warning("LLM relation judge failed; using rule fallback: %s", exc)
            return None


class DeepSeekRelationJudge:
    """DeepSeek Chat Completions adapter using its supported JSON mode."""

    _INSTRUCTIONS = OpenAIRelationJudge._INSTRUCTIONS + """

Return JSON only in this exact shape:
{"relation":"RETAIN|UPDATE|SUPERSEDE|CONFLICT","reason":"short explanation"}
Do not wrap the JSON in Markdown."""

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

    def judge(
        self,
        question: str,
        first: Memory,
        second: Memory,
    ) -> RelationDecision | None:
        payload = {
            "question": question,
            "first_memory": first.model_dump(mode="json", by_alias=True),
            "second_memory": second.model_dump(mode="json", by_alias=True),
        }
        try:
            response = self._client_or_create().chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._INSTRUCTIONS},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                max_tokens=200,
                extra_body={"thinking": {"type": "disabled"}},
            )
            choice = response.choices[0]
            if choice.finish_reason != "stop" or not choice.message.content:
                logger.warning("DeepSeek relation judge returned incomplete output; using rule fallback")
                return None
            return RelationDecision.model_validate_json(choice.message.content)
        except Exception as exc:
            logger.warning("DeepSeek relation judge failed; using rule fallback: %s", exc)
            return None
