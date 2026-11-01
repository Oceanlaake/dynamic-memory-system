"""Unified QA comparison: Full Text / Vector RAG / state-system variants.

Every method shares one LLM answer generator and one scoring script; only the
context differs. Full Text receives the complete original dialogue, Vector RAG
receives pure-embedding Top-K memories, and the state-system variants receive
the Hybrid Top-K candidate set annotated with the resolver's state labels
(current / historical / conflicting).

This is the missing T04 baseline entry. It requires the course question list
and annotations before its numbers can be reported as an official result.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from backend.answer import build_answer_generator
from backend.dynamic_state.base import DynamicStateResolver
from backend.dynamic_state.factory import build_dynamic_state_resolver
from backend.query import resolve_query
from backend.retrieval.base import Retriever
from backend.schemas import Memory
from backend.store import MemoryStore
from evaluation.recall_at_k import load_cases, resolve_retrievers
from evaluation.slot_expansion import answer_f1

_SESSION_RE = re.compile(r"^session_(\d+)$")


def build_full_text_context(sample: dict, *, max_chars: int = 0) -> tuple[str, int, bool]:
    """Render one LoCoMo sample's complete dialogue as plain text."""

    conversation = sample.get("conversation")
    if not isinstance(conversation, dict):
        raise ValueError(f"sample {sample.get('sample_id')} has no conversation dict")
    session_keys = sorted(
        (key for key in conversation if _SESSION_RE.match(key)),
        key=lambda key: int(_SESSION_RE.match(key).group(1)),
    )
    lines: list[str] = []
    turns = 0
    for key in session_keys:
        date = conversation.get(f"{key}_date_time")
        if date:
            lines.append(f"[{date}]")
        for turn in conversation[key] or []:
            if not isinstance(turn, dict):
                continue
            text = str(turn.get("text", "")).strip()
            if text:
                lines.append(f"{turn.get('speaker', '?')}: {text}")
                turns += 1
    text = "\n".join(lines)
    truncated = bool(max_chars and len(text) > max_chars)
    if truncated:
        text = text[:max_chars]
    return text, turns, truncated


def memory_context(memories: list[Memory]) -> str:
    return "\n".join(f"- {_memory_head(memory)}: {memory.content}" for memory in memories)


def _memory_head(memory: Memory) -> str:
    head = " ".join(part for part in (memory.subject, memory.attribute or "", memory.value or "") if part)
    if memory.time.effective_at:
        head = f"{head} (effective {memory.time.effective_at})"
    elif memory.time.date_time:
        head = f"{head} (observed {memory.time.date_time})"
    return head


def labeled_memory_context(response) -> str:
    """Render every candidate with its resolver-assigned state role."""
    effective_ids = {item.memory_id for item in response.effective_memories}
    superseded = {relation.from_ for relation in response.relations if relation.relation == "SUPERSEDE"}
    conflict_ids: set[str] = set()
    for relation in response.relations:
        if relation.relation == "CONFLICT":
            conflict_ids.update((relation.from_, relation.to))
    lines: list[str] = []
    for candidate in response.candidate_memories:
        memory = candidate.memory
        tags: list[str] = []
        if memory.memory_id in effective_ids:
            tags.append("current")
        if memory.memory_id in superseded:
            tags.append("historical")
        if memory.memory_id in conflict_ids:
            tags.append("conflicting")
        prefix = f"[{','.join(tags)}] " if tags else ""
        lines.append(f"- {prefix}{_memory_head(memory)}: {memory.content}")
    return "\n".join(lines)


def _evidence_recall(candidate_memories: list[Memory], case: dict) -> float | None:
    required = set(case.get("required_memory_ids", []))
    if not required:
        return None
    found = {memory.memory_id for memory in candidate_memories}
    return len(required & found) / len(required)


def _answer_row(answer: str | None, case: dict, *, context_chars: int, extra: dict | None = None) -> dict:
    row: dict = {"answer": answer, "refused": answer is None, "context_chars": context_chars}
    if extra:
        row.update(extra)
    if "expected_answer" in case:
        reference = case["expected_answer"]
        row["answerable"] = reference is not None
        row["answer_f1"] = float(answer is None) if reference is None else answer_f1(answer, reference)
    return row


