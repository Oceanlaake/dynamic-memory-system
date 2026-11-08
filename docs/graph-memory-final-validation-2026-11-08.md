# Graph Memory 最终提交前验证（2026-11-08）

本轮验证覆盖 Graph 新增后的功能、兼容性、参数边界、真实冻结数据、答案质量和成本。除明确标注的
DeepSeek 成对答案实验外，其余检查均为本地离线执行。

## 自动化门禁

| 检查 | 结果 |
|---|---|
| Python 全量测试 | 188 passed |
| Graph/API/Schema 专项 | 40 passed |
| Demo 离线验收 | 8/8 passed |
| Python `compileall` | passed |
| 前端 TypeScript + Vite production build | passed |
| `npm audit --audit-level=moderate` | 0 vulnerabilities |
| 340 题 Graph 检索结果重跑 | 配置、摘要和逐题结果完全一致；已刷新当前源码 SHA-256 |
| DeepSeek 646 个上下文重新规划 | 与原实验 `request-contexts.json` 字节级一致 |
| 跟踪差异凭据扫描 | clean |

前端生成包约 995.9 kB，Vite 给出大于 500 kB 的非阻断性体积警告；不影响构建成功，但后续可用
动态 import/code splitting 优化。最终提交前仍建议人工打开一次 Graph 面板，核对当前浏览器尺寸下的
路径布局；自动化已经覆盖类型、构建、API 字段和路径数据。

本轮在 Graph 候选回传真实排序分数后重跑了 3 种检索器 × 4 种跳数 × 3 种预算的边界矩阵，
共 12,240 次题目配置运行，全部通过。Graph 关闭时，线上 `/api/query` 与 `/api/retrieve` 的
Top-K ID 及顺序完全一致；开启后，真实 DeepSeek 场景仍回答 `Shadow and Coco`，并引用
`mem-conv41-466` 和 Graph 找回的 `mem-conv41-450`。

## Graph 专项边界

新增永久回归覆盖：默认关闭不改变原候选、无可用种子安全退化、hop 只允许 1–4、新增候选只允许
1–50、候选预算不丢初始 Top-K、构建顺序确定、内容改变时缓存失效、集合槽位不误建
`NEXT_STATE`、三跳 Turn 路径、Graph F1 成对评分及 Gold 不进入检索。

在 340 题上执行 4 种 hop 上限 × 3 种预算（1/5/50），并对 BM25、Embedding、Hybrid 三种
初始检索器检查：候选不超预算、无重复新增、每条新增都有路径、路径不超 hop、Graph 召回逐题不低于
固定 K。全部通过。预算 5 的 Hybrid 结果如下：

| 最大跳数 | Memory 召回 | Turn 召回 | 平均候选 |
|---:|---:|---:|---:|
| 1 | 61.89% | 69.89% | 6.21 |
| 2 | 63.66% | 71.53% | 8.72 |
| 3 | 65.30% | 73.17% | 9.25 |
| 4 | 65.45% | 73.47% | 9.46 |

正式默认保持 3 跳、最多新增 5 条，避免为小幅召回继续扩大上下文。

最终优化没有继续增加候选，而是把 Graph 候选分数从“75% 路径、25% 问题相关性”调整为
“25% 路径、75% 问题相关性”。该规则先在开发集冻结，再在 `conv-47/48` 测试集运行；测试集
Memory 召回从优化前的 64.93% 提升到 65.30%，DeepSeek F1 从 0.3953 提升到 0.3992。

## 六样本完整图与 API

六份冻结 Memory 均成功导出，节点 ID 唯一、每条边端点存在，并通过 `GraphDocument` 根 Schema：

| 样本 | Memory | 节点 | 边 |
|---|---:|---:|---:|
| conv-41 | 492 | 1,522 | 2,697 |
| conv-42 | 431 | 1,301 | 2,351 |
| conv-43 | 464 | 1,440 | 2,483 |
| conv-44 | 514 | 1,542 | 2,865 |
| conv-47 | 483 | 1,494 | 2,582 |
| conv-48 | 498 | 1,509 | 2,613 |

随后对六个样本分别发起真实 `/api/query` Hybrid K=5 + Graph 请求；全部返回 200，候选均不超过
10，`paths` 数量与新增 Memory 数一致，所有路径不超过 3 跳。答案生成使用测试替身，因此该 API
集成检查没有额外模型费用。

## DeepSeek F1 成对实验

使用用户授权的临时 DeepSeek 凭据运行 `deepseek-flash`；凭据通过无回显标准输入只注入进程，未写入
代码、`.env`、日志或结果。340 题产生 646 个唯一上下文，646/646 请求完成，API 错误为 0。

| 方法 | F1 | EM | 证据召回 | 输入 Token | 拒答 |
|---|---:|---:|---:|---:|---:|
| Hybrid K=5 | 0.3896 | 0.2000 | 59.92% | 669.1 | 114 |
| Hybrid K=5 + Graph | 0.3992 | 0.1882 | 65.30% | 1,030.6 | 108 |

F1 平均增加 0.0096（约 0.96 个百分点），33 题改善、34 题下降、273 题不变；EM 下降 1.18 个
百分点，平均输入 Token 增加 54.0%。因此最终结论是“证据召回明确提升、平均 F1 小幅提升，但
严格匹配和上下文效率下降”，而不是 Graph 全面优于固定 K。

可提交的聚合数据在
[`evaluation/results/graph-answer-deepseek-v2-summary.json`](../evaluation/results/graph-answer-deepseek-v2-summary.json)；
包含模型输出的逐请求 checkpoint 留在本地 Git 忽略目录，不含认证信息。
