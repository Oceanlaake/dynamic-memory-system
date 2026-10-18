"""抽取流水线：LoCoMo -> 原始记忆 -> 规范化 Memory JSON。

两个模式：

* ``llm``：逐 session 调 LLM 抽取（正式产出），可选 gap-fill 补抽 QA evidence 中
  尚未被任何 memory 覆盖的 turn。
* ``rules``：使用 LoCoMo 自带 observation 标注做确定性基线，完全离线。

无论哪种模式，最终都经过 ``postprocess`` 的同一套校验，所以下游 B 看到的永远是
同一份 schema。
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from backend.extract.attribute_norm import normalize_vocabulary
from backend.extract.cache import DEFAULT_CACHE_DIR, CachedExtractionClient, ResponseCache
from backend.extract.llm import ExtractionClient, ExtractionError, build_client, has_llm_credentials
from backend.extract.locomo import Sample, Session, Turn, load_dataset
from backend.extract.postprocess import (
    NormalizeStats,
    finalize_document,
    normalize_all,
    validate_document,
)
from backend.extract.prompts import GAP_SYSTEM_PROMPT, SYSTEM_PROMPT, build_gap_prompt, build_session_prompt
from backend.extract.rules import extract_session_rules

logger = logging.getLogger(__name__)

DEFAULT_OUT_DIR = Path("outputs/memories")
DEFAULT_RAW_PATH = Path("data/raw/locomo10.json")


@dataclass
class ExtractionConfig:
    """一次抽取任务的配置。"""

    provider: str = "auto"  # auto | deepseek | openai | rules
    gap_fill: bool = True
    workers: int = 6
    gap_batch_size: int = 6
    gap_context: int = 2
    gap_min_chars: int = 20
    max_gap_calls_per_sample: int = 200
    retry_failed_sessions: bool = False
    cache_dir: Path | None = DEFAULT_CACHE_DIR
    attribute_normalization: bool = True


@dataclass
class SampleReport:
    sample_id: str
    provider: str
    sessions_total: int = 0
    sessions_extracted: int = 0
    memories: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    qa_evidence_turns: int = 0
    qa_evidence_covered: int = 0
    turns_with_memory: int = 0
    dialogue_turns: int = 0
    llm_calls: int = 0
    llm_errors: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    @property
    def qa_evidence_coverage(self) -> float:
        if not self.qa_evidence_turns:
            return 0.0
        return round(self.qa_evidence_covered / self.qa_evidence_turns, 4)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "provider": self.provider,
            "sessions_total": self.sessions_total,
            "sessions_extracted": self.sessions_extracted,
            "memories": self.memories,
            "by_type": self.by_type,
            "dialogue_turns": self.dialogue_turns,
            "turns_with_memory": self.turns_with_memory,
            "qa_evidence_turns": self.qa_evidence_turns,
            "qa_evidence_covered": self.qa_evidence_covered,
            "qa_evidence_coverage": self.qa_evidence_coverage,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "stats": self.stats,
            "llm_calls": self.llm_calls,
            "llm_errors": self.llm_errors[:10],
        }


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #
def resolve_provider(provider: str) -> str:
    """``auto`` -> 有 key 走 LLM，否则退回离线规则。"""

    choice = (provider or "auto").strip().lower()
    if choice == "auto":
        return "rules" if not has_llm_credentials() else "llm"
    if choice == "rules":
        return "rules"
    return "llm"


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("memories")
        if items is None:
            items = payload.get("results") or payload.get("data")
    else:
        items = payload
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _chunk(turns: Sequence[Turn], size: int) -> Iterable[list[Turn]]:
    for start in range(0, len(turns), size):
        yield list(turns[start : start + size])


def coverage_summary(
    sample: Sample,
    memories: Sequence[dict[str, Any]],
) -> tuple[int, int, int]:
    """**仅用于事后评估**：QA evidence turn 中有多少被 memory 覆盖。

    抽取阶段不使用该指标的结构（见 :func:`_gap_fill`），以免把测试集信息带入产物。
    返回 (QA evidence turn 数, 被覆盖数, 有 memory 的对话 turn 数)。
    """

    evidence_turns = {item["dia_id"] for memory in memories for item in memory.get("evidence", [])}
    qa_turns = sample.qa_evidence_dia_ids()
    covered = sum(1 for dia_id in qa_turns if dia_id in evidence_turns)
    return len(qa_turns), covered, len(evidence_turns)


# --------------------------------------------------------------------------- #
# 单样本抽取
# --------------------------------------------------------------------------- #
def _extract_sessions(
    sample: Sample,
    client: ExtractionClient,
    config: ExtractionConfig,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    sessions = sample.dialogue_sessions()
    if not sessions:
        return [], 0, []

    def run(session: Session) -> tuple[list[dict[str, Any]], str | None]:
        try:
            payload = client.extract_json(SYSTEM_PROMPT, build_session_prompt(sample, session))
            return _extract_items(payload), None
        except ExtractionError as exc:
            return [], f"{session.session_id}: {exc}"

    results: list[tuple[list[dict[str, Any]], str | None]] = []
    if config.workers <= 1:
        for session in sessions:
            results.append(run(session))
    else:
        with ThreadPoolExecutor(max_workers=config.workers) as pool:
            results = list(pool.map(run, sessions))

    memories: list[dict[str, Any]] = []
    errors: list[str] = []
    for items, error in results:
        memories.extend(items)
        if error:
            errors.append(error)
    return memories, len(sessions), errors


def _gap_fill(
    sample: Sample,
    client: ExtractionClient,
    known: Sequence[dict[str, Any]],
    config: ExtractionConfig,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    """对“尚未被任何 memory 引用”的对话 turn 做补抽。

    注意：这里刻意**不读取** ``sample.qa``。抽取阶段只看对话本身，QA 及其 evidence
    只用于事后评估（见 ``coverage_summary``），否则就是测试集泄漏。
    """

    covered = {item["dia_id"] for memory in known for item in memory.get("evidence", []) if isinstance(item, dict)}
    missing_by_session: dict[str, list[str]] = {}
    for turn in sample.all_turns():
        if turn.dia_id in covered:
            continue
        if len(turn.searchable_text.strip()) < config.gap_min_chars:
            continue
        missing_by_session.setdefault(turn.session_id, []).append(turn.dia_id)

    jobs: list[tuple[Session, list[Turn], list[Turn]]] = []
    for session_id, dia_ids in missing_by_session.items():
        session = sample.session(session_id)
        if session is None:
            continue
        targets = [turn for turn in session.turns if turn.dia_id in set(dia_ids)]
        for batch in _chunk(targets, config.gap_batch_size):
            start = batch[0].order - config.gap_context
            end = batch[-1].order + config.gap_context
            context = [turn for turn in session.turns if start <= turn.order <= end]
            jobs.append((session, batch, context))

    jobs = jobs[: config.max_gap_calls_per_sample]
    if not jobs:
        return [], 0, []

    def run(job: tuple[Session, list[Turn], list[Turn]]) -> tuple[list[dict[str, Any]], str | None]:
        session, targets, context = job
        try:
            payload = client.extract_json(
                GAP_SYSTEM_PROMPT, build_gap_prompt(sample, session, targets, context)
            )
            target_ids = {turn.dia_id for turn in targets}
            items = [
                item
                for item in _extract_items(payload)
                if any(
                    isinstance(evidence, dict) and evidence.get("dia_id") in target_ids
                    for evidence in item.get("evidence") or []
                )
            ]
            return items, None
        except ExtractionError as exc:
            return [], f"{session.session_id} gap-fill: {exc}"

    if config.workers <= 1:
        results = [run(job) for job in jobs]
    else:
        with ThreadPoolExecutor(max_workers=config.workers) as pool:
            results = list(pool.map(run, jobs))

    memories: list[dict[str, Any]] = []
    errors: list[str] = []
    for items, error in results:
        memories.extend(items)
        if error:
            errors.append(error)
    return memories, len(jobs), errors


def extract_sample(
    sample: Sample,
    *,
    client: ExtractionClient | None = None,
    config: ExtractionConfig | None = None,
) -> tuple[dict[str, Any], SampleReport]:
    """抽取一个样本，返回 (Memory 文档, 报告)。"""

    config = config or ExtractionConfig()
    started = time.perf_counter()
    mode = resolve_provider(config.provider)
    report = SampleReport(
        sample_id=sample.sample_id,
        provider=mode if mode == "rules" else getattr(client, "name", "llm"),
        sessions_total=len(sample.dialogue_sessions()),
        dialogue_turns=len(sample.all_turns()),
    )

    raw_memories: list[dict[str, Any]] = []
    normalizer_stats = NormalizeStats()

    if mode == "rules":
        for session in sample.dialogue_sessions():
            raw_memories.extend(extract_session_rules(sample, session))
        report.sessions_extracted = len(sample.dialogue_sessions())
        default_confidence = 0.75
    else:
        if client is None:
            client = build_client()
        if config.cache_dir and not getattr(client, "is_cached", False):
            client = CachedExtractionClient(client, ResponseCache(config.cache_dir))
        session_memories, session_count, errors = _extract_sessions(sample, client, config)
        raw_memories.extend(session_memories)
        report.sessions_extracted = session_count
        report.llm_errors.extend(errors)
        report.llm_calls += session_count
        default_confidence = 0.85

        if config.gap_fill:
            gap_memories, gap_calls, gap_errors = _gap_fill(sample, client, raw_memories, config)
            raw_memories.extend(gap_memories)
            report.llm_calls += gap_calls
            report.llm_errors.extend(gap_errors)

    normalized = normalize_all(
        sample, raw_memories, default_confidence=default_confidence, stats=normalizer_stats
    )
    if mode == "llm" and config.attribute_normalization and normalized and client is not None:
        changes, error = normalize_vocabulary(sample, normalized, client)
        normalizer_stats.canonicalized_attributes += changes.get("attributes", 0)
        report.llm_calls += 1
        if error:
            report.llm_errors.append(error)
    document = finalize_document(sample, normalized, stats=normalizer_stats)

    errors = validate_document(document, sample)
    if errors:
        raise ValueError(f"{sample.sample_id}: generated document is invalid: {errors[:5]}")

    qa_total, qa_covered, turns_with_memory = coverage_summary(sample, document["memories"])
    report.memories = len(document["memories"])
    report.by_type = _count_by_type(document["memories"])
    report.qa_evidence_turns = qa_total
    report.qa_evidence_covered = qa_covered
    report.turns_with_memory = turns_with_memory
    report.stats = normalizer_stats.as_dict()
    if mode == "llm" and getattr(client, "is_cached", False):
        report.stats["cache"] = client.cache.stats()
    report.elapsed_seconds = time.perf_counter() - started
    return document, report


def _count_by_type(memories: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for memory in memories:
        memory_type = memory.get("type", "unknown")
        counts[memory_type] = counts.get(memory_type, 0) + 1
    return dict(sorted(counts.items()))


# --------------------------------------------------------------------------- #
# 数据集级抽取
# --------------------------------------------------------------------------- #
def write_document(document: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{document['sample_id']}.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def extract_dataset(
    samples: Sequence[Sample],
    *,
    config: ExtractionConfig | None = None,
    out_dir: Path | str | None = None,
    client: ExtractionClient | None = None,
    resume: bool = False,
    progress: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """批量抽取并落盘，返回 (文档列表, 汇总报告)。"""

    config = config or ExtractionConfig()
    out_path = Path(out_dir or DEFAULT_OUT_DIR)
    mode = resolve_provider(config.provider)
    if mode == "llm" and client is None:
        client = build_client()

    documents: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []

    for sample in samples:
        target = out_path / f"{sample.sample_id}.json"
        if resume and target.exists():
            document = json.loads(target.read_text(encoding="utf-8"))
            documents.append(document)
            reports.append(
                {
                    "sample_id": sample.sample_id,
                    "skipped": True,
                    "memories": len(document.get("memories", [])),
                }
            )
            if progress:
                print(f"[skip] {sample.sample_id}: existing {target}")
            continue

        document, report = extract_sample(sample, client=client, config=config)
        write_document(document, out_path)
        documents.append(document)
        reports.append(report.as_dict())
        if progress:
            print(
                f"[done] {sample.sample_id}: {report.memories} memories "
                f"({report.by_type}), QA-evidence coverage (eval only) "
                f"{report.qa_evidence_covered}/{report.qa_evidence_turns} "
                f"= {report.qa_evidence_coverage:.1%}, {report.elapsed_seconds:.1f}s"
            )

    summary = {
        "provider": mode if mode == "rules" else getattr(client, "name", "llm"),
        "samples": len(documents),
        "memories": sum(len(document.get("memories", [])) for document in documents),
        "by_type": _count_by_type([m for d in documents for m in d.get("memories", [])]),
        "qa_evidence_turns": sum(item.get("qa_evidence_turns", 0) for item in reports),
        "qa_evidence_covered": sum(item.get("qa_evidence_covered", 0) for item in reports),
        "per_sample": reports,
    }
    total_qa = summary["qa_evidence_turns"]
    summary["qa_evidence_coverage"] = (
        round(summary["qa_evidence_covered"] / total_qa, 4) if total_qa else 0.0
    )
    return documents, summary


def load_samples(raw_path: Path | str = DEFAULT_RAW_PATH) -> list[Sample]:
    return load_dataset(raw_path)
