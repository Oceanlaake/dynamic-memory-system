# 补选机制二：Graph Memory 自适应补选（Bonus）

另一种补选实现见 [补选机制一：查询驱动证据补检](supplement-query-expansion.md)；最终数字见 [v1 + v2 合并实验结果](../results/results-v1-v2.md)。

本项目现在提供独立于原有“同槽位/证据邻域补检”的 Graph Memory 实现。图只从结构化
Memory 及其来源字段构建，不读取 QA 标准答案、参考 evidence 或评测标签。

## 图模型

节点分为六类：

| 节点 | 含义 |
|---|---|
| `memory` | 一条完整结构化 Memory |
| `subject` | Memory 描述的人物 |
| `slot` | `subject + attribute` 状态槽位 |
| `value` | 结构化取值 |
| `session` | 来源会话 |
| `turn` | 来源 `dia_id` |

边分为：`ABOUT`、`IN_SLOT`、`HAS_VALUE`、`OBSERVED_IN`、`SUPPORTED_BY`、
`NEXT_STATE` 和 `NEXT_TURN`。`NEXT_STATE` 连接同一槽位中按显式/观测时间排序的相邻
Memory；`NEXT_TURN` 连接同一 Session 中相邻的证据轮次。图导出时保留方向，查询遍历时
允许沿两个方向查找证据。

## 查询流程

1. 普通 BM25 / Embedding / Hybrid 返回 Top-K，作为 Graph 种子。
2. 在图中进行有界 best-first traversal，最多 1–4 跳。
3. 同槽位状态链可直接扩展；相邻 Turn、人物或 Session 路径还需通过问题词相关性过滤。
4. 按路径强度与问题相关性联合排序，当前权重为 25% 路径先验、75% 词项相关性，最多新增配置数量的 Memory。
5. 每条新增候选在 `score` 中保留用于排序的 Graph 联合分数，并保留 `graph_hops`、`graph_path`；响应的 `graph.paths` 同时保留完整边类型。
6. 扩展候选继续进入原有状态关系分析和统一 LLM 回答链路。

Graph 扩展默认关闭，因此不会改变仓库已有 340 题正式实验。最终提交推荐的模式是自适应重试
（`graph_expand` + `graph_retry_on_refusal`，4 hop / 8 memories），结果见
[最终报告](../final/final-report.typ) 第 4 章。Web 中可独立开关，与原有
查询驱动补检组合或分别运行。

## 使用

查询接口示例：

```json
{
  "sample_id": "conv-30",
  "question": "What is Jon's current dance studio status?",
  "top_k": 3,
  "graph_expand": true,
  "graph_retry_on_refusal": true,
  "graph_max_hops": 4,
  "max_graph_memories": 8
}
```

`graph_retry_on_refusal` 会先使用原始 Top-K 证据回答；只有模型因证据不足而拒答时，
才执行 Graph Memory 扩展并重试。这能保留简单问题的原始答案，避免不必要的图证据干扰。
前端在启用 Graph Memory 时默认使用 4 hop / 8 memories，较宽的预算只会应用于拒答后的重试。

导出完整 Graph JSON：

```bash
.venv/bin/python -m backend.graph_memory \
  --sample-id conv-30 --memory-dir outputs/memories \
  --out outputs/graphs/conv-30.json
```

离线消融（Gold 只在检索完成后评分）：

```bash
.venv/bin/python -m evaluation.graph_memory \
  --cases evaluation/results/split-v1/recall-test-cases.json \
  --memory-dir outputs/final-test-v1/memories \
  --retriever hybrid --top-k 5 --max-hops 3 --max-graph-memories 10 \
  --json-out evaluation/results/graph-recall-ablation/graph-memory-v1.json
```

DeepSeek 答案 F1/EM 三组对照（Fixed K5 / Forced Graph / Adaptive Graph 同轮运行，逐请求
checkpoint，可中断续跑）。脚本默认 3 hop / 5 条，复现最终结果需显式传入 4 / 8：

```bash
DEEPSEEK_API_KEY=... .venv/bin/python -m evaluation.graph_answer \
  --cases evaluation/results/split-v1/bonus-test-cases.json \
  --memory-dir outputs/final-test-v1/memories \
  --output-dir evaluation/results/llm-comparison/graph-memory-deepseek-adaptive-final-v2 \
  --provider deepseek --model deepseek-flash \
  --top-k 5 --max-hops 4 --max-graph-memories 8
```

认证信息只从环境读取，不写入结果。先加 `--plan-only` 可在不调用 API 的情况下核对题数、
唯一上下文数和哈希。

Graph Memory 是有界结构化多跳检索，不是开放式自主 Agent。当前不会推断原数据中不存在的
因果边，也不会自动裁决真假；这种边界保证路径可复核、成本可控，并避免把图连接误写成事实。

最终三组对照、340 题 Hybrid 离线召回消融及限制见 [Graph Memory 结果](../results/graph-early-2026-11-08.md)。
