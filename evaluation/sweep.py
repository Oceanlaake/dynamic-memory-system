"""扫描 hybrid 的融合权重，并与纯 bm25 / 纯 embedding 对照。

用于回答两个问题：词法该占多少权重？K 取多少够用？

用法：
    python -m evaluation.sweep --cases evaluation/cases/generated.json
    python -m evaluation.sweep --weights 0,0.2,0.4,0.6,0.8,1.0 --ks 1,3,5,10
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.retrieval.base import Retriever
from backend.retrieval.embedding import SentenceTransformerRetriever
from backend.retrieval.hybrid import HybridRetriever
from backend.retrieval.keyword import BM25Retriever
from backend.store import MemoryStore
from evaluation.metrics import macro_average
from evaluation.recall_at_k import DEFAULT_CASES, evaluate_case, load_cases

DEFAULT_WEIGHTS = "0,0.2,0.4,0.6,0.8,1"


def build_candidates(weights: list[float]) -> dict[str, Retriever]:
    lexical = BM25Retriever()
    semantic = SentenceTransformerRetriever(min_score=0.0)
    candidates: dict[str, Retriever] = {
        "bm25": lexical,
        "embedding": semantic,
    }
    for weight in weights:
        candidates[f"hybrid(w={weight:g})"] = HybridRetriever(
            lexical=lexical,
            semantic=semantic,
            lexical_weight=weight,
            min_score=0.0,
        )
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, nargs="+", default=[DEFAULT_CASES])
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS)
    parser.add_argument("--ks", default="1,3,5,10")
    parser.add_argument("--memory-dir", type=Path, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    ks = [int(value) for value in args.ks.split(",") if value.strip()]
    weights = [float(value) for value in args.weights.split(",") if value.strip()]
    cases = load_cases(args.cases)
    if not cases:
        raise SystemExit("no cases loaded")
    if len(cases) < 20:
        print(f"WARNING: only {len(cases)} case(s); 参数结论不可靠，仅验证管道可跑。\n")

    store = MemoryStore(args.memory_dir)
    report: dict[str, dict] = {}
    for name, retriever in build_candidates(weights).items():
        rows = [evaluate_case(case, retriever, store, ks) for case in cases]
        aggregate = macro_average(rows, ks)
        report[name] = {"macro_recall": aggregate["recall"], "mrr": aggregate["mrr"]}

    header = f"{'strategy':<20}" + "".join(f"R@{k:<6}" for k in ks) + "MRR"
    print(header)
    for name, block in report.items():
        cells = "".join(f"{block['macro_recall'][k]:<8.3f}" for k in ks)
        print(f"{name:<20}{cells}{block['mrr']:.3f}")

    best = max(report, key=lambda name: (report[name]["macro_recall"][ks[-1]], report[name]["mrr"]))
    print(f"\nbest by R@{ks[-1]}, MRR: {best}")
    print(f"cases: {len(cases)}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"written: {args.json_out}")


if __name__ == "__main__":
    main()
