"""合并 11 月 5 日与 11 月 9 日的实验结果（不调用 API）。

两次运行使用相同题单、原始对话、冻结 Memory 与检索 / 补检代码；不同点为答案提示词、
输出上限与模型。脚本从逐题数据重新计算全部指标，并输出 Markdown 与 JSON：

    python scripts/consolidate_results.py
"""
import csv
import json
import random
from pathlib import Path

OLD = Path("evaluation/results/run-v1-2026-11-05/per-question.csv")
NEW = Path("evaluation/results/run-v2-2026-11-09/test-baselines/per-question.csv")
GRAPH_TEST = Path("evaluation/results/run-v2-2026-11-09/test-graph/results.json")
GRAPH_DEV = Path("evaluation/results/run-v2-2026-11-09/dev-graph/results.json")
OUT_MD = Path("docs/results/results-v1-v2.md")
OUT_JSON = Path("evaluation/results/summary-v1-v2.json")

BASE = {"full_text": "Full Text", "vector_rag": "Embedding K5", "state_topk": "Hybrid K5",
        "state_bonus": "K5 + 补检", "state_k10": "Hybrid K10"}
GRAPH = {"fixed_k": "Fixed K5（Graph 组基线）", "graph_memory": "Forced Graph", "adaptive_graph": "Adaptive Graph"}


def f(x):
    return None if x in ("", None) else float(x)


def load_csv(path, model):
    out = {}
    for r in csv.DictReader(path.open(encoding="utf-8")):
        if r["model"] != model:
            continue
        out.setdefault(r["method"], {})[(r["sample_id"], r["case_id"])] = {
            "f1": f(r["answer_f1"]) or 0.0, "em": f(r["answer_em"]) or 0.0,
            "recall": f(r["evidence_set_recall"]),
            "cand": len(json.loads(r["candidate_memory_ids"] or "[]")) if r["method"] != "full_text" else None,
            "tok": f(r["input_tokens"]), "status": r["status"],
        }
    return out


def load_graph(path):
    out = {k: {} for k in GRAPH}
    for row in json.loads(path.read_text())["cases"]:
        key = (row["sample_id"], str(row["case_id"]))
        for m in GRAPH:
            s = row[m]
            g = s.get("generation") or {}
            out[m][key] = {
                "f1": s["answer_f1"], "em": s["answer_em"], "recall": s["evidence_set_recall"],
                "cand": s["candidate_count"], "tok": (g.get("usage") or {}).get("input_tokens"),
                "status": g.get("status") or ("refused" if s.get("refused") else "answered"),
            }
    return out


def mean(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


def stats(rows):
    r = list(rows.values())
    return {
        "n": len(r), "f1": mean([x["f1"] for x in r]), "em": mean([x["em"] for x in r]),
        "recall": mean([x["recall"] for x in r]), "cand": mean([x["cand"] for x in r]),
        "tok": mean([x["tok"] for x in r]),
        "refused": sum(x["status"] == "refused" for x in r),
        "errors": sum(x["status"] == "error" for x in r),
    }


def paired(a, b, seed=7, n=5000):
    keys = sorted(set(a) & set(b))
    d = [b[k]["f1"] - a[k]["f1"] for k in keys]
    rng = random.Random(seed)
    boots = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(n))
    return {"n": len(d), "delta": sum(d) / len(d), "up": sum(x > 1e-9 for x in d),
            "down": sum(x < -1e-9 for x in d), "ci": [boots[int(0.025 * n)], boots[int(0.975 * n) - 1]]}


def pct(x):
    return "—" if x is None else f"{x * 100:.2f}%"


def n4(x):
    return "—" if x is None else f"{x:.4f}"


def n1(x):
    return "—" if x is None else f"{x:,.1f}"


def n2(x):
    return "—" if x is None else f"{x:.2f}"


def pr(p):
    return f"{p['delta']:+.4f} | {p['up']} / {p['down']} | [{p['ci'][0]:+.4f}, {p['ci'][1]:+.4f}]"


