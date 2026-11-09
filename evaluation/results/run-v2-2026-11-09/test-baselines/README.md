# 测试集整体方法对照（最终重测）

340 题，deepseek-flash，最大输出 128 token，与 Graph 三组使用同一版答案提示词。
五组：Full Text / Embedding K5 / Hybrid K5 + rules / K5 + 补检 + rules / Hybrid K10 + rules。

- `summary.md` / `summary.json`：方法汇总与配对计数。
- `per-question.csv`：逐题标准答案、生成答案、F1/EM、状态、Memory ID 与 usage。
- `manifest.json`：冻结配置与数据 / 源码哈希；`actual-usage.json`：实际请求账本。
