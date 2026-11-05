# 最终实验结果包

340 题、单轮、两模型完成、五组方法，另一个模型因服务繁忙阻塞。以 [正式分析](../../../docs/large-scale-results-2026-11-05.md) 为解释来源。

- `summary.md` / `summary.json`：方法汇总与配对计数；blocked 项不是有效成绩。
- `per-question.csv`：模型 × 题目 × 方法，含标准答案、生成答案、F1/EM、状态、记忆 ID 和实际 usage。
- `case-examples.json`：两正两负案例，明确为极端示例，不代表总体。
- `manifest.json`：原始冻结配置和数据/源码哈希。
- `actual-usage.json`：实际请求账本，和独立方法等价用量分开。
- `export-verification.json`：导出完整性及逐题 F1/EM 核对记录。

不包含密钥、逐请求原文、重复对话上下文、失败重试日志或恢复缓存。原始审计材料仍保存在本机被 Git 忽略的 `evaluation/results/llm-comparison/large-scale-v1/`。

现有 340 题是已暴露的自定测试集；GLM 的 Full Text 大量协议失败，不能作为正常语义基线。CSV 空答案结合 status 识别拒答/错误，不把空白视为有效答案。

复现入口：`python -m evaluation.final.large_scale --help`；重新导出：`python -m evaluation.final.export_submission --source <本地完整结果目录> --output <新空目录>`。导出本身不调用 API；重新生成实验答案会产生真实 API 消耗。
