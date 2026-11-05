"""Offline end-to-end check of the generalized large-scale runner."""

import hashlib
import json
import re
import sys

from backend.schemas import (
    CandidateMemory, GenerationResult, GenerationTrace, RetrievalResult, TokenUsage,
)
from evaluation.final import large_scale
from tests.test_expansion import memory


def _fixture(tmp_path):
    memories = tmp_path / "memories"
    memories.mkdir()
    item = memory("m1", "open", content="Jon's studio is open.")
    (memories / "sample.json").write_text(
        json.dumps({"sample_id": "sample", "memories": [item.model_dump()]}))
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps([{"sample_id": "sample", "conversation": {
        "session_1": [{"speaker": "Jon", "dia_id": "D1:1", "text": "The studio is open."}],
    }}]))
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [{
        "sample_id": "sample", "question": "Is Jon's studio open?",
        "required_memory_ids": ["m1"], "expected_answer": "open",
    }]}))
    models = tmp_path / "models.json"
    models.write_text(json.dumps({"models": [{"provider": "deepseek", "model": "fake"}]}))
    return memories, raw, cases, models, item


class _FakeRetriever:
    def __init__(self, item):
        self.item = item

    def retrieve(self, question, memories, top_k, *, sample_id):
        return RetrievalResult(sample_id=sample_id, question=question, top_k=top_k,
                               strategy="hybrid",
                               candidates=[CandidateMemory(memory=self.item, rank=1, score=1)])


class _FakeGenerator:
    provider, model, max_output_tokens = "deepseek", "fake", 256
    _INSTRUCTIONS = "test-instructions"

    def generate(self, question, context):
        return GenerationResult(
            answer="open",
            memory_ids=re.findall(r"\[id:([^\]]+)\]", context),
            trace=GenerationTrace(
                provider="deepseek", model="fake", response_model="fake",
                status="answered", api_called=True,
                context_sha256=hashlib.sha256((question + context).encode()).hexdigest(),
                usage=TokenUsage(input_tokens=20, output_tokens=5, total_tokens=25),
            ),
        )


def test_large_scale_runner_end_to_end(tmp_path, monkeypatch):
    memories, raw, cases, models, item = _fixture(tmp_path)
    monkeypatch.setattr(large_scale, "resolve_retrievers",
                        lambda _: {"embedding": _FakeRetriever(item), "hybrid": _FakeRetriever(item)})
    monkeypatch.setattr(large_scale, "build_answer_generator", lambda **kwargs: _FakeGenerator())
    output = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", [
        "large_scale", "--models-file", str(models), "--cases", str(cases),
        "--raw", str(raw), "--memory-dir", str(memories),
        "--output-dir", str(output), "--top-k", "1", "--larger-k", "2",
    ])
    large_scale.main()

    summary = json.loads((output / "summary.json").read_text())
    block = summary["summary"]["deepseek/fake"]
    for method in large_scale.METHODS:
        assert block[method]["mean_f1"] == 1, method
    assert block["state_k10"]["mean_candidates"] == 1
    assert (output / "summary.md").is_file()
    assert (output / "model-fake.json").is_file()
    assert (output / "manifest.json").is_file()
    # Every unique context got exactly one saved response.
    saved = list((output / "requests" / "fake").glob("*.json"))
    manifest = json.loads((output / "manifest.json").read_text())
    assert len(saved) == manifest["unique_contexts"]
    assert manifest["dependencies"]["openai"]
