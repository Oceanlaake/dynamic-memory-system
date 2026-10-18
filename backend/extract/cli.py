"""命令行入口。

用法：

    # 正式产出（有 DEEPSEEK_API_KEY 时默认走 LLM）
    python -m backend.extract build

    # 完全离线，用 dataset 自带 observation 生成基线
    python -m backend.extract build --provider rules

    # 只处理部分样本
    python -m backend.extract build --samples conv-26,conv-30

    # 校验已生成的 JSON（schema + evidence 可追溯性）
    python -m backend.extract validate

    # 查看当前产物统计
    python -m backend.extract stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.extract.cache import DEFAULT_CACHE_DIR
from backend.extract.locomo import load_dataset
from backend.extract.pipeline import (
    DEFAULT_OUT_DIR,
    DEFAULT_RAW_PATH,
    ExtractionConfig,
    extract_dataset,
    load_samples,
)
from backend.extract.postprocess import validate_document

DEFAULT_REPORT = Path("outputs/extraction_report.json")


def _select_samples(samples, spec: str | None):
    if not spec:
        return samples
    wanted = [item.strip() for item in spec.split(",") if item.strip()]
    known = {sample.sample_id: sample for sample in samples}
    missing = [item for item in wanted if item not in known]
    if missing:
        raise SystemExit(f"unknown sample id(s): {', '.join(missing)}; available: {', '.join(sorted(known))}")
    return [known[item] for item in wanted]


def cmd_build(args: argparse.Namespace) -> int:
    samples = _select_samples(load_samples(args.raw), args.samples)
    if args.limit:
        samples = samples[: args.limit]

    config = ExtractionConfig(
        provider=args.provider,
        gap_fill=not args.no_gap_fill,
        workers=args.workers,
        gap_batch_size=args.gap_batch_size,
        gap_context=args.gap_context,
        gap_min_chars=args.gap_min_chars,
        cache_dir=None if args.no_cache else args.cache_dir,
        attribute_normalization=not args.no_attr_normalize,
    )

    documents, summary = extract_dataset(
        samples,
        config=config,
        out_dir=args.out,
        resume=args.resume,
    )

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"samples        : {summary['samples']}")
    print(f"memories       : {summary['memories']} {summary['by_type']}")
    print(f"QA coverage*   : {summary['qa_evidence_covered']}/{summary['qa_evidence_turns']} "
          f"= {summary['qa_evidence_coverage']:.1%}  (*eval only, not used for extraction)")
    print(f"output dir     : {Path(args.out)}")
    print(f"report         : {report_path}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    files = sorted(directory.glob("*.json"))
    if not files:
        print(f"no JSON files under {directory}", file=sys.stderr)
        return 1

    samples = {sample.sample_id: sample for sample in load_dataset(args.raw)} if args.raw else {}
    failures = 0
    for path in files:
        document = json.loads(path.read_text(encoding="utf-8"))
        sample = samples.get(document.get("sample_id"))
        errors = validate_document(document, sample)
        if errors:
            failures += 1
            print(f"[FAIL] {path.name}: {len(errors)} error(s)")
            for error in errors[:10]:
                print(f"       {error}")
        else:
            print(f"[ ok ] {path.name}: {len(document.get('memories', []))} memories")

    print()
    print(f"validated {len(files)} file(s), {failures} failure(s)")
    return 1 if failures else 0


def cmd_stats(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    files = sorted(directory.glob("*.json"))
    if not files:
        print(f"no JSON files under {directory}", file=sys.stderr)
        return 1

    samples = {sample.sample_id: sample for sample in load_dataset(args.raw)}
    rows = []
    total_by_type: dict[str, int] = {}
    total_memories = 0
    total_evidence_turns = 0
    total_qa_turns = 0
    total_covered = 0

    for path in files:
        document = json.loads(path.read_text(encoding="utf-8"))
        sample = samples.get(document.get("sample_id"))
        memories = document.get("memories", [])
        by_type: dict[str, int] = {}
        evidence_turns: set[str] = set()
        missing_quote = 0
        null_attribute = 0
        for memory in memories:
            by_type[memory["type"]] = by_type.get(memory["type"], 0) + 1
            total_by_type[memory["type"]] = total_by_type.get(memory["type"], 0) + 1
            if not memory.get("attribute"):
                null_attribute += 1
            for evidence in memory.get("evidence", []):
                evidence_turns.add(evidence["dia_id"])
                if not evidence.get("quote"):
                    missing_quote += 1
        qa_turns = sample.qa_evidence_dia_ids() if sample else []
        covered = sum(1 for dia_id in qa_turns if dia_id in evidence_turns)
        total_memories += len(memories)
        total_evidence_turns += len(evidence_turns)
        total_qa_turns += len(qa_turns)
        total_covered += covered
        rows.append(
            {
                "sample_id": document.get("sample_id"),
                "memories": len(memories),
                "by_type": by_type,
                "evidence_turns": len(evidence_turns),
                "qa_coverage": round(covered / len(qa_turns), 4) if qa_turns else 0.0,
                "null_attribute": null_attribute,
                "missing_quote": missing_quote,
            }
        )

    print(f"{'sample':10} {'mem':>5} {'state':>6} {'event':>6} {'goal':>5} {'pref':>5} {'req':>4} "
          f"{'turns':>6} {'qa_cov':>7}")
    for row in rows:
        by_type = row["by_type"]
        print(
            f"{row['sample_id']:10} {row['memories']:5} {by_type.get('state', 0):6} "
            f"{by_type.get('event', 0):6} {by_type.get('goal', 0):5} {by_type.get('preference', 0):5} "
            f"{by_type.get('requirement', 0):4} {row['evidence_turns']:6} {row['qa_coverage']:7.1%}"
        )
    print("-" * 68)
    print(
        f"{'TOTAL':10} {total_memories:5} "
        f"{total_by_type.get('state', 0):6} {total_by_type.get('event', 0):6} "
        f"{total_by_type.get('goal', 0):5} {total_by_type.get('preference', 0):5} "
        f"{total_by_type.get('requirement', 0):4} {total_evidence_turns:6} "
        f"{(total_covered / total_qa_turns if total_qa_turns else 0):7.1%}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.extract",
        description="LoCoMo -> Structured Memory JSON",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="抽取并写出 Memory JSON")
    build.add_argument("--raw", type=Path, default=DEFAULT_RAW_PATH)
    build.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    build.add_argument("--samples", default=None, help="逗号分隔的 sample_id，例如 conv-26,conv-30")
    build.add_argument("--limit", type=int, default=0, help="只处理前 N 个样本（调试用）")
    build.add_argument(
        "--provider",
        default="auto",
        choices=["auto", "deepseek", "openai", "rules"],
        help="auto：有 API key 走 LLM，否则退回 rules",
    )
    build.add_argument("--workers", type=int, default=6, help="并发请求数")
    build.add_argument("--no-gap-fill", action="store_true", help="关闭未被引用 turn 的补抽")
    build.add_argument("--gap-batch-size", type=int, default=6)
    build.add_argument("--gap-context", type=int, default=2)
    build.add_argument("--gap-min-chars", type=int, default=20, help="短于该长度的 turn 不补抽")
    build.add_argument("--resume", action="store_true", help="跳过已存在的输出文件")
    build.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR, help="LLM 响应缓存目录")
    build.add_argument("--no-cache", action="store_true", help="禁用缓存（每次都真实调用）")
    build.add_argument(
        "--no-attr-normalize",
        action="store_true",
        help="不做 LLM 属性词表归一（每个样本多一次调用）",
    )
    build.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    build.set_defaults(func=cmd_build)

    validate = sub.add_parser("validate", help="按 APIs/memory_schema.json 校验产物")
    validate.add_argument("--dir", type=Path, default=DEFAULT_OUT_DIR)
    validate.add_argument("--raw", type=Path, default=DEFAULT_RAW_PATH)
    validate.set_defaults(func=cmd_validate)

    stats = sub.add_parser("stats", help="查看产物统计与 QA evidence 覆盖率")
    stats.add_argument("--dir", type=Path, default=DEFAULT_OUT_DIR)
    stats.add_argument("--raw", type=Path, default=DEFAULT_RAW_PATH)
    stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
