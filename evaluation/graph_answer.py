"""Paired answer-quality evaluation for fixed K and Graph Memory policies.

The two methods share the same Hybrid Top-K seeds, rule resolver, answer model,
prompt, and scorer.  Only bounded Graph Memory expansion differs.  The runner
plans deterministic contexts first, checkpoints every external response, and
can resume an interrupted run without repeating completed API calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from backend.answer import build_answer_generator
from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.qa import answer_query, labeled_memory_context
from backend.store import MemoryStore
from evaluation.final.large_scale import (
    Planner,
    Replay,
    dependency_versions,
    method_metrics,
    paired_delta,
    request_phase,
)
from evaluation.recall_at_k import load_cases, resolve_retrievers
from evaluation.slot_expansion import score_response

METHODS = ("fixed_k", "graph_memory", "adaptive_graph")


def run_pair(
    cases: list[dict], store: MemoryStore, retriever, resolver, generator, *,
    top_k: int = 5, max_hops: int = 3, max_graph_memories: int = 5,
) -> dict:
    if not cases or any("expected_answer" not in case for case in cases):
        raise ValueError("Every non-empty QA case set requires expected_answer")
    if not 1 <= top_k <= 50 or not 1 <= max_hops <= 4:
        raise ValueError("Require 1 <= top_k <= 50 and 1 <= max_hops <= 4")
    if not 1 <= max_graph_memories <= 50:
        raise ValueError("max_graph_memories must be between 1 and 50")

    rows = []
    cache = {}
    for index, case in enumerate(cases):
        memories = store.memories(case["sample_id"])
        if memories is None:
            raise ValueError(f"Unknown sample: {case['sample_id']}")
        initial = retriever.retrieve(
            case["question"], memories, top_k, sample_id=case["sample_id"],
        )
        row = {
            "case_id": case.get("case_id", str(index)),
            "sample_id": case["sample_id"],
            "question": case["question"],
            "expected_answer": case["expected_answer"],
            "required_memory_ids": case.get("required_memory_ids", []),
        }
        for method, enabled, retry_on_refusal in (
            ("fixed_k", False, False),
            ("graph_memory", True, False),
            ("adaptive_graph", True, True),
        ):
            response = answer_query(
                initial, memories, resolver, generator,
                graph_expand=enabled, graph_max_hops=max_hops,
                max_graph_memories=max_graph_memories,
                graph_retry_on_refusal=retry_on_refusal, cache=cache,
            )
            scored = score_response(response, case)
            scored["answerable"] = case["expected_answer"] is not None
            scored["context_chars"] = len(labeled_memory_context(response))
            scored["graph"] = response.graph.model_dump() if response.graph else None
            row[method] = scored
        rows.append(row)
    return {"cases": rows}


def summarize(report: dict) -> dict:
    cases = report["cases"]
    return {
        "methods": {method: method_metrics(cases, method) for method in METHODS},
        "paired": paired_delta(cases, "fixed_k", "graph_memory"),
        "paired_adaptive": paired_delta(cases, "fixed_k", "adaptive_graph"),
    }


def _hashes(paths: list[Path]) -> dict[str, str]:
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", type=Path, required=True)
    parser.add_argument("--memory-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--provider", choices=("deepseek", "openai", "glm"), default="deepseek")
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-hops", type=int, default=3)
    parser.add_argument("--max-graph-memories", type=int, default=5)
    parser.add_argument("--max-output-tokens", type=int, default=128)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--circuit-breaker", type=int, default=5)
    parser.add_argument("--max-api-errors", type=int, default=20)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    if args.limit:
        cases = cases[:args.limit]
    store = MemoryStore(args.memory_dir)
    retriever = resolve_retrievers(["hybrid"])["hybrid"]
    resolver = RuleBasedDynamicStateResolver()
    reference = build_answer_generator(
        provider=args.provider, model=args.model, max_output_tokens=args.max_output_tokens,
    )
    prompt_sha = hashlib.sha256(reference._INSTRUCTIONS.encode()).hexdigest()
    planner = Planner(args.provider, args.model, args.max_output_tokens, prompt_sha)
    planned = run_pair(
        cases, store, retriever, resolver, planner, top_k=args.top_k,
        max_hops=args.max_hops, max_graph_memories=args.max_graph_memories,
    )

    out = args.output_dir
    if out.exists() and any(out.iterdir()) and not (out / "manifest.json").exists():
        raise FileExistsError("Choose a new empty output directory")
    out.mkdir(parents=True, exist_ok=True)
    source_paths = [
        Path("backend/answer.py"), Path("backend/graph_memory.py"), Path("backend/qa.py"),
        Path("backend/query.py"), Path("evaluation/graph_answer.py"),
    ]
    manifest = {
        "provider": args.provider,
        "model": args.model,
        "case_count": len(cases),
        "unique_contexts": len(planner.tasks),
        "top_k": args.top_k,
        "max_hops": args.max_hops,
        "max_graph_memories": args.max_graph_memories,
        "max_output_tokens": args.max_output_tokens,
        "prompt_sha256": prompt_sha,
        "gold_usage": "answer_scoring_only",
        "case_sha256": _hashes(args.cases),
        "memory_sha256": _hashes(sorted(args.memory_dir.glob("*.json"))),
        "source_sha256": _hashes(source_paths),
        "dependencies": dependency_versions(),
    }
    manifest_path = out / "manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise RuntimeError("Existing manifest differs; use a new output directory")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (out / "request-contexts.json").write_text(
        json.dumps(planner.tasks, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps({"cases": len(cases), "unique_contexts": len(planner.tasks)}, indent=2))
    if args.plan_only:
        return

    model_key = f"{args.provider}/{args.model}"
    results, blocked = request_phase(
        out, [{"provider": args.provider, "model": args.model}], planner.tasks,
        prompt_sha, args.max_output_tokens, max_retries=args.max_retries,
        circuit_breaker=args.circuit_breaker, max_api_errors=args.max_api_errors,
    )
    if blocked:
        (out / "blocked.json").write_text(json.dumps(blocked, indent=2) + "\n")
        raise SystemExit(f"Graph answer evaluation blocked: {blocked[model_key]}")

    replay = Replay(args.provider, args.model, prompt_sha, args.max_output_tokens, results[model_key])
    report = run_pair(
        cases, store, retriever, resolver, replay, top_k=args.top_k,
        max_hops=args.max_hops, max_graph_memories=args.max_graph_memories,
    )
    report["configuration"] = manifest
    report["summary"] = summarize(report)
    (out / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    (out / "summary.json").write_text(
        json.dumps(report["summary"], ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
