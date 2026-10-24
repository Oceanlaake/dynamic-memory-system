# 项目过程大纲

## Milestone 1 和 2 项目启动与 Proposal

- 9 月 28 日：创建项目仓库，搭建基础目录并添加团队成员。
- 10 月 7 日：形成 Team Workflow 初稿，完成 Proposal 分工并确定第一次会议时间。
- 10 月 8 日：召开第一次会议，集中讨论 Proposal 的技术方案、文档结构和内容分工。
- 10 月 9—10 日：完成 Proposal、Team Workflow 及相关 PDF，完成 Milestone 1 和 2 的交付。

## Milestone 3 和 4 系统设计与功能开发

- 10 月 15 日：召开第二次会议，明确系统主流程：LoCoMo 长对话经过结构化 Memory 抽取、候选记忆检索、动态状态判断和有效记忆选择，最终生成带证据的答案并在 Web 端展示。
- 10 月 15 日：完成模块分工：Memory Schema、数据抽取、Retrieval、Dynamic State 和 Web Integration 分别由成员负责；统一采用 Python FastAPI 后端、React TypeScript 前端和 JSON 数据契约。
- 10 月 15—16 日：确定 Memory 字段、粒度与证据回链方式，完成 LoCoMo 示例数据到结构化 Memory 的初步链路。
- 10 月 17 日：完成 B1 检索模块、接口契约和评估管道；完成 B2 动态状态解析，支持 RETAIN、UPDATE、SUPERSEDE、CONFLICT 关系及 Effective Memory 选择；形成前端 Web Demo。
- 10 月 18 日：更新 Memory 抽取流程并生成正式抽取结果，推进 SRS 结构设计。
- 10 月 19 日：同步 `effective_at` 等接口字段，完成前后端合并、可运行 Web Demo、真实数据接入和检索参数定标；工作重心转向 SRS 与中期展示。

## 中期材料与展示准备

- 10 月 19 日：将团队分为 SRS 组和中期展示组。SRS 组负责需求文档编写、审核与排版；展示组负责 Presentation、PPT、代码集成和 Demo 验收。
- 10 月 20 日：完善 Demo 启动方式和异常输入处理，形成可用于中期展示的端到端流程。
- 10 月 20 日 21:29—21:49：召开第三次会议，展示并审查 SRS、中期 PPT 和前端 Demo，确认三项材料主体基本完整。
- 10 月 20 日会议后：根据反馈补充 SRS 细节，优化 PPT 内容顺序、排版和讲解重点，继续修复 Demo 展示细节并检查现场运行流程。
- 10 月 21—22 日：完成中期 SRS、汇报 PPT 和 Demo 的一致性检查与最终收尾，形成中期阶段交付材料。

## 中期阶段成果

- 已建立可追溯的结构化 Memory 数据格式，并保留原始会话与 `dia_id` 证据。
- 已实现候选记忆检索、动态状态关系判断、Effective Memory 选择和答案生成链路。
- 已完成前后端接口对接，可在 Web 页面展示 Query、Candidate Memory、Relation、Effective Memory、Answer 和 Source。
- 已建立检索与状态解析评估用例，并完成主要模块测试和 Demo 验收脚本。
- 已形成 SRS、中期 PPT、会议记录和可运行 Demo，完成中期阶段材料准备。
