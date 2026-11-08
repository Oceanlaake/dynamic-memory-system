"""Offline Graph Memory ablation: fixed Top-K versus bounded multi-hop expansion.

Gold Memory/evidence IDs are used only after retrieval for scoring.  Graph
construction and traversal receive the question, Top-K candidates, and the
sample's structured Memory store; they never receive QA labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from backend.graph_memory import expand_graph_memories
from backend.retrieval.base import Retriever
from backend.store import MemoryStore
from evaluation.recall_at_k import load_cases, resolve_retrievers


def _recall(found: set[str], required: set[str]) -> float | None:
    return len(found & required) / len(required) if required else None


def run(
    cases: list[dict],
    store: MemoryStore,
    retriever: Retriever,
    *,
    top_k: int = 5,
    max_hops: int = 3,
    max_graph_memories: int = 5,
) -> dict:
    if not cases:
        raise ValueError("cases must not be empty")
    rows = []
    for index, case in enumerate(cases):
        memories = store.memories(case["sample_id"])
        if memories is None:
            raise ValueError(f"Unknown sample: {case['sample_id']}")
        initial = retriever.retrieve(
            case["question"], memories, top_k, sample_id=case["sample_id"],
        )
        expanded, trace = expand_graph_memories(
            initial, memories, enabled=True, max_hops=max_hops,
            max_new_memories=max_graph_memories,
        )
        required = set(case.get("required_memory_ids", []))
        initial_ids = {candidate.memory.memory_id for candidate in initial.candidates}
        graph_ids = {candidate.memory.memory_id for candidate in expanded.candidates}
        source_turns = set(case.get("evidence", []))
        initial_turns = {
            ref.dia_id for candidate in initial.candidates for ref in candidate.memory.evidence
        }
        graph_turns = {
            ref.dia_id for candidate in expanded.candidates for ref in candidate.memory.evidence
        }
        rows.append({
            "case_id": case.get("case_id", str(index)),
            "sample_id": case["sample_id"],
            "question": case["question"],
            "fixed_k": {
                "candidate_count": len(initial_ids),
                "memory_recall": _recall(initial_ids, required),
                "source_turn_recall": _recall(initial_turns, source_turns),
            },
            "graph_memory": {
                "candidate_count": len(graph_ids),
                "memory_recall": _recall(graph_ids, required),
                "source_turn_recall": _recall(graph_turns, source_turns),
                "added_memory_ids": trace.added_memory_ids,
                "path_count": len(trace.paths),
                "visited_node_count": trace.visited_node_count,
                "truncated": trace.truncated,
                "stop_reason": trace.stop_reason,
            },
        })

    def mean_known(method: str, metric: str) -> float | None:
        values = [row[method][metric] for row in rows if row[method][metric] is not None]
        return sum(values) / len(values) if values else None

    summary = {}
    for method in ("fixed_k", "graph_memory"):
        summary[method] = {
            "cases": len(rows),
            "mean_memory_recall": mean_known(method, "memory_recall"),
            "mean_source_turn_recall": mean_known(method, "source_turn_recall"),
            "mean_candidate_count": sum(row[method]["candidate_count"] for row in rows) / len(rows),
        }
    summary["graph_memory"].update({
        "triggered_cases": sum(bool(row["graph_memory"]["added_memory_ids"]) for row in rows),
        "truncated_cases": sum(row["graph_memory"]["truncated"] for row in rows),
        "mean_visited_nodes": sum(row["graph_memory"]["visited_node_count"] for row in rows) / len(rows),
    })
    return {
        "configuration": {
            "retriever": retriever.name,
            "top_k": top_k,
            "max_hops": max_hops,
            "max_graph_memories": max_graph_memories,
            "gold_usage": "scoring_only",
        },
        "summary": summary,
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", type=Path, required=True)
    parser.add_argument("--memory-dir", type=Path, required=True)
    parser.add_argument("--retriever", choices=("bm25", "embedding", "hybrid"), default="hybrid")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-hops", type=int, default=3)
    parser.add_argument("--max-graph-memories", type=int, default=5)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    report = run(
        load_cases(args.cases), MemoryStore(args.memory_dir),
        resolve_retrievers([args.retriever])[args.retriever],
        top_k=args.top_k, max_hops=args.max_hops,
        max_graph_memories=args.max_graph_memories,
    )
    memory_paths = sorted(args.memory_dir.glob("*.json"))
    source_paths = [Path("backend/graph_memory.py"), Path("evaluation/graph_memory.py")]
    report["configuration"].update({
        "case_files": [str(path) for path in args.cases],
        "memory_dir": str(args.memory_dir),
        "case_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in args.cases
        },
        "memory_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in memory_paths
        },
        "source_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths
        },
    })
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"written: {args.json_out}")


if __name__ == "__main__":
    main()
