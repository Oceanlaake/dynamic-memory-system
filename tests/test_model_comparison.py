"""Exercise the complete multi-model CLI using explicit fake API results."""

import hashlib
import json
import re
import sys

from backend.schemas import CandidateMemory, GenerationResult, GenerationTrace, RetrievalResult, TokenUsage
from evaluation.final import model_compare
from tests.test_expansion import memory


def test_model_matrix_freezes_context_and_keeps_each_models_usage_separate(tmp_path, monkeypatch):
    memories = tmp_path / "memories"
    memories.mkdir()
    item = memory("m1", "open", content="Jon's studio is open.")
    (memories / "sample.json").write_text(json.dumps({"sample_id": "sample", "memories": [item.model_dump()]}))
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps([{"sample_id": "sample", "conversation": {
        "session_1": [{"speaker": "Jon", "dia_id": "D1:1", "text": "The studio is open."}],
    }}]))
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [{"sample_id": "sample", "question": "Is Jon's studio open?",
                                            "required_memory_ids": ["m1"], "expected_answer": "open"}]}))
    models = tmp_path / "models.json"
    models.write_text(json.dumps({"models": [{"provider": "deepseek", "model": "fake-a"},
                                             {"provider": "openai", "model": "fake-b"},
                                             {"provider": "glm", "model": "fake-c"}]}))

    class Retriever:
        def retrieve(self, question, memories, top_k, *, sample_id):
            return RetrievalResult(sample_id=sample_id, question=question, top_k=top_k, strategy="hybrid",
                                   candidates=[CandidateMemory(memory=item, rank=1, score=1)])

    class Generator:
        def __init__(self, provider, model):
            self.provider, self.model = provider, model

        def generate(self, question, context):
            tokens = 20 if self.model == "fake-a" else 30
            return GenerationResult(answer="open", memory_ids=re.findall(r"\[id:([^\]]+)\]", context),
                trace=GenerationTrace(provider=self.provider, model=self.model, response_model=self.model,
                    status="answered", api_called=True, context_sha256=hashlib.sha256((question+context).encode()).hexdigest(),
                    usage=TokenUsage(input_tokens=tokens, output_tokens=5, total_tokens=tokens+5)))

    monkeypatch.setattr(model_compare, "resolve_retrievers", lambda _: {"embedding": Retriever(), "hybrid": Retriever()})
    monkeypatch.setattr(model_compare, "build_answer_generator", lambda **kwargs: Generator(kwargs["provider"], kwargs["model"]))
    output = tmp_path / "results"
    monkeypatch.setattr(sys, "argv", ["model_compare", "--models-file", str(models), "--cases", str(cases),
                                      "--raw", str(raw), "--memory-dir", str(memories),
                                      "--output-dir", str(output), "--repeats", "2"])
    model_compare.main()
    result = json.loads((output / "summary.json").read_text())
    for model, tokens in [("deepseek/fake-a", 20), ("openai/fake-b", 30), ("glm/fake-c", 30)]:
        for method in model_compare.METHODS:
            assert result[model][method]["mean_f1"] == 1
            assert result[model][method]["token_footprint"]["input_tokens"]["mean_reported"] == tokens
        assert result[model]["state_bonus"]["reused"] == 2
        assert result[model]["state_bonus"]["api_calls"] == 0
    assert (output / "summary.md").is_file()
