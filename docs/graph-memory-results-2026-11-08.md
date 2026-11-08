# Graph Memory 离线消融结果（2026-11-08）

本实验只评估 Graph Memory 是否找回更多答案证据，不调用答案 LLM，也不报告答案 F1。
逐题结果见 [`evaluation/results/graph-memory-v1.json`](../evaluation/results/graph-memory-v1.json)。

## 配置

- 数据：冻结的自定测试集 `conv-47`、`conv-48`，340 道可映射 category 1–4 QA。
- Memory：`outputs/final-test-v1/memories`。
- 初始检索：Hybrid，BM25 0.4 + `all-MiniLM-L6-v2` 0.6，K=5。
- Graph：最大 3 跳，最多新增 5 条 Memory。
- Gold 用途：只在 Graph 检索完成后计算 Memory 集合召回和原始证据 Turn 召回；建图和遍历不读取 Gold。

## 结果

| 方法 | Memory 集合召回 | 原始证据 Turn 召回 | 平均候选 |
|---|---:|---:|---:|
| Hybrid K=5 | 59.92% | 68.07% | 5.00 |
| Hybrid K=5 + Graph Memory | 64.93% | 72.77% | 9.29 |

- Memory 召回提高 5.01 个百分点；29/340 题改善，311 题不变，没有下降题。
- 原始证据 Turn 召回提高 4.70 个百分点；24/340 题改善，316 题不变，没有下降题。
- 329 题新增了 Graph 候选；其中 234 题达到“最多新增 5 条”的预算上限。
- 平均访问 254.33 个图节点。访问节点只是本地遍历，不进入 LLM 上下文；只有选中的新增 Memory 进入回答链路。

## 解释边界

Graph Memory 提升的是候选证据召回，不自动证明最终答案 F1 提升。平均候选从 5.00 增至
9.29，会增加答案模型输入 Token，也可能带来上下文干扰。它与固定 K=10、现有查询补检的
候选预算并不相同，因此不能直接宣称更高效或全面更优。

该结果证明当前实现能够通过显式状态槽位和证据 Turn 路径找回 Top-K 外的相关 Memory，且
路径可在 Web 和结果 JSON 中审计。后续如需形成答案质量结论，应在相同答案模型、输出预算和
候选预算下增加 Graph 组，并同时报告 F1、Token、错误与拒答。
