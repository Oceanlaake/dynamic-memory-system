# 实验结果索引

命名规则：`split-*` 为冻结的数据划分与题单，`run-v<版本>-<日期>` 为一次完整运行，`summary-*` 为跨运行汇总。

| 路径 | 内容 | 状态 |
|---|---|---|
| [`split-v1/`](split-v1/summary.md) | 冻结的开发 / 测试划分与题单（`bonus-*-cases.json`、`recall-*-cases.json`），以及召回测试、关系回归、Web 验收记录与截图 | 当前（所有运行共用） |
| [`run-v1-2026-11-05/`](run-v1-2026-11-05/README.md) | v1：11 月 5 日，旧版答案提示词；DeepSeek Flash 与 GLM-4-Flash 的五组方法对照（340 题测试集） | 当前（作为版本对照） |
| [`run-v2-2026-11-09/`](run-v2-2026-11-09/README.md) | v2：11 月 9 日最终运行，最终提示词，DeepSeek Flash。`test-baselines/` 测试集五组方法；`test-graph/` 测试集 Fixed / Forced / Adaptive Graph；`dev-graph/` 开发集 650 题复核 | **当前（最终结论）** |
| `summary-v1-v2.json` | v1 与 v2 合并后的全部指标与逐题配对比较；解读见 [合并实验结果](../../docs/results/results-v1-v2.md) | **当前** |
| [`graph-recall-ablation/`](graph-recall-ablation/) | Graph 确定性证据召回消融（不调用模型；Hybrid K=5，1–4 跳） | 当前 |
| [`archive/`](archive/README.md) | 早期探索、快速检查、旧版 Graph 答案对照 | 历史 |
| `llm-comparison/` | 逐请求 checkpoint 与原始响应 | 仅本地，Git 忽略 |

生成方式：`scripts/rerun_final.sh`（v2 运行与发布）、`scripts/consolidate_results.py`（合并汇总，不调用 API）。所有运行中标准答案只在检索和生成完成后用于评分。
