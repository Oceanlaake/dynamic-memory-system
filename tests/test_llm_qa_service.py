"""No template answers, grounded citations, and truthful API token accounting."""

import json
from types import SimpleNamespace as NS

from backend.answer import DeepSeekAnswerGenerator, OpenAIAnswerGenerator, extract_usage
from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.qa import answer_query, generate_grounded_answer, generation_summary
from backend.schemas import GenerationResult, GenerationTrace, TokenUsage
from tests.test_expansion import memory, retrieval


class Request:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.kwargs = response, error, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def deepseek(response_json=None, *, finish="stop", usage=None):
    request = Request(NS(choices=[NS(finish_reason=finish, message=NS(content=json.dumps(
        response_json if response_json is not None else {"answer": "open", "memory_ids": ["m1"]}
    )))], model="actual-deepseek-revision", usage=usage))
    return DeepSeekAnswerGenerator(client=NS(chat=NS(completions=request))), request


def test_deepseek_reports_usage_and_uses_fixed_short_answer_budget():
    generator, request = deepseek(usage=NS(prompt_tokens=100, completion_tokens=20, total_tokens=120,
                                          prompt_cache_hit_tokens=40, prompt_cache_miss_tokens=60))
    result = generator.generate("Question", "Context")
    assert result.answer == "open" and result.memory_ids == ["m1"]
    assert result.trace.response_model == "actual-deepseek-revision"
    assert result.trace.usage.input_tokens == 100
    assert result.trace.usage.output_tokens == 20
    assert result.trace.usage.cached_input_tokens == 40
    assert result.trace.usage.uncached_input_tokens == 60
    assert result.trace.usage.total_tokens == 120  # Cache tokens are not added again.
    assert request.kwargs["temperature"] == 0
    assert request.kwargs["max_tokens"] == 256


def test_openai_reports_cached_and_reasoning_details_without_double_counting():
    request = Request(NS(status="completed", output_text='{"answer":"open","memory_ids":["m1"]}',
                         model="actual-openai-revision", usage=NS(
        input_tokens=300, output_tokens=40, total_tokens=340,
        input_tokens_details=NS(cached_tokens=200), output_tokens_details=NS(reasoning_tokens=10),
    )))
    result = OpenAIAnswerGenerator(model="requested-model", client=NS(responses=request)).generate("q", "c")
    assert result.trace.usage.uncached_input_tokens == 100
    assert result.trace.usage.reasoning_tokens == 10
    assert result.trace.usage.total_tokens == 340
    assert set(request.kwargs["text"]["format"]["schema"]["required"]) == {"answer", "memory_ids"}


def test_invalid_structured_response_is_an_error_but_keeps_consumed_usage():
    generator, _ = deepseek({"answer": "open"}, usage={"prompt_tokens": 10, "completion_tokens": 5})
    result = generator.generate("q", "c")
    assert result.answer is None
    assert result.trace.status == "error" and result.trace.error_code == "invalid_response"
    assert result.trace.usage.total_tokens == 15


def test_api_failure_does_not_look_like_a_model_refusal_or_leak_error_details(caplog):
    request = Request(error=RuntimeError("sensitive-diagnostic-details"))
    generator = DeepSeekAnswerGenerator(client=NS(chat=NS(completions=request)))
    result = generator.generate("q", "c")
    assert result.answer is None and result.trace.status == "error"
    assert result.trace.error_code == "api_error" and result.trace.api_called
    assert result.trace.usage.input_tokens is None
    assert "sensitive-diagnostic-details" not in caplog.text


def test_deepseek_never_borrows_an_openai_credential(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "a-different-provider-secret")
    result = DeepSeekAnswerGenerator(api_key=None).generate("q", "c")
    assert result.trace.error_code == "not_configured"
    assert not result.trace.api_called