def run_comparison(
    cases: list[dict],
    store: MemoryStore,
    raw_by_sample: dict[str, dict],
    generator,
    embedding: Retriever,
    hybrid: Retriever,
    resolver: DynamicStateResolver,
    *,
    top_k: int = 5,
    max_expansion_memories: int = 50,
    full_text_max_chars: int = 0,
) -> dict:
    if not cases:
        raise ValueError("cases must not be empty")

    rows: list[dict] = []
    for index, case in enumerate(cases):
        sample_id = case["sample_id"]
        memories = store.memories(sample_id)
        if memories is None:
            raise ValueError(f"Unknown sample: {sample_id}")
        question = case["question"]
        entry = {
            "case_id": case.get("case_id", str(index)),
            "sample_id": sample_id,
            "question": question,
            "required_memory_ids": case.get("required_memory_ids", []),
        }

        raw = raw_by_sample.get(sample_id)
        if raw is None:
            entry["full_text"] = {"answer": None, "refused": True, "context_chars": 0, "missing_raw": True}
        else:
            full_text, turns, truncated = build_full_text_context(
                raw, max_chars=full_text_max_chars,
            )
            entry["full_text"] = _answer_row(
                generator.answer(question, full_text), case,
                context_chars=len(full_text),
                extra={"turns": turns, "truncated": truncated},
            )

        emb_retrieval = embedding.retrieve(question, memories, top_k, sample_id=sample_id)
        emb_memories = [candidate.memory for candidate in emb_retrieval.candidates]
        emb_context = memory_context(emb_memories)
        entry["vector_rag"] = _answer_row(
            generator.answer(question, emb_context) if emb_context else None, case,
            context_chars=len(emb_context),
            extra={
                "candidate_memory_ids": [memory.memory_id for memory in emb_memories],
                "evidence_set_recall": _evidence_recall(emb_memories, case),
                "degraded": emb_retrieval.degraded,
            },
        )

        hybrid_retrieval = hybrid.retrieve(question, memories, top_k, sample_id=sample_id)
        for name, expand in (("state_topk", False), ("state_bonus", True)):
            response = resolve_query(
                hybrid_retrieval, memories, resolver,
                expand_slots=expand, max_expansion_memories=max_expansion_memories,
            )
            context = labeled_memory_context(response)
            entry[name] = _answer_row(
                generator.answer(question, context) if context else None, case,
                context_chars=len(context),
                extra={
                    "candidate_memory_ids": [
                        candidate.memory.memory_id for candidate in response.candidate_memories
                    ],
                    "effective_memory_ids": [item.memory_id for item in response.effective_memories],
                    "evidence_set_recall": _evidence_recall(
                        [candidate.memory for candidate in response.candidate_memories], case,
                    ),
                    "evidence_status": response.evidence_status,
                    "template_answer": response.answer,
                    "degraded": response.degraded,
                    "expansion": response.expansion.model_dump() if response.expansion else None,
                },
            )
        rows.append(entry)

    summary: dict = {}
    for name in ("full_text", "vector_rag", "state_topk", "state_bonus"):
        selected = [row[name] for row in rows]
        annotated = [row for row in selected if "answer_f1" in row]
        summary[name] = {
            "cases": len(selected),
            "annotated_cases": len(annotated),
            "answerable_cases": sum(row.get("answerable", False) for row in selected),
            "mean_answer_f1": (
                sum(row["answer_f1"] for row in annotated) / len(annotated) if annotated else None
            ),
            "refusals": sum(row["refused"] for row in selected),
            "answerable_refusals": sum(
                1 for row in selected if row.get("answerable") and row["refused"]
            ),
            "mean_context_chars": sum(row["context_chars"] for row in selected) / len(selected),
        }
    return {"summary": summary, "cases": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", type=Path, required=True)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/locomo10.json"))
    parser.add_argument("--memory-dir", type=Path, default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-expansion-memories", type=int, default=50)
    parser.add_argument("--full-text-max-chars", type=int, default=0)
    parser.add_argument("--resolver", choices=("rules", "hybrid"), default="rules")
    parser.add_argument("--provider", choices=("openai", "deepseek"), default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    cases = load_cases(args.cases)
    store = MemoryStore(args.memory_dir)
    raw_by_sample = {
        sample.get("sample_id"): sample
        for sample in json.loads(args.raw.read_text(encoding="utf-8"))
    }
    retrievers = resolve_retrievers(["embedding", "hybrid"])
    report = run_comparison(
        cases, store, raw_by_sample,
        build_answer_generator(provider=args.provider, model=args.model),
        retrievers["embedding"], retrievers["hybrid"],
        build_dynamic_state_resolver(mode=args.resolver),
        top_k=args.top_k,
        max_expansion_memories=args.max_expansion_memories,
        full_text_max_chars=args.full_text_max_chars,
    )
    report["configuration"] = {
        "case_files": [str(path) for path in args.cases],
        "raw_file": str(args.raw),
        "memory_dir": str(store.directory),
        "top_k": args.top_k,
        "max_expansion_memories": args.max_expansion_memories,
        "full_text_max_chars": args.full_text_max_chars,
        "resolver": args.resolver,
        "answer_generator": "shared LLM answer generator (backend/answer.py)",
        "f1_normalization": "same local token F1 as slot_expansion; refusals count as 0",
    }
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"written: {args.json_out}")


if __name__ == "__main__":
    main()
