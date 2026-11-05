"""Exercise the real SDK serialization against a local, simulated BigModel API."""

import json

import httpx
from openai import OpenAI
import pytest

from backend.answer import GLMAnswerGenerator, build_answer_generator
from backend.qa import generate_grounded_answer
from tests.test_expansion import memory


@pytest.mark.parametrize("model,thinking", [
    ("glm-4.7-flash", True), ("glm-4.5-air", True), ("glm-4-flash-250414", False),
])
def test_glm_sdk_request_citations_and_real_usage_fields(model, thinking):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={
            "id": "glm-test", "created": 1, "object": "chat.completion", "model": model,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": '{"answer":"open","memory_ids":["m1"]}',
            }}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110,
                      "prompt_tokens_details": {"cached_tokens": 40}},
        })

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = OpenAI(api_key="glm-test-key", base_url="https://open.bigmodel.cn/api/paas/v4/",
                        http_client=http, max_retries=0)
        generator = GLMAnswerGenerator(model=model, client=client)
        result = generate_grounded_answer("Is it open?", "[id:m1] open", generator,
                                          memories=[memory("m1", "open")])
    assert len(requests) == 1
    assert str(requests[0].url) == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer glm-test-key"
    body = json.loads(requests[0].content)
    assert body["model"] == model and body["max_tokens"] == 256
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0
    if thinking:
        assert body["thinking"] == {"type": "disabled"}
    else:
        assert "thinking" not in body
    assert "tools" not in body  # Evidence-only QA must not enable web search.
    assert result.answer == "open" and result.memory_ids == ["m1"]
    assert result.trace.provider == "glm" and result.trace.response_model == model
    assert result.trace.status == "answered"
    assert result.trace.usage.input_tokens == 100
    assert result.trace.usage.cached_input_tokens == 40
    assert result.trace.usage.uncached_input_tokens == 60
    assert result.trace.usage.total_tokens == 110


@pytest.mark.parametrize("primary", [True, False])
def test_glm_factory_uses_own_keys_endpoint_and_model_default(monkeypatch, primary):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("DMS_ANSWER_PROVIDER", "deepseek")
    monkeypatch.setenv("DMS_ANSWER_MODEL", "deepseek-flash")
    monkeypatch.setenv("DMS_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DMS_LLM_MODEL", "deepseek-flash")
    monkeypatch.setenv("ZAI_API_KEY", "alias-key")
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    if primary:
        monkeypatch.setenv("GLM_API_KEY", "primary-key")
    monkeypatch.setenv("GLM_BASE_URL", "https://example.test/v4/")
    generator = build_answer_generator(provider="glm", max_output_tokens=512)
    assert isinstance(generator, GLMAnswerGenerator)
    assert generator.model == "glm-4.7-flash"  # Never inherit another provider's model.
    assert generator.api_key == ("primary-key" if primary else "alias-key")
    assert generator.base_url == "https://example.test/v4/"
    assert generator.max_output_tokens == 512


def test_glm_without_key_does_not_borrow_other_provider_credentials(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "other-provider-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "other-provider-key")
    result = build_answer_generator(provider="glm", model="glm-4.7-flash").generate("q", "c")
    assert result.answer is None and result.trace.status == "error"
    assert result.trace.error_code == "not_configured" and not result.trace.api_called


@pytest.mark.parametrize("status,content,finish,expected", [
    (401, None, "stop", "api_error"),
    (200, "not JSON", "stop", "invalid_response"),
    (200, '{"answer":"partial"', "length", "incomplete_response"),
    (200, '{"answer":null,"memory_ids":[]}', "stop", None),
    (200, '{"answer":"open","memory_ids":["invented"]}', "stop", "invalid_citation"),
])
def test_glm_failure_refusal_and_invalid_citation_have_no_fallback(status, content, finish, expected):
    calls = []

    def handle(request):
        calls.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "Invalid key", "code": "401"}})
        return httpx.Response(200, json={
            "id": "glm-test", "created": 1, "object": "chat.completion", "model": "glm-4.7-flash",
            "choices": [{"index": 0, "finish_reason": finish,
                         "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
        })

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = OpenAI(api_key="test", base_url="https://example.test/v4/", http_client=http, max_retries=0)
        result = generate_grounded_answer("q", "[id:m1] open", GLMAnswerGenerator(client=client),
                                          memories=[memory("m1", "open")])
    assert len(calls) == 1 and result.answer is None and result.memory_ids == []
    assert result.trace.status == ("error" if expected else "refused")
    assert result.trace.error_code == expected
    assert result.trace.usage.total_tokens == (110 if status == 200 else None)
