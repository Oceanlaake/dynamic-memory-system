"""Export a small, auditable release without raw API/context/checkpoint files.

Read-only with respect to source results. No provider calls or re-scoring policy
changes: existing row scores are checked against the frozen references.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

from evaluation.slot_expansion import answer_em, answer_f1


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_results(source: Path, output: Path) -> dict:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Choose a new empty export directory; existing results are preserved")
    manifest = json.loads((source / "manifest.json").read_text())
    summary = json.loads((source / "summary.json").read_text())
    references = {}
    for filename in manifest["case_files"]:
        for case in json.loads(Path(filename).read_text())["cases"]:
            references[(case["sample_id"], case["question"])] = case
    compact = {
        "note": "Frozen large-scale results; no new API calls. F1/EM are local metrics, not official scores. Raw requests and contexts remain local.",
        "summary": summary["summary"],
        "paired": {
            model: {name: {k: v for k, v in pair.items() if k != "changes"}
                    for name, pair in pairs.items()}
            for model, pairs in summary["paired"].items()
        },
        "blocked": summary["blocked"],
    }
    methods = ("full_text", "vector_rag", "state_topk", "state_bonus", "state_k10")
    rows, reports, usage = [], {}, {}
    for model in summary["summary"]:
        model_id = model.split("/", 1)[1]
        slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model_id)
        report = json.loads((source / f"model-{slug}.json").read_text())
        if len(report["cases"]) != manifest["case_count"]:
            raise ValueError(f"Incomplete cases for {model}")
        reports[model] = report
        usage[model] = json.loads((source / f"actual-usage-{slug}.json").read_text())
        for case in report["cases"]:
            reference = references[(case["sample_id"], case["question"])]
            expected = reference["expected_answer"]
            for method in methods:
                result = case[method]
                if expected is not None:
                    if abs(answer_f1(result["answer"], expected) - result["answer_f1"]) > 1e-12:
                        raise ValueError(f"F1 mismatch: {model}/{case['case_id']}/{method}")
                    if answer_em(result["answer"], expected) != result["answer_em"]:
                        raise ValueError(f"EM mismatch: {model}/{case['case_id']}/{method}")
                trace = result["generation"]
                token_usage = trace["usage"]
                rows.append({
                    "model": model, "case_id": case["case_id"], "sample_id": case["sample_id"],
                    "question": case["question"], "expected_answer": expected, "method": method,
                    "answer": result["answer"], "answer_f1": result.get("answer_f1"),
                    "answer_em": result.get("answer_em"), "status": trace["status"],
                    "error_code": trace["error_code"],
                    "required_memory_ids": json.dumps(reference["required_memory_ids"]),
                    "candidate_memory_ids": json.dumps(result.get("candidate_memory_ids", [])),
                    "answer_memory_ids": json.dumps(result.get("answer_memory_ids", [])),
                    "evidence_set_recall": result.get("evidence_set_recall"),
                    "input_tokens": token_usage["input_tokens"], "output_tokens": token_usage["output_tokens"],
                    "cached_input_tokens": token_usage["cached_input_tokens"],
                    "reasoning_tokens": token_usage["reasoning_tokens"],
                    "context_sha256": trace["context_sha256"],
                })
        for method in methods:
            scored = [r["answer_f1"] for r in rows if r["model"] == model and r["method"] == method]
            if abs(sum(scored) / len(scored) - summary["summary"][model][method]["mean_f1"]) > 1e-12:
                raise ValueError(f"Summary mismatch: {model}/{method}")

    examples = []
    primary = reports.get("deepseek/deepseek-flash")
    if primary:
        ordered = sorted(primary["cases"], key=lambda c: c["state_bonus"]["answer_f1"] - c["state_topk"]["answer_f1"])
        for case in [*ordered[-2:], *ordered[:2]]:
            reference = references[(case["sample_id"], case["question"])]
            examples.append({
                "model": "deepseek/deepseek-flash", "case_id": case["case_id"],
                "sample_id": case["sample_id"], "question": case["question"],
                "expected_answer": reference["expected_answer"],
                **{method: {k: case[method].get(k) for k in (
                    "answer", "answer_f1", "answer_memory_ids", "candidate_memory_ids", "evidence_set_recall")}
                   for method in ("state_topk", "state_bonus")},
            })
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "manifest.json", manifest)
    write_json(output / "summary.json", compact)
    write_json(output / "actual-usage.json", usage)
    write_json(output / "case-examples.json", {
        "selection": "Two highest and two lowest paired F1 changes for DeepSeek bonus vs K5. Illustrative extremes, not a representative random sample.",
        "cases": examples,
    })
    with (output / "per-question.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (output / "summary.md").write_text((source / "summary.md").read_text().rstrip() + "\n", encoding="utf-8")
    (output / "README.md").write_text(
        "# 最终实验结果包\n\n"
        "340 题、单轮、两模型完成、五组方法，另一个模型因服务繁忙阻塞。"
        "以 [正式分析](../../../docs/large-scale-results-2026-11-05.md) 为解释来源。\n\n"
        "- `summary.md` / `summary.json`：方法汇总与配对计数；blocked 项不是有效成绩。\n"
        "- `per-question.csv`：模型 × 题目 × 方法，含标准答案、生成答案、F1/EM、状态、记忆 ID 和实际 usage。\n"
        "- `case-examples.json`：两正两负案例，明确为极端示例，不代表总体。\n"
        "- `manifest.json`：原始冻结配置和数据/源码哈希。\n"
        "- `actual-usage.json`：实际请求账本，和独立方法等价用量分开。\n"
        "- `export-verification.json`：导出完整性及逐题 F1/EM 核对记录。\n\n"
        "不包含密钥、逐请求原文、重复对话上下文、失败重试日志或恢复缓存。"
        "原始审计材料仍保存在本机被 Git 忽略的 `evaluation/results/llm-comparison/large-scale-v1/`。\n\n"
        "现有 340 题是已暴露的自定测试集；GLM 的 Full Text 大量协议失败，不能作为正常语义基线。"
        "CSV 空答案结合 status 识别拒答/错误，不把空白视为有效答案。\n\n"
        "复现入口：`python -m evaluation.final.large_scale --help`；"
        "重新导出：`python -m evaluation.final.export_submission --source <本地完整结果目录> --output <新空目录>`。"
        "导出本身不调用 API；重新生成实验答案会产生真实 API 消耗。\n",
        encoding="utf-8",
    )
    verification = {
        "completed_models": len(reports), "cases_per_model": manifest["case_count"],
        "methods_per_case": len(methods), "csv_rows": len(rows),
        "all_row_f1_em_verified": True, "all_method_mean_f1_verified": True,
        "source_directory": str(source),
        "exporter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "artifact_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(output.iterdir()) if p.is_file()},
    }
    write_json(output / "export-verification.json", verification)
    return verification


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_results(args.source, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
