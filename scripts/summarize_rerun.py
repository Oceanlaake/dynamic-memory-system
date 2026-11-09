"""汇总 scripts/rerun_final.sh 的结果，输出 Markdown（不调用 API）。

用法：python scripts/summarize_rerun.py evaluation/results/run-v2-2026-11-09
"""
import json
import sys
from pathlib import Path

GRAPH_NAMES = {"fixed_k": "Fixed K5", "graph_memory": "Forced Graph", "adaptive_graph": "Adaptive Graph"}
BASE_NAMES = {"full_text": "Full Text", "vector_rag": "Embedding K5", "state_topk": "Hybrid K5 + rules",
              "state_bonus": "K5 + 补检 + rules", "state_k10": "Hybrid K10 + rules"}


def pct(x):
    return "—" if x is None else f"{x * 100:.2f}%"


def num(x, f="{:.4f}"):
    return "—" if x is None else f.format(x)


def stats(r):
    """Return (input_tokens, refusals, errors) for both old and new summary layouts."""
    g = r.get("generation") or {}
    tok = r.get("mean_input_tokens")
    if tok is None:
        tok = ((g.get("standalone_token_footprint") or r.get("token_footprint") or {})
               .get("input_tokens", {}).get("mean_reported"))
    ref = r.get("refusals", g.get("model_refusals", (r.get("failure_types") or {}).get("refused")))
    err = r.get("errors", g.get("errors"))
    return tok, ("—" if ref is None else ref), ("—" if err is None else err)


def graph_table(d: Path, title: str) -> list[str]:
    s = json.loads((d / "summary.json").read_text())
    m = json.loads((d / "manifest.json").read_text())
    out = [f"## {title}", "",
           f"{m['case_count']} 题，{m['unique_contexts']} 个唯一上下文；{m['provider']}/{m['model']}，"
           f"K={m['top_k']}，Graph ≤{m['max_hops']} 跳 / ≤{m['max_graph_memories']} 条，输出 ≤{m['max_output_tokens']} token。", "",
           "| 方法 | F1 | EM | Memory 召回 | 平均候选 | 平均输入 Token | 拒答 | 错误 |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for k, name in GRAPH_NAMES.items():
        r = s["methods"][k]
        tok, ref, err = stats(r)
        out.append(f"| {name} | {num(r['mean_f1'])} | {num(r['mean_em'])} | {pct(r['mean_evidence_set_recall'])} | "
                   f"{num(r['mean_candidates'], '{:.2f}')} | {num(tok, '{:.1f}')} | {ref} | {err} |")
    for key, label in (("paired", "Forced vs Fixed"), ("paired_adaptive", "Adaptive vs Fixed")):
        p = s[key]
        out.append("")
        out.append(f"- {label}：ΔF1 {p['mean_delta_f1']:+.4f}，提升 {p['improved']} / 下降 {p['worsened']} / 不变 {p['unchanged']}")
    out.append("")
    return out


def base_table(d: Path) -> list[str]:
    s = json.loads((d / "summary.json").read_text())["summary"]
    out = ["## 测试集整体方法对照（同一新版提示词）", "",
           "| 模型 | 方法 | F1 | EM | Memory 召回 | 平均候选 | 平均输入 Token | 拒答 | 错误 |",
           "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for model, methods in s.items():
        for k, name in BASE_NAMES.items():
            r = methods.get(k)
            if not r:
                continue
            tok, ref, err = stats(r)
            out.append(f"| {model} | {name} | {num(r['mean_f1'])} | {num(r['mean_em'])} | {pct(r.get('mean_evidence_set_recall'))} | "
                       f"{num(r.get('mean_candidates'), '{:.2f}')} | {num(tok, '{:.1f}')} | {ref} | {err} |")
    out.append("")
    return out


def main():
    root = Path(sys.argv[1])
    lines = ["# v2 最终运行结果（2026-11-09）", "",
             "由 `scripts/rerun_final.sh` 生成。标准答案只在生成结束后评分；完整 checkpoint 留在 Git 忽略目录 "
             "`evaluation/results/llm-comparison/final-rerun-2026-11-09/`。", ""]
    if (root / "test-graph").exists():
        lines += graph_table(root / "test-graph", "测试集：Fixed / Forced / Adaptive Graph")
    if (root / "test-baselines").exists():
        lines += base_table(root / "test-baselines")
    if (root / "dev-graph").exists():
        lines += graph_table(root / "dev-graph", "开发集确认：Fixed / Forced / Adaptive Graph")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
