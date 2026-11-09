# 大规模统一 LLM 对照结果

F1/EM 为本地英文 token 归一化口径；错误、拒答与跳过均计 0 分。Token 为 API usage 的已报告行均值，未报告保持 null。

## 表 1：模型 × 整体方法（回答质量与消耗）

| 模型 | 方法 | F1 | EM | Memory 召回 | 平均候选 | 输入 Token | 输出 Token | 错误 | 拒答 | 跳过 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| deepseek/deepseek-flash | Full Text | 0.5692 | 0.3500 | — | — | 20139.2 | 13.7 | 0 | 43 | 0 |
| deepseek/deepseek-flash | Embedding K=5 | 0.4677 | 0.2794 | 0.592 | 5.00 | 795.0 | 18.7 | 0 | 98 | 0 |
| deepseek/deepseek-flash | Hybrid K=5 + rules | 0.4611 | 0.2735 | 0.599 | 5.00 | 825.1 | 18.5 | 0 | 98 | 0 |
| deepseek/deepseek-flash | K=5 + 补检 + rules | 0.4823 | 0.3000 | 0.650 | 6.81 | 984.8 | 19.1 | 0 | 86 | 3 |
| deepseek/deepseek-flash | Hybrid K=10 + rules | 0.5014 | 0.2941 | 0.675 | 9.99 | 1238.4 | 19.6 | 0 | 79 | 0 |

## 表 2：模型 × K5 / K10 / 补检（收益与成本）

| 模型 | 方法 | F1 | 平均候选 | 输入 Token | 相对 K10 输入 Token |
|---|---|---:|---:|---:|---:|
| deepseek/deepseek-flash | Hybrid K=5 + rules | 0.4611 | 5.00 | 825.1 | -33.4% |
| deepseek/deepseek-flash | K=5 + 补检 + rules | 0.4823 | 6.81 | 984.8 | -20.5% |
| deepseek/deepseek-flash | Hybrid K=10 + rules | 0.5014 | 9.99 | 1238.4 | 0.0% |

## 配对差异（新方案 − 基线，F1）

| 模型 | 比较 | 平均 F1 差 | 上升 / 下降 / 不变 |
|---|---|---:|---:|
| deepseek/deepseek-flash | Hybrid K=5 + rules − Embedding K=5 | -0.0066 | 43 / 37 / 260 |
| deepseek/deepseek-flash | K=5 + 补检 + rules − Hybrid K=5 + rules | 0.0212 | 21 / 10 / 309 |
| deepseek/deepseek-flash | K=5 + 补检 + rules − Hybrid K=10 + rules | -0.0191 | 17 / 25 / 298 |
| deepseek/deepseek-flash | Hybrid K=5 + rules − Hybrid K=10 + rules | -0.0403 | 15 / 37 / 288 |

重复轮次：1。以上为逐轮均值的简单汇总；轮间波动见 summary.json。
