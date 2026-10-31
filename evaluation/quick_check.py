"""Exploratory evaluation on a previously used conversation; not a held-out test.

Example (cached embedding model only):
HF_HUB_OFFLINE=1 .venv/bin/python -m evaluation.quick_check
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.store import MemoryStore
from evaluation.build_cases import build_cases, parse_evidence
from evaluation.recall_at_k import resolve_retrievers
from evaluation.slot_expansion import run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", default="conv-30")
    parser.add_argument("--retrievers", nargs="+", default=["bm25", "hybrid"])
    parser.add_argument("--raw", type=Path, default=Path("data/raw/locomo10.json"))
    parser.add_argument("--memory-dir", type=Path, default=Path("outputs/memories"))
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/results/bonus_quick_check"))
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--larger-k", type=int, default=10)
    args = parser.parse_args()
    store = MemoryStore(args.memory_dir)
    memories = store.memories(args.sample)
    if not memories:
        raise ValueError(f"No extracted memories for {args.sample}")
    samples = [s for s in json.loads(args.raw.read_text()) if s.get("sample_id") == args.sample]
    cases, stats = build_cases(samples, {args.sample: memories}, {1, 2, 3, 4})
    known_turns = {ref.dia_id for memory in memories for ref in memory.evidence}
    for index, case in enumerate(cases):
        case["case_id"] = f"{args.sample}-qa-{index:03d}"
        case["evidence"] = parse_evidence(case["evidence"])
        case["all_source_turns_mapped"] = set(case["evidence"]) <= known_turns
        # Gold answers are scoring-only. Do not synthesize state/relation labels.
        if isinstance(case.get("answer"), (str, int, float)):
            case["expected_answer"] = str(case["answer"])
    provenance = {
        "purpose": "exploratory, previously used conversation; not official held-out evaluation",
        "sample_id": args.sample, "raw_file": str(args.raw), "memory_dir": str(args.memory_dir),
        "memory_count": len(memories), "case_generation": stats,
        "fully_mapped_cases": sum(c["all_source_turns_mapped"] for c in cases),
        "memory_gold_note": "all extracted memories citing any gold evidence turn; automatic proxy, not manual state labels",
        "answer_scoring_note": "local English token F1; raw memory-content answers may score low despite containing the answer",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "cases.json").write_text(
        json.dumps({"provenance": provenance, "cases": cases}, ensure_ascii=False, indent=2)+"\n",
    )
    print(json.dumps(provenance, ensure_ascii=False), flush=True)
    for name, retriever in resolve_retrievers(args.retrievers).items():
        report = run(cases, store, retriever, RuleBasedDynamicStateResolver(),
                     top_k=args.top_k, larger_k=args.larger_k)
        report["configuration"].update({**provenance, "retriever": name, "resolver": "rules"})
        (args.output_dir / f"{name}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2)+"\n",
        )
        print(json.dumps({"retriever": name, "summary": report["summary"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
