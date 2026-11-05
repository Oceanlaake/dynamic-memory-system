"""Same evidence/QA pipeline across configured answer models, with API usage.

Models are user-configured; this script never substitutes a different model.
Rules are fixed and local so the reported LLM usage covers answer generation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from statistics import mean, stdev

from backend.answer import build_answer_generator
from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.store import MemoryStore
from evaluation.final.qa_compare import run_comparison
from evaluation.recall_at_k import load_cases, resolve_retrievers

METHODS = ("full_text", "vector_rag", "state_topk", "state_bonus")


def aggregate(runs: list[dict]) -> dict:
    out = {}
    for method in METHODS:
        scores = [r["summary"][method]["mean_answer_f1"] for r in runs]
        known_scores = [s for s in scores if s is not None]
        traces = [row[method]["generation"] for r in runs for row in r["cases"]]
        tokens = {}
        for name in ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens", "reasoning_tokens"):
            values = [t["usage"][name] for t in traces if t["usage"][name] is not None]
            tokens[name] = {"mean_reported": mean(values) if values else None, "reported_rows": len(values)}
        out[method] = {
            "repeats": len(runs), "rows": len(traces),
            "mean_f1": mean(known_scores) if known_scores else None,
            "repeat_f1_std": stdev(known_scores) if len(known_scores) > 1 else None,
            "token_footprint": tokens,
            "api_calls": sum(t["api_called"] for t in traces),
            "reused": sum(t["reused"] for t in traces),
            "api_or_validation_errors": sum(t["status"] == "error" for t in traces),
            "model_refusals": sum(t["status"] == "refused" for t in traces),
            "skipped": sum(t["status"] == "skipped" for t in traces),
            "has_model_response": any(t["status"] in {"answered", "refused"} for t in traces),
            "reported_response_models": sorted({t["response_model"] for t in traces if t["response_model"]}),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-file", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", type=Path, required=True)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/locomo10.json"))
    parser.add_argument("--memory-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-expansion-memories", type=int, default=50)
    parser.add_argument("--max-output-tokens", type=int, default=256)
    args = parser.parse_args()
    models = json.loads(args.models_file.read_text())["models"]
    if (not models or args.repeats < 1 or args.max_output_tokens < 1
            or not 1 <= args.top_k <= 50 or not 1 <= args.max_expansion_memories <= 200):
        raise ValueError("Require models, positive repeats and output budget")
    for model in models:
        if set(model) != {"provider", "model"}:
            raise ValueError("Models file accepts provider/model only; use environment variables for credentials")
        if model["provider"] not in {"deepseek", "openai", "glm"} or not model["model"].strip():
            raise ValueError("Specify the exact supported provider and model ID")
    if len({(m["provider"], m["model"]) for m in models}) != len(models):
        raise ValueError("Duplicate model configurations")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError("Choose a new empty output directory to preserve earlier results")
    cases = load_cases(args.cases)
    if not cases or any("expected_answer" not in c for c in cases):
        raise ValueError("Every QA case requires expected_answer (null for unanswerable)")
    raw = {s["sample_id"]: s for s in json.loads(args.raw.read_text())}
    store = MemoryStore(args.memory_dir)
    if any(c["sample_id"] not in raw or store.memories(c["sample_id"]) is None for c in cases):
        raise ValueError("Every sample needs both raw history and frozen Memory")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "models": models, "repeats": args.repeats, "top_k": args.top_k,
        "max_output_tokens": args.max_output_tokens, "max_expansion_memories": args.max_expansion_memories,
        "state_resolver": "rules", "prompt_policy": "backend.answer._Generator._INSTRUCTIONS",
        "input_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [*args.cases, args.raw, args.models_file]},
        "memory_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in args.memory_dir.glob("*.json")},
        "source_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [
            Path("backend/answer.py"), Path("backend/qa.py"), Path("backend/query.py"),
            Path("backend/dynamic_state/resolver.py"), Path("backend/retrieval/evidence.py"),
            Path("backend/retrieval/expansion.py"), Path("evaluation/final/qa_compare.py"),
            Path("evaluation/final/model_compare.py")]},
        "note": "No template final answers. All models see the same prepared evidence policy; identical inputs reuse one result within each model/run only. Token footprint and actual spend are separate. Missing API usage remains null.",
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
    retrievers = resolve_retrievers(["embedding", "hybrid"])
    grouped = {index: [] for index in range(len(models))}
    hashes = None
    for repeat in range(args.repeats):
        # Rotate the model order on repeats; each model/run has a fresh reuse cache.
        order = list(range(len(models)))
        order = order[repeat % len(order):] + order[:repeat % len(order)]
        for index in order:
            model = models[index]
            report = run_comparison(
                cases, store, raw,
                build_answer_generator(provider=model["provider"], model=model["model"],
                                       max_output_tokens=args.max_output_tokens),
                retrievers["embedding"], retrievers["hybrid"], RuleBasedDynamicStateResolver(),
                top_k=args.top_k, max_expansion_memories=args.max_expansion_memories,
            )
            current = [(row["sample_id"], row["question"], method, row[method]["generation"]["context_sha256"])
                       for row in report["cases"] for method in METHODS]
            if hashes is None:
                hashes = current
            elif current != hashes:
                raise RuntimeError("Evidence contexts changed between model runs")
            report["configuration"] = {**model, "repeat": repeat+1, "resolver": "rules",
                                       "max_output_tokens": args.max_output_tokens}
            slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model["model"])
            (args.output_dir / f"model-{index+1}-{slug}-run-{repeat+1}.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2)+"\n")
            grouped[index].append(report)
    summary = {f"{m['provider']}/{m['model']}": aggregate(grouped[i]) for i, m in enumerate(models)}
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n")
    lines = ["# LLM 模型对照结果", "", "Token 为 API usage，对相同输入复用的逻辑用量与实际请求消耗请查原始 JSON。", "",
             "| 模型 | 方法 | F1 | 输入 Token 均值 | 输出 Token 均值 | 错误 | 模型拒答 | 请求 / 复用 |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    def fmt(value):
        return f"{value:.3f}" if value is not None else "未报告"
    for model, methods in summary.items():
        for method, s in methods.items():
            f1 = fmt(s["mean_f1"]) if s["has_model_response"] else "无有效模型结果"
            lines.append(f"| {model} | {method} | {f1} | "
                         f"{fmt(s['token_footprint']['input_tokens']['mean_reported'])} | "
                         f"{fmt(s['token_footprint']['output_tokens']['mean_reported'])} | "
                         f"{s['api_or_validation_errors']} | {s['model_refusals']} | {s['api_calls']} / {s['reused']} |")
    (args.output_dir / "summary.md").write_text("\n".join(lines)+"\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
