# 最终提交材料

| 材料 | 文件 | 说明 |
|---|---|---|
| 最终报告 | [final-report.pdf](final-report.pdf) | 5 页，按 SRS 版式编写；源文件 [final-report.typ](final-report.typ)，编译：`typst compile docs/final/final-report.typ` |
| 最终展示 | [final-presentation.pdf](final-presentation.pdf) | 10 页，沿用中期汇报模板 |
| 项目代码 | 仓库本身 | 启动方式见根目录 [README](../../README.md)（`./demo/start_demo.sh --final`） |
| 过程记录 | [`process/`](../../process/README.md) | 五次组会纪要、技术决策、协作截图与过程大纲 |

一键生成全部提交物：`./scripts/package_submission.sh`（输出到 `submission/`）。

## 数字口径

最终数字以报告第 4 章与 [v1 + v2 合并实验结果](../results/results-v1-v2.md) 为准：

- v1（11 月 5 日）与 v2（11 月 9 日）使用相同的题单、对话、冻结 Memory 与检索代码，差异只在答案提示词、输出上限与模型。
- 方法之间只在同一次运行内比较；跨运行只做同题配对的“提示词版本效应”分析。
- v2 测试集：Hybrid K5 0.4611 → K5 + 补检 0.4823 / Adaptive Graph 0.4837（无下降题），Hybrid K10 0.5014，Full Text 0.5692；开发集 650 题复核补选收益成立。
- F1 / EM 为本地英文 token 口径，不等于语义正确率；拒答、错误与跳过均计 0 分。
