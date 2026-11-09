# v2 最终运行结果（2026-11-09）

由 `scripts/rerun_final.sh` 生成。标准答案只在生成结束后评分；完整 checkpoint 留在 Git 忽略目录 `evaluation/results/llm-comparison/final-rerun-2026-11-09/`。

## 测试集：Fixed / Forced / Adaptive Graph

340 题，628 个唯一上下文；deepseek/deepseek-flash，K=5，Graph ≤4 跳 / ≤8 条，输出 ≤128 token。

| 方法 | F1 | EM | Memory 召回 | 平均候选 | 平均输入 Token | 拒答 | 错误 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Fixed K5 | 0.4573 | 0.2765 | 59.92% | 5.00 | 825.1 | 100 | 0 |
| Forced Graph | 0.4887 | 0.2971 | 66.55% | 9.75 | 1263.2 | 83 | 0 |
| Adaptive Graph | 0.4837 | 0.2912 | 63.89% | 6.36 | 948.8 | 83 | 0 |

- Forced vs Fixed：ΔF1 +0.0314，提升 26 / 下降 10 / 不变 304

- Adaptive vs Fixed：ΔF1 +0.0264，提升 14 / 下降 0 / 不变 326

## 测试集整体方法对照（同一新版提示词）

| 模型 | 方法 | F1 | EM | Memory 召回 | 平均候选 | 平均输入 Token | 拒答 | 错误 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| deepseek/deepseek-flash | Full Text | 0.5692 | 0.3500 | — | — | 20139.2 | 43 | 0 |
| deepseek/deepseek-flash | Embedding K5 | 0.4677 | 0.2794 | 59.20% | 5.00 | 795.0 | 98 | 0 |
| deepseek/deepseek-flash | Hybrid K5 + rules | 0.4611 | 0.2735 | 59.92% | 5.00 | 825.1 | 98 | 0 |
| deepseek/deepseek-flash | K5 + 补检 + rules | 0.4823 | 0.3000 | 64.97% | 6.81 | 984.8 | 86 | 0 |
| deepseek/deepseek-flash | Hybrid K10 + rules | 0.5014 | 0.2941 | 67.45% | 9.99 | 1238.4 | 79 | 0 |

## 开发集确认：Fixed / Forced / Adaptive Graph

650 题，1238 个唯一上下文；deepseek/deepseek-flash，K=5，Graph ≤4 跳 / ≤8 条，输出 ≤128 token。

| 方法 | F1 | EM | Memory 召回 | 平均候选 | 平均输入 Token | 拒答 | 错误 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Fixed K5 | 0.4389 | 0.2400 | 60.23% | 5.00 | 824.0 | 181 | 0 |
| Forced Graph | 0.4574 | 0.2462 | 64.01% | 10.44 | 1327.0 | 160 | 0 |
| Adaptive Graph | 0.4539 | 0.2462 | 62.21% | 6.67 | 978.8 | 155 | 0 |

- Forced vs Fixed：ΔF1 +0.0186，提升 55 / 下降 32 / 不变 563

- Adaptive vs Fixed：ΔF1 +0.0150，提升 19 / 下降 0 / 不变 631

