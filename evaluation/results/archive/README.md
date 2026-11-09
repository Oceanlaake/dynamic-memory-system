# 历史结果归档

这里的结果已被后续版本取代，保留用于追溯开发过程，不作为最终结论引用。

| 路径 | 来源 / 时间 | 被什么取代 |
|---|---|---|
| `early-sweeps/` | 10 月中旬检索策略选型（BM25 / Embedding / Hybrid 参数扫描、conv-30 召回） | `split-v1/` 的冻结召回测试 |
| `bonus_quick_check/`、`bonus_quick_check_v2/` | 补检机制早期快速检查 | `docs/design/supplement-query-expansion.md` 与 11 月 5 日正式对照 |
| `state_diagnostics/` | 动态状态解析早期诊断 | `split-v1/` 关系回归 |
| `qa-compare-v1/` | 11 月 1 日 50 题先导问答对照 | 11 月 5 日 340 题对照（`run-v1-2026-11-05/`） |
| `graph-answer-early/` | 11 月 8 日 Graph 一律扩图 v1 / v2（旧提示词，F1 0.3896 → 0.3992） | 最终三组对照（`run-v2-2026-11-09/`） |