def test_model_refusal_is_distinct_from_api_error():
    generator, _ = deepseek({"answer": None, "memory_ids": []}, usage={"prompt_tokens": 20, "completion_tokens": 5})
    result = generator.generate("q", "c")
    assert result.answer is None and result.trace.status == "refused"
    assert result.trace.error_code is None
    assert result.trace.usage.total_tokens == 25


def test_string_null_is_normalized_to_model_refusal():
    generator, _ = deepseek({"answer": "null", "memory_ids": []})
    result = generator.generate("q", "c")
    assert result.answer is None and result.trace.status == "refused"
    assert result.trace.error_code is None


def test_missing_usage_stays_unknown_not_a_character_based_estimate():
    assert extract_usage(None).input_tokens is None
    assert extract_usage({}).total_tokens is None


class FixedGenerator:
    provider, model = "fake", "fake"

    def __init__(self, answer="Max and Daisy", ids=None):
        self.answer, self.ids, self.calls = answer, ids if ids is not None else ["m2"], 0

    def generate(self, question, context):
        self.calls += 1
        return GenerationResult(answer=self.answer, memory_ids=self.ids, trace=GenerationTrace(
            provider="fake", model="fake", status="answered" if self.answer else "refused", api_called=True,
            usage=TokenUsage(input_tokens=100, output_tokens=10, total_tokens=110),
        ))


def test_llm_can_cite_supporting_memory_not_selected_by_rank_one_and_never_calls_template(monkeypatch):
    first = memory("m1", "two_dogs", attribute="pet_ownership", content="Jon has two dogs.")
    second = memory("m2", "dogs_named", attribute="pet_ownership", content="Jon's dogs are named Max and Daisy.")
    resolver = RuleBasedDynamicStateResolver()
    monkeypatch.setattr(resolver, "_answer", lambda *args: (_ for _ in ()).throw(AssertionError("Template called")))
    result = answer_query(retrieval(first, second, question="What are the names of Jon's dogs?"),
                          [first, second], resolver, FixedGenerator())
    assert result.answer == "Max and Daisy"
    assert result.effective_memories[0].memory_id == "m1"  # Advisory, not a hard filter.
    assert result.answer_memory_ids == ["m2"]
    assert result.evidence[0].dia_id == second.evidence[0].dia_id


def test_invalid_citation_is_rejected_without_template_fallback():
    m = memory("m1")
    result = answer_query(retrieval(m), [m], RuleBasedDynamicStateResolver(),
                          FixedGenerator(answer="fabricated", ids=["not-in-context"]))
    assert result.answer is None and result.evidence == []
    assert result.generation.status == "error"
    assert result.generation.error_code == "invalid_citation"
    assert result.generation.usage.total_tokens == 110


def test_identical_input_reuse_separates_logical_footprint_from_actual_spend():
    generator = FixedGenerator(ids=["m1"])
    m = memory("m1")
    cache = {}
    first = generate_grounded_answer("q", "context", generator, memories=[m], cache=cache)
    second = generate_grounded_answer("q", "context", generator, memories=[m], cache=cache)
    assert generator.calls == 1
    assert not second.trace.api_called and second.trace.reused
    stats = generation_summary([first.trace, second.trace])
    assert stats["api_calls"] == 1 and stats["reused"] == 1
    assert stats["actual_calls_usage"]["input_tokens"]["sum_reported"] == 100
    assert stats["standalone_token_footprint"]["input_tokens"]["mean_reported"] == 100


def test_no_evidence_skips_llm_and_never_returns_a_canned_answer():
    initial = retrieval(memory("m1")).model_copy(update={"candidates": [], "degraded": True})
    generator = FixedGenerator()
    result = answer_query(initial, [], RuleBasedDynamicStateResolver(), generator)
    assert generator.calls == 0
    assert result.answer is None and result.generation.status == "skipped"


def test_raw_dialogue_generation_has_no_memory_id_citations():
    result = generate_grounded_answer("q", "raw dialogue", FixedGenerator(ids=["invented-id"]))
    assert result.trace.error_code == "invalid_citation"
