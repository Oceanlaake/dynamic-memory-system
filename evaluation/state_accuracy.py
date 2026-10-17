"""B2 relation-label accuracy evaluation.

Examples:
    python -m evaluation.state_accuracy
    python -m evaluation.state_accuracy --resolver hybrid --model gpt-5-mini
    python -m evaluation.state_accuracy --json-out evaluation/results/state_accuracy.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from backend.dynamic_state.base import DynamicStateResolver
from backend.dynamic_state.factory import build_dynamic_state_resolver
from backend.schemas import CandidateMemory, Memory, RetrievalResult

LABELS = ("RETAIN", "UPDATE", "SUPERSEDE", "CONFLICT")
DEFAULT_CASES = (
    Path("evaluation/cases/b2_relations.json"),
    Path("evaluation/cases/b2_relations_challenge.json"),
)


def load_cases(paths: Sequence[Path]) -> list[dict]:
    cases: list[dict] = []
    for path in paths:
        cases.extend(json.loads(path.read_text(encoding="utf-8"))["cases"])
    return cases


def evaluate_case(case: dict, resolver: DynamicStateResolver) -> dict:
    first = Memory.model_validate(case["first_memory"])
    second = Memory.model_validate(case["second_memory"])
    retrieval = RetrievalResult(
        sample_id=case["sample_id"],
        question=case["question"],
        top_k=2,
        strategy="bm25",
        candidates=[
            CandidateMemory(memory=first, score=1.0, rank=1),
            CandidateMemory(memory=second, score=0.9, rank=2),
        ],
    )
    response = resolver.resolve(retrieval)
    relation = next(
        (
            item
            for item in response.relations
            if {item.from_, item.to} == {first.memory_id, second.memory_id}
        ),
        None,
    )
    predicted = relation.relation if relation else None
    expected = case["expected_relation"]
    return {
        "case_id": case["case_id"],
        "sample_id": case["sample_id"],
        "expected": expected,
        "predicted": predicted,
        "correct": predicted == expected,
        "reason": relation.reason if relation else None,
    }


def build_report(cases: Sequence[dict], resolver: DynamicStateResolver) -> dict:
    if not cases:
        raise ValueError("cases must not be empty")
    rows = [evaluate_case(case, resolver) for case in cases]
    per_label: dict[str, dict[str, float | int]] = {}
    for label in LABELS:
        selected = [row for row in rows if row["expected"] == label]
        correct = sum(row["correct"] for row in selected)
        per_label[label] = {
            "correct": correct,
            "total": len(selected),
            "accuracy": correct / len(selected) if selected else 0.0,
        }

    prediction_labels = (*LABELS, "NONE")
    confusion = {
        expected: {predicted: 0 for predicted in prediction_labels}
        for expected in LABELS
    }
    for row in rows:
        confusion[row["expected"]][row["predicted"] or "NONE"] += 1

    correct = sum(row["correct"] for row in rows)
    return {
        "cases": rows,
        "summary": {
            "correct": correct,
            "total": len(rows),
            "accuracy": correct / len(rows),
            "no_prediction": sum(row["predicted"] is None for row in rows),
            "per_label": per_label,
            "confusion_matrix": confusion,
        },
    }


def print_report(report: dict) -> None:
    print(f"{'case':<40} {'expected':<11} {'predicted':<11} result")
    for row in report["cases"]:
        result = "PASS" if row["correct"] else "FAIL"
        print(
            f"{row['case_id'][:38]:<40} {row['expected']:<11} "
            f"{(row['predicted'] or 'NONE'):<11} {result}"
        )
    summary = report["summary"]
    print(
        f"\naccuracy: {summary['correct']}/{summary['total']} "
        f"({summary['accuracy']:.2%}), no prediction: {summary['no_prediction']}"
    )
    print("\nper-label accuracy:")
    for label, metrics in summary["per_label"].items():
        print(
            f"  {label:<10} {metrics['correct']}/{metrics['total']} "
            f"({metrics['accuracy']:.2%})"
        )
    print("\nconfusion matrix (rows=expected, columns=predicted):")
    prediction_labels = (*LABELS, "NONE")
    print(f"{'':<12}" + "".join(f"{label[:6]:>8}" for label in prediction_labels))
    for expected, counts in summary["confusion_matrix"].items():
        print(f"{expected:<12}" + "".join(f"{counts[label]:>8}" for label in prediction_labels))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, nargs="+", default=list(DEFAULT_CASES))
    parser.add_argument("--resolver", choices=("rules", "hybrid"), default="rules")
    parser.add_argument("--provider", choices=("openai", "deepseek"), default=None)
    parser.add_argument("--model", default=None, help="Model override; otherwise use environment/default")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    cases = load_cases(args.cases)
    resolver = build_dynamic_state_resolver(
        mode=args.resolver,
        provider=args.provider,
        model=args.model,
    )
    report = build_report(cases, resolver)
    print_report(report)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"written: {args.json_out}")


if __name__ == "__main__":
    main()
