"""Recall@K 对照实验：bm25 / embedding / hybrid 在同一批 case 上的召回表现。

用法：
    python -m evaluation.recall_at_k
    python -m evaluation.recall_at_k --retrievers bm25 embedding --ks 1,3,5
    python -m evaluation.recall_at_k --cases evaluation/cases/generated.json
    python -m evaluation.recall_at_k --json-out evaluation/results/recall.json
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
from evaluation.metrics import macro_average, rank_metrics

DEFAULT_CASES = Path("evaluation/cases/conv-30.json")


def load_cases(paths: list[Path]) -> list[dict]:
    cases: list[dict] = []
    for path in paths:
        cases.extend(json.loads(path.read_text(encoding="utf-8"))["cases"])
    return cases


def resolve_retrievers(names: list[str]) -> dict[str, Retriever]:
    """共用一个语义检索器，避免重复加载模型。"""
    semantic: SentenceTransformerRetriever | None = None
    resolved: dict[str, Retriever] = {}
    for name in names:
        if name == "bm25":
            resolved[name] = BM25Retriever()
        elif name in {"embedding", "hybrid"}:
            semantic = semantic or SentenceTransformerRetriever()
            resolved[name] = semantic if name == "embedding" else HybridRetriever(semantic=semantic)
        else:
            raise ValueError(f"unknown retriever: {name}")
    return resolved


def evaluate_case(case: dict, retriever: Retriever, store: MemoryStore, ks: list[int]) -> dict:
    memories = store.memories(case["sample_id"])
    if memories is None:
        raise ValueError(f"sample {case['sample_id']} not found in {store.directory}")

    result = retriever.retrieve(
        case["question"], memories, max(ks), sample_id=case["sample_id"]
    )
    ranking = [candidate.memory.memory_id for candidate in result.candidates]
    metrics = rank_metrics(ranking, case["required_memory_ids"], ks)
    return {
        "sample_id": case["sample_id"],
        "question": case["question"],
        "strategy": result.strategy,
        "degraded": result.degraded,
        "ranking": ranking,
        "recall": metrics["recall"],
        "mrr": metrics["mrr"],
    }


def run(cases: list[dict], retrievers: dict[str, Retriever], store: MemoryStore, ks: list[int]) -> dict:
    report: dict[str, dict] = {}
    for name, retriever in retrievers.items():
        rows = [evaluate_case(case, retriever, store, ks) for case in cases]
        aggregate = macro_average(rows, ks)
        report[name] = {
            "cases": rows,
            "macro_recall": aggregate["recall"],
            "mrr": aggregate["mrr"],
        }
    return report


def print_report(report: dict, ks: list[int]) -> None:
    header = f"{'case':<28}" + "".join(f"R@{k:<6}" for k in ks) + "MRR"
    for name, block in report.items():
        print(f"\n== {name} ==")
        print(header)
        for row in block["cases"]:
            cells = "".join(f"{row['recall'][k]:<8.2f}" for k in ks)
            print(f"{row['question'][:26]:<28}{cells}{row['mrr']:.2f}")
        cells = "".join(f"{block['macro_recall'][k]:<8.2f}" for k in ks)
        print(f"{'macro':<28}{cells}{block['mrr']:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, nargs="+", default=[DEFAULT_CASES])
    parser.add_argument("--retrievers", nargs="+", default=["bm25", "embedding", "hybrid"])
    parser.add_argument("--ks", default="1,3,5")
    parser.add_argument("--memory-dir", type=Path, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="json-out 只写聚合指标，省略逐题 ranking（避免数 MB 的产物）",
    )
    args = parser.parse_args()

    ks = [int(value) for value in args.ks.split(",") if value.strip()]
    cases = load_cases(args.cases)
    if not cases:
        raise SystemExit("no cases loaded")

    store = MemoryStore(args.memory_dir)
    report = run(cases, resolve_retrievers(args.retrievers), store, ks)
    print_report(report, ks)
    print(f"\ncases: {len(cases)}")

    if args.json_out:
        payload = report
        if args.summary_only:
            payload = {
                name: {
                    "macro_recall": block["macro_recall"],
                    "mrr": block["mrr"],
                    "case_count": len(block["cases"]),
                }
                for name, block in report.items()
            }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"written: {args.json_out}")


if __name__ == "__main__":
    main()
