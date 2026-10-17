"""Hybrid B2 relation-judging tests without network calls."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.dynamic_state.factory import build_dynamic_state_resolver
from backend.dynamic_state.llm import DeepSeekRelationJudge, OpenAIRelationJudge, RelationDecision
from backend.dynamic_state.resolver import RuleBasedDynamicStateResolver
from backend.schemas import CandidateMemory, Memory, RetrievalResult


def _memory(
    memory_id: str,
    *,
    attribute: str = "place.status",
    value: str,
    session_id: str = "unknown",
    content: str | None = None,
) -> Memory:
    return Memory.model_validate(
        {
            "memory_id": memory_id,
            "subject": "Place",
            "type": "state",
            "content": content or f"The {attribute} is {value}.",
            "attribute": attribute,
            "value": value,
            "time": {"session_id": session_id},
            "evidence": [{"session_id": session_id, "dia_id": f"{memory_id}:1"}],
        }
    )


def _retrieval(first: Memory, second: Memory) -> RetrievalResult:
    return RetrievalResult(
        sample_id="sample",
        question="What changed?",
        top_k=2,
        strategy="bm25",
        candidates=[
            CandidateMemory(memory=first, score=1.0, rank=1),
            CandidateMemory(memory=second, score=0.9, rank=2),
        ],
    )


class _RecordingJudge:
    def __init__(self, decision: RelationDecision | None) -> None:
        self.decision = decision
        self.calls: list[tuple[str, str]] = []

    def judge(self, question: str, first: Memory, second: Memory) -> RelationDecision | None:
        self.calls.append((first.memory_id, second.memory_id))
        return self.decision


def test_hybrid_uses_judge_for_unordered_incompatible_values():
    judge = _RecordingJudge(
        RelationDecision(relation="SUPERSEDE", reason="The second statement explicitly corrects the first.")
    )
    resolver = RuleBasedDynamicStateResolver(relation_judge=judge)

    response = resolver.resolve(
        _retrieval(_memory("m1", value="open"), _memory("m2", value="closed"))
    )

    assert judge.calls == [("m1", "m2")]
    assert response.relations[0].relation == "SUPERSEDE"


def test_hybrid_keeps_confident_rule_without_calling_judge():
    judge = _RecordingJudge(
        RelationDecision(relation="CONFLICT", reason="This answer must not override a clear rule.")
    )
    resolver = RuleBasedDynamicStateResolver(relation_judge=judge)

    response = resolver.resolve(
        _retrieval(
            _memory(
                "m1",
                value="planned",
                session_id="session_1",
                content="The opening was planned for 2023-01-01.",
            ),
            _memory(
                "m2",
                value="opened",
                session_id="session_2",
                content="The place opened on 2023-02-01.",
            ),
        )
    )

    assert judge.calls == []
    assert response.relations[0].relation == "SUPERSEDE"


def test_hybrid_uses_judge_when_only_session_order_supports_supersede():
    judge = _RecordingJudge(
        RelationDecision(relation="RETAIN", reason="NYC and New York City are aliases.")
    )
    resolver = RuleBasedDynamicStateResolver(relation_judge=judge)

    response = resolver.resolve(
        _retrieval(
            _memory("m1", attribute="residence.city", value="NYC", session_id="session_1"),
            _memory(
                "m2",
                attribute="residence.city",
                value="New York City",
                session_id="session_2",
            ),
        )
    )

    assert judge.calls == [("m1", "m2")]
    assert response.relations[0].relation == "RETAIN"


def test_hybrid_falls_back_when_judge_returns_none():
    judge = _RecordingJudge(None)
    resolver = RuleBasedDynamicStateResolver(relation_judge=judge)

    response = resolver.resolve(
        _retrieval(_memory("m1", value="open"), _memory("m2", value="closed"))
    )

    assert judge.calls == [("m1", "m2")]
    assert response.relations[0].relation == "CONFLICT"


def test_hybrid_uses_judge_for_different_attributes_in_same_topic():
    judge = _RecordingJudge(
        RelationDecision(relation="UPDATE", reason="The second memory adds a compatible detail.")
    )
    resolver = RuleBasedDynamicStateResolver(relation_judge=judge)

    response = resolver.resolve(
        _retrieval(
            _memory("m1", attribute="place.status", value="open", session_id="session_1"),
            _memory("m2", attribute="place.visitors", value="busy", session_id="session_2"),
        )
    )

    assert judge.calls == [("m1", "m2")]
    assert response.relations[0].relation == "UPDATE"


class _FakeResponses:
    def __init__(self, response: object) -> None:
        self.response = response
        self.kwargs: dict | None = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def test_openai_judge_uses_strict_structured_output():
    responses = _FakeResponses(
        SimpleNamespace(
            status="completed",
            output_text=json.dumps({"relation": "UPDATE", "reason": "Compatible detail."}),
        )
    )
    client = SimpleNamespace(responses=responses)
    judge = OpenAIRelationJudge(model="test-model", client=client)

    decision = judge.judge(
        "What changed?",
        _memory("m1", attribute="place.status", value="open"),
        _memory("m2", attribute="place.visitors", value="busy"),
    )

    assert decision == RelationDecision(relation="UPDATE", reason="Compatible detail.")
    assert responses.kwargs["model"] == "test-model"
    assert responses.kwargs["store"] is False
    output_format = responses.kwargs["text"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["strict"] is True


def test_openai_judge_falls_back_on_incomplete_response():
    client = SimpleNamespace(
        responses=_FakeResponses(SimpleNamespace(status="incomplete", output_text=""))
    )
    judge = OpenAIRelationJudge(model="test-model", client=client)

    assert judge.judge(
        "What changed?", _memory("m1", value="open"), _memory("m2", value="closed")
    ) is None


class _FakeChatCompletions:
    def __init__(self, response: object) -> None:
        self.response = response
        self.kwargs: dict | None = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def test_deepseek_judge_uses_json_mode():
    completions = _FakeChatCompletions(
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content=json.dumps(
                            {"relation": "UPDATE", "reason": "Compatible detail."}
                        )
                    ),
                )
            ]
        )
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    judge = DeepSeekRelationJudge(model="deepseek-flash", client=client)

    decision = judge.judge(
        "What changed?",
        _memory("m1", attribute="place.status", value="open"),
        _memory("m2", attribute="place.visitors", value="busy"),
    )

    assert decision == RelationDecision(relation="UPDATE", reason="Compatible detail.")
    assert completions.kwargs["model"] == "deepseek-flash"
    assert completions.kwargs["response_format"] == {"type": "json_object"}
    assert completions.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


def test_factory_builds_deepseek_hybrid_without_model_env(monkeypatch):
    monkeypatch.delenv("DMS_LLM_MODEL", raising=False)
    resolver = build_dynamic_state_resolver(mode="hybrid", provider="deepseek")

    assert isinstance(resolver, RuleBasedDynamicStateResolver)
    assert isinstance(resolver._relation_judge, DeepSeekRelationJudge)
    assert resolver._relation_judge.model == "deepseek-flash"


def test_factory_defaults_to_rules(monkeypatch):
    resolver = build_dynamic_state_resolver(mode="rules")
    assert isinstance(resolver, RuleBasedDynamicStateResolver)
    assert resolver._relation_judge is None


def test_factory_requires_model_for_hybrid(monkeypatch):
    monkeypatch.setenv("DMS_LLM_MODEL", "")
    with pytest.raises(ValueError, match="DMS_LLM_MODEL"):
        build_dynamic_state_resolver(mode="hybrid", provider="openai")
