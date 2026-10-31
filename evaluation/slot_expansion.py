"""Controlled comparison of fixed K, larger K, and same-slot history expansion.

Uses the same query orchestration as HTTP. Gold annotations are used only for
scoring; neither retrieval nor expansion receives required/effective IDs.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from time import perf_counter

from backend.dynamic_state.base import DynamicStateResolver
from backend.dynamic_state.factory import build_dynamic_state_resolver
from backend.query import resolve_query
from backend.retrieval.base import Retriever
from backend.schemas import QueryResponse
from backend.store import MemoryStore
from evaluation.recall_at_k import load_cases, resolve_retrievers


def answer_f1(prediction: str | None, reference: str) -> float:
    """English token F1; disclose this normalization in the report, not official scoring."""
    def tokens(text: str) -> list[str]:
        return [t for t in re.findall(r"[a-z0-9]+", text.casefold()) if t not in {"a", "an", "the"}]

    predicted, expected = tokens(prediction or ""), tokens(reference)
    if not predicted or not expected:
        return float(predicted == expected)
    overlap = sum((Counter(predicted) & Counter(expected)).values())
    return 2 * overlap / (len(predicted) + len(expected))


def score_response(response: QueryResponse, case: dict) -> dict:
    required = set(case["required_memory_ids"])
    candidates = {c.memory.memory_id for c in response.candidate_memories}
    row = {
        "candidate_count": len(candidates),
        "candidate_memory_ids": [c.memory.memory_id for c in response.candidate_memories],
        "evidence_set_recall": len(required & candidates) / len(required),
        "answer": response.answer,
        "refused": response.answer is None,
        "effective_memory_ids": [m.memory_id for m in response.effective_memories],
        "evidence_status": response.evidence_status,
        "expansion": response.expansion.model_dump() if response.expansion else None,
        "resolver_calls": 1,
    }
    if case.get("evidence"):
        source_turns = set(case["evidence"])
        retrieved_turns = {
            ref.dia_id for candidate in response.candidate_memories
            for ref in candidate.memory.evidence
        }
        row["source_evidence_recall"] = len(source_turns & retrieved_turns) / len(source_turns)
    if "expected_effective_memory_ids" in case:
        row["effective_exact_match"] = (
            set(row["effective_memory_ids"]) == set(case["expected_effective_memory_ids"])
        )
    if "expected_answer" in case:
        reference = case["expected_answer"]
        row["answer_f1"] = (
            float(response.answer is None) if reference is None
            else answer_f1(response.answer, reference)
        )
    if "expected_relations" in case:
        predicted = {(r.from_, r.to): r.relation for r in response.relations}
        labels = case["expected_relations"]
        row["relation_correct"] = sum(
            predicted.get((r["from"], r["to"])) == r["relation"] for r in labels
        )
        row["relation_total"] = len(labels)
    return row


def run(
    cases: list[dict], store: MemoryStore, retriever: Retriever,
    resolver: DynamicStateResolver, *, top_k: int = 3, larger_k: int = 10,
    max_expansion_memories: int = 50,
) -> dict:
    if not cases:
        raise ValueError("cases must not be empty")
    if not 1 <= top_k < larger_k <= 50:
        raise ValueError("require 1 <= top_k < larger_k <= 50")
    if not 1 <= max_expansion_memories <= 200:
        raise ValueError("require 1 <= max_expansion_memories <= 200")

    # Validate every case before running any resolver/API calls.
    for case in cases:
        memories = store.memories(case["sample_id"])
        if memories is None:
            raise ValueError(f"Unknown sample: {case['sample_id']}")
        known = {m.memory_id for m in memories}
        required = set(case["required_memory_ids"])
        if not required or not required <= known:
            raise ValueError(f"Missing/unknown gold evidence in {case.get('case_id', case['question'])}")
        if not set(case.get("expected_effective_memory_ids", [])) <= known:
            raise ValueError("Unknown expected effective memory")
        for relation in case.get("expected_relations", []):
            if not {relation["from"], relation["to"]} <= known:
                raise ValueError("Unknown memory in expected relations")

    rows = []
    for index, case in enumerate(cases):
        memories = store.memories(case["sample_id"])
        assert memories is not None
        started = perf_counter()
        initial = retriever.retrieve(case["question"], memories, top_k, sample_id=case["sample_id"])
        initial_ms = (perf_counter() - started) * 1000
        variants = {}
        for name, k, expand in [("fixed_k", top_k, False), ("larger_k", larger_k, False),
                                ("slot_expansion", top_k, True)]:
            started = perf_counter()
            retrieval = initial if k == top_k else retriever.retrieve(
                case["question"], memories, k, sample_id=case["sample_id"],
            )
            response = resolve_query(
                retrieval, memories, resolver, expand_slots=expand,
                max_expansion_memories=max_expansion_memories,
            )
            row = score_response(response, case)
            row["latency_ms"] = (perf_counter() - started) * 1000 + (initial_ms if k == top_k else 0)
            row["strategy"] = retrieval.strategy
            row["degraded"] = response.degraded
            variants[name] = row
        rows.append({"case_id": case.get("case_id", str(index)), "sample_id": case["sample_id"],
                     "question": case["question"], "variants": variants})

    summary = {}
    for name in ("fixed_k", "larger_k", "slot_expansion"):
        selected = [row["variants"][name] for row in rows]
        block = {
            "cases": len(selected),
            "mean_evidence_set_recall": sum(r["evidence_set_recall"] for r in selected) / len(selected),
            "mean_candidate_count": sum(r["candidate_count"] for r in selected) / len(selected),
            "mean_latency_ms": sum(r["latency_ms"] for r in selected) / len(selected),
            "refusals": sum(r["refused"] for r in selected),
            "resolver_calls": len(selected),
            "degraded_count": sum(r["degraded"] for r in selected),
        }
        for metric in ("effective_exact_match", "answer_f1", "source_evidence_recall"):
            annotated = [r[metric] for r in selected if metric in r]
            block[f"{metric}_annotated_cases"] = len(annotated)
            block[f"mean_{metric}"] = sum(annotated) / len(annotated) if annotated else None
        total = sum(r.get("relation_total", 0) for r in selected)
        block["relation_annotated_pairs"] = total
        block["relation_accuracy"] = (
            sum(r.get("relation_correct", 0) for r in selected) / total if total else None
        )
        summary[name] = block
    return {
        "configuration": {"top_k": top_k, "larger_k": larger_k,
                          "max_expansion_memories": max_expansion_memories,
                          "f1_normalization": "lowercase ASCII alphanumeric tokens; remove a/an/the",
                          "latency_note": "shared initial retrieval; includes its time in both K variants; warm caches may affect results",
                          "llm_call_count": "not instrumented; resolver_calls is not LLM calls"},
        "summary": summary, "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", type=Path, required=True)
    parser.add_argument("--memory-dir", type=Path, default=None)
    parser.add_argument("--retriever", choices=("bm25", "embedding", "hybrid"), default="bm25")
    parser.add_argument("--resolver", choices=("rules", "hybrid"), default="rules")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--larger-k", type=int, default=10)
    parser.add_argument("--max-expansion-memories", type=int, default=50)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    report = run(
        load_cases(args.cases), MemoryStore(args.memory_dir),
        resolve_retrievers([args.retriever])[args.retriever],
        build_dynamic_state_resolver(mode=args.resolver), top_k=args.top_k,
        larger_k=args.larger_k, max_expansion_memories=args.max_expansion_memories,
    )
    report["configuration"].update({
        "case_files": [str(path) for path in args.cases],
        "memory_dir": str(MemoryStore(args.memory_dir).directory),
        "retriever": args.retriever, "resolver": args.resolver,
    })
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
