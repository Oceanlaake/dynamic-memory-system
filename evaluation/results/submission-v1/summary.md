# 大规模统一 LLM 对照结果

F1/EM 为本地英文 token 归一化口径；错误、拒答与跳过均计 0 分。Token 为 API usage 的已报告行均值，未报告保持 null。

## 表 1：模型 × 整体方法（回答质量与消耗）

| 模型 | 方法 | F1 | EM | Memory 召回 | 平均候选 | 输入 Token | 输出 Token | 错误 | 拒答 | 跳过 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| deepseek/deepseek-flash | Full Text | 0.5043 | 0.2324 | — | — | 19983.2 | 18.6 | 0 | 61 | 0 |
| deepseek/deepseek-flash | Embedding K=5 | 0.4069 | 0.2029 | 0.592 | 5.00 | 639.0 | 21.4 | 0 | 113 | 0 |
| deepseek/deepseek-flash | Hybrid K=5 + rules | 0.3976 | 0.2029 | 0.599 | 5.00 | 669.1 | 21.8 | 0 | 109 | 0 |
| deepseek/deepseek-flash | K=5 + 补检 + rules | 0.4075 | 0.2088 | 0.650 | 6.81 | 828.8 | 22.3 | 0 | 101 | 3 |
| deepseek/deepseek-flash | Hybrid K=10 + rules | 0.4243 | 0.2059 | 0.675 | 9.99 | 1082.4 | 23.4 | 0 | 98 | 0 |
| glm/glm-4-flash-250414 | Full Text | 0.0405 | 0.0235 | — | — | 20010.5 | 322.2 | 300 | 0 | 0 |
| glm/glm-4-flash-250414 | Embedding K=5 | 0.3659 | 0.1882 | 0.592 | 5.00 | 678.4 | 22.4 | 33 | 81 | 0 |
| glm/glm-4-flash-250414 | Hybrid K=5 + rules | 0.3663 | 0.1912 | 0.599 | 5.00 | 706.3 | 20.9 | 19 | 103 | 0 |
| glm/glm-4-flash-250414 | K=5 + 补检 + rules | 0.3647 | 0.1941 | 0.650 | 6.81 | 868.2 | 22.0 | 30 | 89 | 3 |
| glm/glm-4-flash-250414 | Hybrid K=10 + rules | 0.3491 | 0.1765 | 0.675 | 9.99 | 1127.4 | 23.4 | 48 | 73 | 0 |

## 表 2：模型 × K5 / K10 / 补检（收益与成本）

| 模型 | 方法 | F1 | 平均候选 | 输入 Token | 相对 K10 输入 Token |
|---|---|---:|---:|---:|---:|
| deepseek/deepseek-flash | Hybrid K=5 + rules | 0.3976 | 5.00 | 669.1 | -38.2% |
| deepseek/deepseek-flash | K=5 + 补检 + rules | 0.4075 | 6.81 | 828.8 | -23.4% |
| deepseek/deepseek-flash | Hybrid K=10 + rules | 0.4243 | 9.99 | 1082.4 | 0.0% |
| glm/glm-4-flash-250414 | Hybrid K=5 + rules | 0.3663 | 5.00 | 706.3 | -37.4% |
| glm/glm-4-flash-250414 | K=5 + 补检 + rules | 0.3647 | 6.81 | 868.2 | -23.0% |
| glm/glm-4-flash-250414 | Hybrid K=10 + rules | 0.3491 | 9.99 | 1127.4 | 0.0% |

## 配对差异（新方案 − 基线，F1）

| 模型 | 比较 | 平均 F1 差 | 上升 / 下降 / 不变 |
|---|---|---:|---:|
| deepseek/deepseek-flash | Hybrid K=5 + rules − Embedding K=5 | -0.0093 | 50 / 58 / 232 |
| deepseek/deepseek-flash | K=5 + 补检 + rules − Hybrid K=5 + rules | 0.0099 | 26 / 15 / 299 |
| deepseek/deepseek-flash | K=5 + 补检 + rules − Hybrid K=10 + rules | -0.0168 | 34 / 50 / 256 |
| deepseek/deepseek-flash | Hybrid K=5 + rules − Hybrid K=10 + rules | -0.0267 | 30 / 54 / 256 |
| glm/glm-4-flash-250414 | Hybrid K=5 + rules − Embedding K=5 | 0.0003 | 41 / 53 / 246 |
| glm/glm-4-flash-250414 | K=5 + 补检 + rules − Hybrid K=5 + rules | -0.0015 | 22 / 16 / 302 |
| glm/glm-4-flash-250414 | K=5 + 补检 + rules − Hybrid K=10 + rules | 0.0156 | 34 / 29 / 277 |
| glm/glm-4-flash-250414 | Hybrid K=5 + rules − Hybrid K=10 + rules | 0.0171 | 37 / 36 / 267 |

重复轮次：1。以上为逐轮均值的简单汇总；轮间波动见 summary.json。
