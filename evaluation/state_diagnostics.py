"""Run provisional, source-audited diagnostics on full history prefixes.

Only evaluation fixtures/scoring are added. This runner does not normalize or
rewrite production memories, tune retrieval, or pass labels to the resolver.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from backend.dynamic_state import RuleBasedDynamicStateResolver
from backend.schemas import Memory
from backend.store import MemoryStore
from evaluation.recall_at_k import resolve_retrievers
from evaluation.slot_expansion import run


def session_number(session: str) -> int:
    match = re.fullmatch(r"session_(\d+)", session)
    if not match:
        raise ValueError(f"Unexpected session ID: {session}")
    return int(match.group(1))


def before_cutoff(memory: Memory, cutoff: int) -> bool:
    return (session_number(memory.time.session_id) <= cutoff
            and all(session_number(ref.session_id) <= cutoff for ref in memory.evidence))


def audit_case(case: dict, variant: dict, by_id: dict[str, Memory]) -> None:
    """Transparent diagnostics, not a general semantic answer evaluator."""
    effective_ids = set(variant["effective_memory_ids"])
    effective_turns = {ref.dia_id for key in effective_ids for ref in by_id[key].evidence}
    source = set(case["evidence"])
    variant["effective_source_recall"] = len(source & effective_turns) / len(source)
    expected_refusal = case["expected_refusal"]
    variant["refusal_behavior_match"] = variant["refused"] == expected_refusal
    if "acceptable_effective_memory_sets" in case:
        variant["provisional_effective_set_match"] = any(
            effective_ids == set(acceptable) for acceptable in case["acceptable_effective_memory_sets"]
        )
    if expected_refusal:
        variant["diagnostic_pass"] = variant["refused"]
        return
    answer = variant["answer"] or ""
    pattern_hits = {pattern: bool(re.search(pattern, answer, re.I)) for pattern in case["answer_patterns"]}
    variant["answer_pattern_hits"] = pattern_hits
    variant["answer_pattern_pass"] = bool(answer) and all(pattern_hits.values())
    source_pass = variant.get("provisional_effective_set_match",
                              variant["effective_source_recall"] == 1)
    variant["diagnostic_pass"] = variant["answer_pattern_pass"] and source_pass


def summarize_audit(rows: list[dict], cases_by_id: dict[str, dict]) -> dict:
    summary = {}
    for name in ("fixed_k", "larger_k", "slot_expansion"):
        variants = [row["variants"][name] for row in rows]
        answerable = [row["variants"][name] for row in rows
                      if not cases_by_id[row["case_id"]]["expected_refusal"]]
        unanswerable = [row["variants"][name] for row in rows
                        if cases_by_id[row["case_id"]]["expected_refusal"]]
        block = {
            "provisional_diagnostic_passes": sum(v["diagnostic_pass"] for v in variants),
            "cases": len(rows),
            "answerable_cases": len(answerable),
            "answerable_refusals": sum(v["refused"] for v in answerable),
            "unanswerable_cases": len(unanswerable),
            "correct_unanswerable_refusals": sum(v["refused"] for v in unanswerable),
            "answer_pattern_passes": sum(v["answer_pattern_pass"] for v in answerable),
            "mean_effective_source_recall": sum(v["effective_source_recall"] for v in variants) / len(variants),
            "by_category": {},
        }
        for category in sorted({c["diagnostic_category"] for c in cases_by_id.values()}):
            subset = [row["variants"][name] for row in rows
                      if cases_by_id[row["case_id"]]["diagnostic_category"] == category]
            block["by_category"][category] = {
                "passes": sum(v["diagnostic_pass"] for v in subset), "cases": len(subset),
            }
        summary[name] = block
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("evaluation/cases/state_diagnostics.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/results/state_diagnostics"))
    parser.add_argument("--retrievers", nargs="+", default=["bm25", "hybrid"])
    args = parser.parse_args()
    fixture = json.loads(args.cases.read_text())
    cases = fixture["cases"]
    source_path = Path(fixture["source_memories"])
    source = json.loads(source_path.read_text())
    memories = [Memory.model_validate(m) for m in source["memories"]]
    by_id = {m.memory_id: m for m in memories}
    raw = next(sample for sample in json.loads(Path(fixture["source_raw"]).read_text())
               if sample["sample_id"] == source["sample_id"])
    turns = {t["dia_id"]: {**t, "session_id": key,
                          "session_date_time": raw["conversation"][f"{key}_date_time"]}
             for key, value in raw["conversation"].items() if isinstance(value, list)
             for t in value}
    official_questions = {qa["question"] for qa in raw["qa"]}
    for case in cases:
        if case["question_origin"] == "original_qa" and case["question"] not in official_questions:
            raise ValueError(f"Question mislabeled as original QA: {case['case_id']}")
        for key in case["required_memory_ids"]:
            if key not in by_id or not before_cutoff(by_id[key], case["cutoff_session"]):
                raise ValueError(f"Gold memory outside snapshot: {case['case_id']}: {key}")
        for group in case.get("acceptable_effective_memory_sets", []):
            if not group or not all(key in by_id and before_cutoff(by_id[key], case["cutoff_session"])
                                    for key in group):
                raise ValueError("Invalid effective-memory alternative")
        for dia_id in case["evidence"]:
            if session_number(turns[dia_id]["session_id"]) > case["cutoff_session"]:
                raise ValueError("Future evidence leaked into snapshot")
        for pattern in case["answer_patterns"]:
            re.compile(pattern)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    provenance = {
        **{k: v for k, v in fixture.items() if k != "cases"},
        "source_memory_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        "categories": dict(Counter(c["diagnostic_category"] for c in cases)),
        "question_origins": dict(Counter(c["question_origin"] for c in cases)),
        "annotation_warning": "Provisional assistant labels and explicit regex checks; not human-validated accuracy or official held-out performance",
    }
    # A temporary store provides the unchanged run() pipeline with full prefixes.
    # Persist only the manifest and source quotes; all snapshots can be regenerated.
    with TemporaryDirectory(prefix="state-diagnostics-") as temp:
        counts = {}
        for cutoff in sorted({c["cutoff_session"] for c in cases}):
            sample_id = f"conv-30-through-{cutoff:02d}"
            selected = [m for m in memories if before_cutoff(m, cutoff)]
            counts[sample_id] = len(selected)
            Path(temp, f"{sample_id}.json").write_text(json.dumps({
                "sample_id": sample_id, "memories": [m.model_dump() for m in selected],
            }))
        provenance["snapshot_memory_counts"] = counts
        source_audit = [
            {"case_id": c["case_id"], "question": c["question"], "cutoff_session": c["cutoff_session"],
             "reference_answer": c.get("expected_answer"), "expected_refusal": c["expected_refusal"],
             "annotation_note": c["annotation_note"],
             "source_turns": [turns[key] for key in c["evidence"]]}
            for c in cases
        ]
        (args.output_dir / "source_audit.json").write_text(json.dumps({
            "provenance": provenance, "cases": source_audit,
        }, ensure_ascii=False, indent=2)+"\n")
        cases_by_id = {c["case_id"]: c for c in cases}
        store = MemoryStore(temp)
        for name, retriever in resolve_retrievers(args.retrievers).items():
            report = run(cases, store, retriever, RuleBasedDynamicStateResolver(), top_k=3, larger_k=10)
            for row in report["cases"]:
                for variant in row["variants"].values():
                    audit_case(cases_by_id[row["case_id"]], variant, by_id)
            report["diagnostic_summary"] = summarize_audit(report["cases"], cases_by_id)
            report["configuration"].update({"provenance": provenance, "retriever": name, "resolver": "rules"})
            (args.output_dir / f"{name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
            print(json.dumps({"retriever": name, "summary": report["summary"],
                              "diagnostics": report["diagnostic_summary"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