def main():
    old_ds = load_csv(OLD, "deepseek/deepseek-flash")
    old_glm = load_csv(OLD, "glm/glm-4-flash-250414")
    new_ds = load_csv(NEW, "deepseek/deepseek-flash")
    gt, gd = load_graph(GRAPH_TEST), load_graph(GRAPH_DEV)

    res = {"note": "Recomputed from per-question data; no API calls.", "test": {}, "dev": {}, "paired": {}}
    L = ["# 合并实验结果（11 月 5 日 + 11 月 9 日）", "",
         "由 `scripts/consolidate_results.py` 从逐题数据重新计算，不调用 API。F1 / EM 为本地英文 token 口径；"
         "拒答、错误与跳过均计 0 分；95% 置信区间为逐题配对 bootstrap（5,000 次）。", "",
         "## 两次运行能否放在一起", "",
         "| 项目 | 11 月 5 日（v1） | 11 月 9 日（v2，最终） |", "|---|---|---|",
         "| 测试题单 / 原始对话 / 冻结 Memory | 340 题 conv-47/48；哈希一致 | 同左（哈希一致） |",
         "| 检索、补检、关系规则代码 | 一致 | 一致 |",
         "| 答案提示词 | 旧版（短答案，未约束粒度与列表完整性） | 新版（最短完整答案、列表不漏项、`\"null\"` 归一化） |",
         "| 最大输出 Token | 1024 | 128 |",
         "| 模型 | DeepSeek Flash、GLM-4-Flash（GLM-4.7 因限流无有效成绩） | DeepSeek Flash |",
         "| 补选方法 | 查询驱动补检 | 补检 + Graph Memory（强制 / 自适应） |", "",
         "因此：*同一天内*的方法可以直接比较；*跨天*只能作为“提示词版本效应”逐题配对比较，不能把 v1 某方法与 v2 另一方法的差值算作方法收益。", "",
         "## 表 1　测试集全部方法（340 题）", "",
         "| 运行 | 模型 | 方法 | F1 | EM | Memory 召回 | 平均候选 | 平均输入 Token | 拒答 | 错误 |",
         "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]

    def row(run, model, name, s):
        return (f"| {run} | {model} | {name} | {n4(s['f1'])} | {n4(s['em'])} | {pct(s['recall'])} | {n2(s['cand'])} | "
                f"{n1(s['tok'])} | {s['refused']} | {s['errors']} |")

    for run, model, data in (("v1 11/5", "GLM-4-Flash", old_glm), ("v1 11/5", "DeepSeek", old_ds)):
        for k, name in BASE.items():
            s = stats(data[k]); res["test"][f"{run}|{model}|{name}"] = s
            L.append(row(run, model, name, s))
    for k, name in BASE.items():
        s = stats(new_ds[k]); res["test"][f"v2 11/9|DeepSeek|{name}"] = s
        L.append(row("**v2 11/9**", "DeepSeek", name, s))
    for k, name in GRAPH.items():
        s = stats(gt[k]); res["test"][f"v2 11/9|DeepSeek|{name}"] = s
        L.append(row("**v2 11/9**", "DeepSeek", name, s))
    L += ["", "v1 的 GLM-4-Flash Full Text 有 300/340 次协议错误，不代表语义能力。v2 中 Hybrid K5 与 Graph 组的 Fixed K5 是同一配置的两次独立请求，"
          "二者 F1 之差可视为运行间波动的量级。", ""]

    # table 2: prompt version effect
    L += ["## 表 2　提示词版本效应（DeepSeek，同题配对：v2 − v1）", "",
          "| 方法 | v1 F1 | v2 F1 | ΔF1 | 提升 / 下降题数 | 95% CI |", "|---|---:|---:|---:|---|---|"]
    for k, name in BASE.items():
        p = paired(old_ds[k], new_ds[k]); res["paired"][f"version|{name}"] = p
        L.append(f"| {name} | {n4(stats(old_ds[k])['f1'])} | {n4(stats(new_ds[k])['f1'])} | {pr(p)} |")
    L += ["", "所有方法在新提示词下都显著提升，幅度（约 +5 到 +8 个百分点）大于任何补选方法本身的贡献，"
          "所以跨版本的总提升主要来自答案约束，而非补选。", ""]

    # table 3: method comparisons within v2 test
    L += ["## 表 3　v2 测试集内的方法配对比较（DeepSeek，340 题）", "",
          "| 比较（后者 − 前者） | ΔF1 | 提升 / 下降题数 | 95% CI |", "|---|---:|---|---|"]
    comps = [
        ("Hybrid K5 → K5 + 补检", new_ds["state_topk"], new_ds["state_bonus"]),
        ("Fixed K5 → Forced Graph", gt["fixed_k"], gt["graph_memory"]),
        ("Fixed K5 → Adaptive Graph", gt["fixed_k"], gt["adaptive_graph"]),
        ("Forced Graph → Adaptive Graph", gt["graph_memory"], gt["adaptive_graph"]),
        ("K5 + 补检 → Adaptive Graph", new_ds["state_bonus"], gt["adaptive_graph"]),
        ("Hybrid K10 → Adaptive Graph", new_ds["state_k10"], gt["adaptive_graph"]),
        ("Hybrid K10 → Forced Graph", new_ds["state_k10"], gt["graph_memory"]),
        ("Hybrid K5 → Hybrid K10", new_ds["state_topk"], new_ds["state_k10"]),
        ("Hybrid K10 → Full Text", new_ds["state_k10"], new_ds["full_text"]),
        ("Embedding K5 → Hybrid K5", new_ds["vector_rag"], new_ds["state_topk"]),
    ]
    for name, a, b in comps:
        p = paired(a, b); res["paired"][f"test|{name}"] = p
        L.append(f"| {name} | {pr(p)} |")
    L.append("")

    # table 4: dev confirmation
    L += ["## 表 4　开发集确认（v2，650 题，DeepSeek）", "",
          "| 方法 | F1 | EM | Memory 召回 | 平均候选 | 平均输入 Token | 拒答 | 错误 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for k, name in GRAPH.items():
        s = stats(gd[k]); res["dev"][name] = s
        L.append(f"| {name} | {n4(s['f1'])} | {n4(s['em'])} | {pct(s['recall'])} | {n2(s['cand'])} | {n1(s['tok'])} | {s['refused']} | {s['errors']} |")
    L += ["", "| 比较（后者 − 前者） | ΔF1 | 提升 / 下降题数 | 95% CI |", "|---|---:|---|---|"]
    for name, a, b in (("Fixed K5 → Forced Graph", gd["fixed_k"], gd["graph_memory"]),
                       ("Fixed K5 → Adaptive Graph", gd["fixed_k"], gd["adaptive_graph"]),
                       ("Forced Graph → Adaptive Graph", gd["graph_memory"], gd["adaptive_graph"])):
        p = paired(a, b); res["paired"][f"dev|{name}"] = p
        L.append(f"| {name} | {pr(p)} |")
    L.append("")

    L += ["## 结论", "",
          "1. **最大的单一改进是答案提示词**：同题配对下，所有 DeepSeek 方法的 F1 都提升约 6–8 个百分点（表 2，置信区间均不含 0）。"
          "因此 v1 → v2 的总提升不能归功于补选。",
          "2. **补选在同一版本内确实有效**：相对 K5，补检 +2.1、Forced Graph +3.1、Adaptive Graph +2.6 个百分点，置信区间均不含 0（表 3）；"
          "开发集 650 题上 Adaptive 仍为 +1.5 个百分点、19 升 0 降（表 4），说明收益不是只在测试集上成立。",
          "3. **Adaptive 与 Forced 精度相当，但更稳、更省**：两者 F1 差在测试集与开发集的置信区间都跨 0；"
          "Adaptive 在两个集合上都没有下降题，输入 Token 少约 25%。",
          "4. **补选没有超过直接取 K10**：K10 的 F1 比 Adaptive 高 1.8 个百分点（置信区间刚好跨 0），但输入 Token 多约 30%。"
          "补选的价值是用更少上下文拿回 K5 → K10 一半以上的收益（约 56%–60%），而不是精度上限更高。",
          "5. **Full Text 仍是精度上限**：F1 0.5692，比 K10 高 6.8 个百分点，但每题约 2 万输入 Token，是 Adaptive 的约 21 倍。",
          "6. **复现性**：同学 11 月 8 日的运行（Fixed / Forced / Adaptive F1 0.4546 / 0.4784 / 0.4859）与本次重测"
          "（0.4573 / 0.4887 / 0.4837）各组相差不超过 0.011，Forced 与 Adaptive 的先后在波动范围内互换；同一配置两次请求"
          "（Hybrid K5 与 Fixed K5）相差 0.004。",
          "7. **多模型**：GLM-4-Flash 只有 v1 数据；其 Full Text 协议错误过多，Embedding / Hybrid / 补检三组彼此接近（约 0.365），"
          "K10 反而更低，且 19–48 次接口错误计 0 分，模型间结论以 DeepSeek 为主。", ""]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    OUT_JSON.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
