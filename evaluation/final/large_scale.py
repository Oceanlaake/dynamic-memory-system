"""Generalized large-scale unified QA experiment.

Five methods per answer model:
  full_text   - complete original dialogue
  vector_rag  - pure-embedding Top-K, no rule hints
  state_topk  - Hybrid K=5 + rule hints (basic system)
  state_bonus - Hybrid K=5 + query-driven evidence expansion + rule hints
  state_k10   - Hybrid K=larger_k + rule hints (same-candidate-count control)

The runner is two-phase: it first plans every deterministic context without any
API call, then requests each unique (question, context) once per model with an
immediate per-request checkpoint, then replays the saved responses through the
formal scorer. Resume picks up saved requests, a circuit breaker stops on
consecutive API failures, and only transient API errors are retried.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, stdev
from time import perf_counter, sleep

from backend.answer import build_answer_generator
from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.qa import generation_summary
from backend.schemas import GenerationResult, GenerationTrace
from backend.store import MemoryStore
from evaluation.final.qa_compare import run_comparison
from evaluation.recall_at_k import load_cases, resolve_retrievers

METHODS = ("full_text", "vector_rag", "state_topk", "state_bonus", "state_k10")
METHOD_LABELS = {
    "full_text": "Full Text",
    "vector_rag": "Embedding K=5",
    "state_topk": "Hybrid K=5 + rules",
    "state_bonus": "K=5 + 补检 + rules",
    "state_k10": "Hybrid K=10 + rules",
}
TOKEN_FIELDS = (
    "input_tokens", "output_tokens", "total_tokens",
    "cached_input_tokens", "uncached_input_tokens", "reasoning_tokens",
)


def request_key(provider: str, model: str, prompt_sha: str, question: str,
                context: str, max_output_tokens: int) -> str:
    payload = "\x00".join([provider, model, prompt_sha, question, context,
                           str(max_output_tokens)])
    return hashlib.sha256(payload.encode()).hexdigest()


def dependency_versions() -> dict[str, str]:
    names = ("openai", "pydantic", "sentence-transformers", "fastapi", "numpy", "torch")
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    versions["python"] = sys.version.split()[0]
    return versions


class Planner:
    """Registers every unique answer context; makes no API call."""

    def __init__(self, provider: str, model: str, max_output_tokens: int, prompt_sha: str):
        self.provider, self.model = provider, model
        self.max_output_tokens, self.prompt_sha = max_output_tokens, prompt_sha
        self.tasks: dict[str, dict] = {}

    def generate(self, question: str, context: str) -> GenerationResult:
        key = request_key(self.provider, self.model, self.prompt_sha, question,
                          context, self.max_output_tokens)
        if key not in self.tasks:
            self.tasks[key] = {"question": question, "context": context}
        return GenerationResult(trace=GenerationTrace(
            provider=self.provider, model=self.model, status="refused",
            context_chars=len(context),
            context_sha256=hashlib.sha256((question + "\x00" + context).encode()).hexdigest(),
            max_output_tokens=self.max_output_tokens,
        ))


class Replay:
    """Serves checkpointed responses during formal scoring; marks reuse."""

    def __init__(self, provider: str, model: str, prompt_sha: str, max_output_tokens: int,
                 results: dict[str, GenerationResult]):
        self.provider, self.model = provider, model
        self.prompt_sha, self.max_output_tokens = prompt_sha, max_output_tokens
        self.results = results
        self.delivered: set[str] = set()

    def generate(self, question: str, context: str) -> GenerationResult:
        key = request_key(self.provider, self.model, self.prompt_sha, question,
                          context, self.max_output_tokens)
        if key not in self.results:
            raise RuntimeError(f"No checkpointed response for context {key[:12]}")
        result = self.results[key].model_copy(deep=True)
        if key in self.delivered:
            result.trace.api_called = False
            result.trace.reused = True
            result.trace.elapsed_ms = 0
        self.delivered.add(key)
        return result


def classify_failure(row: dict) -> str:
    trace = row.get("generation", {})
    status = trace.get("status", "error")
    error_code = trace.get("error_code")
    if status == "error":
        if error_code == "invalid_citation":
            return "invalid_citation"
        if error_code == "invalid_response":
            return "json_error"
        if error_code == "incomplete_response":
            return "truncated"
        if error_code == "api_error":
            return "api_error"
        return f"error:{error_code}"
    if status == "refused":
        return "refused"
    if status == "skipped":
        return f"skipped:{error_code}"
    if status == "answered":
        f1 = row.get("answer_f1")
        if f1 is not None and f1 >= 1.0 - 1e-12:
            return "correct"
        recall = row.get("evidence_set_recall")
        if recall is None:
            return "answered_wrong"
        if recall == 0.0:
            return "retrieval_miss"
        if recall < 1.0:
            return "partial_evidence"
        return "evidence_retrieved_but_wrong_answer"
    return f"unknown:{status}"


def method_metrics(cases: list[dict], method: str) -> dict:
    rows = [row[method] for row in cases]
    traces = [GenerationTrace.model_validate(r["generation"]) for r in rows]
    f1 = [r["answer_f1"] for r in rows if r.get("answer_f1") is not None]
    em = [r["answer_em"] for r in rows if r.get("answer_em") is not None]
    recalls = [r["evidence_set_recall"] for r in rows if r.get("evidence_set_recall") is not None]
    candidates = [len(r["candidate_memory_ids"]) for r in rows
                  if "candidate_memory_ids" in r]
    token_footprint = {}
    for field in TOKEN_FIELDS:
        values = [getattr(t.usage, field) for t in traces
                  if getattr(t.usage, field) is not None]
        token_footprint[field] = {
            "mean_reported": mean(values) if values else None,
            "reported_rows": len(values),
        }
    return {
        "cases": len(rows),
        "answerable_cases": sum(r.get("answerable", False) for r in rows),
        "mean_f1": mean(f1) if f1 else None,
        "mean_em": mean(em) if em else None,
        "mean_evidence_set_recall": mean(recalls) if recalls else None,
        "mean_candidates": mean(candidates) if candidates else None,
        "generation": generation_summary(traces),
        "token_footprint": token_footprint,
        "failure_types": dict(Counter(classify_failure(r) for r in rows)),
    }


def paired_delta(cases: list[dict], base: str, new: str) -> dict:
    deltas = []
    changes = []
    for row in cases:
        b, n = row[base], row[new]
        bf = b.get("answer_f1", 0.0) or 0.0
        nf = n.get("answer_f1", 0.0) or 0.0
        delta = nf - bf
        deltas.append(delta)
        if abs(delta) > 1e-12:
            changes.append({
                "case_id": row.get("case_id"),
                "sample_id": row.get("sample_id"),
                "question": row.get("question"),
                "expected_answer": row.get("expected_answer"),
                "delta_f1": delta,
                "base_answer": b.get("answer"),
                "new_answer": n.get("answer"),
                "base_f1": bf,
                "new_f1": nf,
            })
    return {
        "mean_delta_f1": mean(deltas) if deltas else None,
        "improved": sum(d > 1e-12 for d in deltas),
        "worsened": sum(d < -1e-12 for d in deltas),
        "unchanged": sum(abs(d) <= 1e-12 for d in deltas),
        "changes": sorted(changes, key=lambda r: -r["delta_f1"]),
    }


def write_markdown(out: Path, models: list[dict], summary: dict,
                   paired: dict, repeats: int) -> None:
    lines = [
        "# 大规模统一 LLM 对照结果",
        "",
        "F1/EM 为本地英文 token 归一化口径；错误、拒答与跳过均计 0 分。"
        "Token 为 API usage 的已报告行均值，未报告保持 null。",
        "",
        "## 表 1：模型 × 整体方法（回答质量与消耗）",
        "",
        "| 模型 | 方法 | F1 | EM | Memory 召回 | 平均候选 | 输入 Token | 输出 Token | 错误 | 拒答 | 跳过 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    fmt = lambda value, digits=3: f"{value:.{digits}f}" if value is not None else "—"
    for model in models:
        key = f"{model['provider']}/{model['model']}"
        methods = summary[key]
        for method in METHODS:
            s = methods[method]
            g = s["generation"]
            lines.append(
                f"| {key} | {METHOD_LABELS[method]} | {fmt(s['mean_f1'], 4)} | "
                f"{fmt(s['mean_em'], 4)} | {fmt(s['mean_evidence_set_recall'])} | "
                f"{fmt(s['mean_candidates'], 2)} | "
                f"{fmt(s['token_footprint']['input_tokens']['mean_reported'], 1)} | "
                f"{fmt(s['token_footprint']['output_tokens']['mean_reported'], 1)} | "
                f"{g['errors']} | {g['model_refusals']} | {g['skipped']} |"
            )
    lines += [
        "",
        "## 表 2：模型 × K5 / K10 / 补检（收益与成本）",
        "",
        "| 模型 | 方法 | F1 | 平均候选 | 输入 Token | 相对 K10 输入 Token |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for model in models:
        key = f"{model['provider']}/{model['model']}"
        methods = summary[key]
        k10_in = methods["state_k10"]["token_footprint"]["input_tokens"]["mean_reported"]
        for method in ("state_topk", "state_bonus", "state_k10"):
            s = methods[method]
            mean_in = s["token_footprint"]["input_tokens"]["mean_reported"]
            relative = None
            if mean_in is not None and k10_in:
                relative = (mean_in - k10_in) / k10_in * 100
            lines.append(
                f"| {key} | {METHOD_LABELS[method]} | {fmt(s['mean_f1'], 4)} | "
                f"{fmt(s['mean_candidates'], 2)} | {fmt(mean_in, 1)} | "
                f"{fmt(relative, 1)}% |"
            )
    lines += [
        "",
        "## 配对差异（新方案 − 基线，F1）",
        "",
        "| 模型 | 比较 | 平均 F1 差 | 上升 / 下降 / 不变 |",
        "|---|---|---:|---:|",
    ]
    pairs = [("vector_rag", "state_topk"), ("state_topk", "state_bonus"),
             ("state_k10", "state_bonus"), ("state_k10", "state_topk")]
    for model in models:
        key = f"{model['provider']}/{model['model']}"
        for base, new in pairs:
            p = paired[key][f"{new}_vs_{base}"]
            lines.append(
                f"| {key} | {METHOD_LABELS[new]} − {METHOD_LABELS[base]} | "
                f"{fmt(p['mean_delta_f1'], 4)} | "
                f"{p['improved']} / {p['worsened']} / {p['unchanged']} |"
            )
    lines += [
        "",
        f"重复轮次：{repeats}。以上为逐轮均值的简单汇总；轮间波动见 summary.json。",
        "",
    ]
    (out / "summary.md").write_text("\n".join(lines) + "\n")


def request_phase(out: Path, models: list[dict], tasks: dict[str, dict],
                  prompt_sha: str, max_output_tokens: int, *, max_retries: int,
                  circuit_breaker: int,
                  max_api_errors: int) -> tuple[dict[str, dict[str, GenerationResult]], dict[str, str]]:
    model_results: dict[str, dict[str, GenerationResult]] = {}
    blocked: dict[str, str] = {}
    attempt_log = out / "attempts.jsonl"
    with attempt_log.open("a") as log:
        for model in models:
            provider, model_id = model["provider"], model["model"]
            model_key = f"{provider}/{model_id}"
            slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model_id)
            requests_dir = out / "requests" / slug
            requests_dir.mkdir(parents=True, exist_ok=True)
            generator = build_answer_generator(
                provider=provider, model=model_id, max_output_tokens=max_output_tokens)
            prompt = getattr(generator, "_INSTRUCTIONS", None)
            if prompt is not None:
                actual_prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
                if actual_prompt_sha != prompt_sha:
                    raise RuntimeError("Prompt changed between plan and request; use a fresh output directory")
            saved = {p.stem: GenerationResult.model_validate_json(p.read_text())
                     for p in requests_dir.glob("*.json")}
            pending = [key for key in tasks if key not in saved]
            saved_api_errors = sum(1 for r in saved.values()
                                   if r.trace.error_code == "api_error")
            print(f"[{provider}/{model_id}] {len(saved)} saved, {len(pending)} pending",
                  flush=True)
            if saved_api_errors >= max_api_errors:
                blocked[model_key] = (
                    f"{saved_api_errors} saved API errors >= {max_api_errors}; "
                    f"model marked blocked (service busy or unavailable)")
                model_results[model_key] = saved
                print(f"BLOCKED {model_key}: {blocked[model_key]}", flush=True)
                continue
            try:
                consecutive_api_errors = 0
                total_api_errors = saved_api_errors
                started = perf_counter()
                for position, key in enumerate(pending, start=1):
                    task = tasks[key]
                    result = generator.generate(task["question"], task["context"])
                    attempts = 1
                    while result.trace.error_code == "api_error" and attempts < max_retries:
                        backoff = min(2 ** attempts, 30)
                        log.write(json.dumps({
                            "key": key, "provider": provider, "model": model_id,
                            "attempt": attempts, "status": result.trace.status,
                            "error_code": result.trace.error_code,
                            "http_status": result.trace.http_status,
                            "provider_error_code": result.trace.provider_error_code,
                        }) + "\n")
                        log.flush()
                        print(f"  retry {attempts}/{max_retries - 1} for {key[:12]} "
                              f"({result.trace.http_status}/{result.trace.provider_error_code})",
                              flush=True)
                        sleep(backoff)
                        result = generator.generate(task["question"], task["context"])
                        attempts += 1
                    log.write(json.dumps({
                        "key": key, "provider": provider, "model": model_id,
                        "attempt": attempts, "status": result.trace.status,
                        "error_code": result.trace.error_code,
                        "http_status": result.trace.http_status,
                        "provider_error_code": result.trace.provider_error_code,
                    }) + "\n")
                    log.flush()
                    (requests_dir / f"{key}.json").write_text(
                        result.model_dump_json(indent=2) + "\n")
                    saved[key] = result
                    if result.trace.error_code == "not_configured":
                        raise RuntimeError(
                            f"Credentials missing for {provider}/{model_id}; no requests were charged")
                    if result.trace.error_code == "api_error":
                        consecutive_api_errors += 1
                        total_api_errors += 1
                        if consecutive_api_errors >= circuit_breaker:
                            raise RuntimeError(
                                f"{circuit_breaker} consecutive API failures; "
                                f"stopped to inspect saved responses")
                        if total_api_errors >= max_api_errors:
                            raise RuntimeError(
                                f"{total_api_errors} API errors >= {max_api_errors}; "
                                f"model marked blocked (service busy or unavailable)")
                    else:
                        consecutive_api_errors = 0
                    if position % 10 == 0 or position == len(pending):
                        print(f"  saved {len(saved)}/{len(tasks)}; "
                              f"elapsed {perf_counter() - started:.1f}s", flush=True)
            except RuntimeError as exc:
                blocked[model_key] = str(exc)
                print(f"BLOCKED {model_key}: {exc}", flush=True)
            model_results[model_key] = saved
    return model_results, blocked


def run_once(out: Path, models: list[dict], cases: list[dict], store: MemoryStore,
             raw_by_sample: dict, embedding, hybrid, resolver, *, top_k: int,
             larger_k: int, max_expansion_memories: int, max_output_tokens: int,
             full_text_max_chars: int, max_retries: int, circuit_breaker: int,
             max_api_errors: int, plan_only: bool, manifest_extra: dict) -> dict:
    if out.exists() and any(out.iterdir()) and not (out / "manifest.json").exists():
        raise FileExistsError("Choose a new empty output directory to preserve earlier results")
    out.mkdir(parents=True, exist_ok=True)

    reference = build_answer_generator(
        provider=models[0]["provider"], model=models[0]["model"],
        max_output_tokens=max_output_tokens)
    prompt_sha = hashlib.sha256(reference._INSTRUCTIONS.encode()).hexdigest()

    planner = Planner(models[0]["provider"], models[0]["model"],
                      max_output_tokens, prompt_sha)
    run_comparison(cases, store, raw_by_sample, planner, embedding, hybrid, resolver,
                   top_k=top_k, max_expansion_memories=max_expansion_memories,
                   full_text_max_chars=full_text_max_chars, larger_k=larger_k)
    tasks = planner.tasks

    input_paths = []
    manifest = {
        "models": models, "repeats": 1, "top_k": top_k, "larger_k": larger_k,
        "max_output_tokens": max_output_tokens,
        "max_expansion_memories": max_expansion_memories,
        "full_text_max_chars": full_text_max_chars,
        "state_resolver": "rules",
        "prompt_policy": "backend.answer._Generator._INSTRUCTIONS",
        "prompt_sha256": prompt_sha,
        "case_count": len(cases),
        "unique_contexts": len(tasks),
        "dependencies": dependency_versions(),
        "note": "No template answers. All models see identical prepared evidence contexts; "
                "each unique input is requested once per model. Token footprint and actual "
                "spend are separate. Missing usage stays null. Sanitized raw text, finish "
                "reason and HTTP/provider error codes are kept in requests/.",
        **manifest_extra,
    }
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        comparable_keys = (
            "models", "prompt_sha256", "top_k", "larger_k", "max_output_tokens",
            "max_expansion_memories", "full_text_max_chars", "input_sha256",
            "memory_sha256", "case_count",
        )
        def _generation_hashes(manifest_doc: dict) -> dict:
            return {k: v for k, v in manifest_doc.get("source_sha256", {}).items()
                    if not k.endswith("large_scale.py")}
        if ({k: existing.get(k) for k in comparable_keys} !=
                {k: manifest.get(k) for k in comparable_keys} or
                _generation_hashes(existing) != _generation_hashes(manifest)):
            raise RuntimeError("Existing run manifest differs; use a new output directory")
    (out / "request-contexts.json").write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2) + "\n")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    if plan_only:
        return {"plan": {"unique_contexts": len(tasks)}}

    model_results, blocked = request_phase(
        out, models, tasks, prompt_sha, max_output_tokens,
        max_retries=max_retries, circuit_breaker=circuit_breaker,
        max_api_errors=max_api_errors,
    )
    if blocked:
        (out / "blocked.json").write_text(
            json.dumps(blocked, ensure_ascii=False, indent=2) + "\n")

    summary: dict[str, dict] = {}
    paired: dict[str, dict] = {}
    for model in models:
        key = f"{model['provider']}/{model['model']}"
        if key in blocked:
            continue
        results = model_results[key]
        # The planner keyed every unique context with a single run-level
        # namespace; models are isolated by the requests/<model-slug>/ directory,
        # so replay must reuse that same namespace to find the saved responses.
        replay = Replay(planner.provider, planner.model, prompt_sha,
                        max_output_tokens, results)
        report = run_comparison(cases, store, raw_by_sample, replay, embedding, hybrid,
                                resolver, top_k=top_k,
                                max_expansion_memories=max_expansion_memories,
                                full_text_max_chars=full_text_max_chars,
                                larger_k=larger_k)
        report["configuration"] = {**model, "resolver": "rules",
                                   "max_output_tokens": max_output_tokens,
                                   "larger_k": larger_k}
        slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model["model"])
        (out / f"model-{slug}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        for row in report["cases"]:
            row["expected_answer"] = next(
                (c["expected_answer"] for c in cases
                 if c["sample_id"] == row["sample_id"] and c["question"] == row["question"]),
                None)
        methods = {method: method_metrics(report["cases"], method) for method in METHODS}
        summary[key] = methods
        paired[key] = {f"{new}_vs_{base}": paired_delta(report["cases"], base, new)
                       for base, new in (("vector_rag", "state_topk"),
                                         ("state_topk", "state_bonus"),
                                         ("state_k10", "state_bonus"),
                                         ("state_k10", "state_topk"))}
        ledger = generation_summary([r.trace for r in results.values()])
        (out / f"actual-usage-{slug}.json").write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    (out / "summary.json").write_text(
        json.dumps({"summary": summary, "paired": paired, "blocked": blocked},
                   ensure_ascii=False, indent=2) + "\n")
    write_markdown(out, [m for m in models
                         if f"{m['provider']}/{m['model']}" not in blocked],
                   summary, paired, 1)
    return {"summary": summary, "paired": paired}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-file", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", type=Path, required=True)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/locomo10.json"))
    parser.add_argument("--memory-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--larger-k", type=int, default=10)
    parser.add_argument("--max-expansion-memories", type=int, default=50)
    parser.add_argument("--max-output-tokens", type=int, default=256)
    parser.add_argument("--full-text-max-chars", type=int, default=0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--circuit-breaker", type=int, default=5)
    parser.add_argument("--max-api-errors", type=int, default=20)
    parser.add_argument("--limit", type=int, default=0,
                        help="Only run the first N cases (for dev-subset pilots)")
    parser.add_argument("--plan-only", action="store_true",
                        help="Plan contexts and write manifest without any API call")
    args = parser.parse_args()

    models = json.loads(args.models_file.read_text())["models"]
    if not models or args.repeats < 1 or args.max_output_tokens < 1:
        raise ValueError("Require models, positive repeats and output budget")
    for model in models:
        if set(model) != {"provider", "model"}:
            raise ValueError("Models file accepts provider/model only; credentials live in env")
        if model["provider"] not in {"deepseek", "openai", "glm"} or not model["model"].strip():
            raise ValueError("Specify the exact supported provider and model ID")
    if len({(m["provider"], m["model"]) for m in models}) != len(models):
        raise ValueError("Duplicate model configurations")
    if not 1 <= args.top_k < args.larger_k <= 50:
        raise ValueError("require 1 <= top_k < larger_k <= 50")
    if not 1 <= args.max_expansion_memories <= 200:
        raise ValueError("max_expansion_memories must be between 1 and 200")

    cases = load_cases(args.cases)
    if args.limit:
        cases = cases[:args.limit]
    if not cases or any("expected_answer" not in c for c in cases):
        raise ValueError("Every QA case requires expected_answer")
    raw = {s["sample_id"]: s for s in json.loads(args.raw.read_text())}
    store = MemoryStore(args.memory_dir)
    if any(c["sample_id"] not in raw or store.memories(c["sample_id"]) is None for c in cases):
        raise ValueError("Every sample needs both raw history and frozen Memory")

    retrievers = resolve_retrievers(["embedding", "hybrid"])
    resolver = RuleBasedDynamicStateResolver()
    input_paths = [*args.cases, args.raw, args.models_file]
    memory_paths = sorted(args.memory_dir.glob("*.json"))
    source_paths = [
        Path("backend/answer.py"), Path("backend/qa.py"), Path("backend/query.py"),
        Path("backend/dynamic_state/resolver.py"), Path("backend/retrieval/evidence.py"),
        Path("backend/retrieval/expansion.py"), Path("evaluation/final/qa_compare.py"),
    ]
    manifest_extra = {
        "input_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in input_paths},
        "memory_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in memory_paths},
        "source_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in source_paths},
        "runner_sha256": hashlib.sha256(
            Path("evaluation/final/large_scale.py").read_bytes()).hexdigest(),
        "case_files": [str(p) for p in args.cases],
        "raw_file": str(args.raw),
        "memory_dir": str(store.directory),
        "limit": args.limit,
    }

    base = args.output_dir
    for repeat in range(args.repeats):
        out = base / f"run-{repeat + 1}" if args.repeats > 1 else base
        result = run_once(
            out, models, cases, store, raw, retrievers["embedding"],
            retrievers["hybrid"], resolver, top_k=args.top_k, larger_k=args.larger_k,
            max_expansion_memories=args.max_expansion_memories,
            max_output_tokens=args.max_output_tokens,
            full_text_max_chars=args.full_text_max_chars,
            max_retries=args.max_retries, circuit_breaker=args.circuit_breaker,
            max_api_errors=args.max_api_errors,
            plan_only=args.plan_only, manifest_extra=manifest_extra,
        )
        if args.plan_only:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        print(json.dumps({"repeat": repeat + 1, "output": str(out)},
                         ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
