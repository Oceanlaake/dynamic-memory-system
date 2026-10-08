// 软件需求工程 · Project Proposal
// 内容依据：docs/项目要求大纲.pdf（智能体动态记忆管理项目要求）。
// 团队信息、定量目标和最终 UML 用例图待团队确认。

#set page(
  paper: "a4",
  margin: (top: 1.8cm, bottom: 1.8cm, left: 2cm, right: 2cm),
  numbering: "1",
)
#set text(font: ("STsong"), size: 10pt, lang: "zh")
#set par(justify: true, leading: 0.62em)
#set heading(numbering: "1.")
#show heading.where(level: 1): set text(size: 13pt, weight: "bold")
#show heading.where(level: 2): set text(size: 10.5pt, weight: "bold")

#align(center)[
  #text(size: 18pt, weight: "bold")[智能体动态记忆管理系统：项目提案]

  #v(0.3em)
  #text(size: 10.5pt)[Vision and Scope & Feature Roadmap]

  #v(0.55em)
  团队名称：待填写　｜　团队编号：待填写　｜　版本：初稿
]

#v(0.7em)

= Project Background / Problem

在长程、多轮对话中，人物的计划、偏好和状态会随时间变化。普通全文阅读或向量检索可以找到相关历史内容，却可能同时取回旧状态和新状态。如果系统没有区分保留、更新、替代和矛盾关系，就可能依据已经过时的信息回答当前问题。

本项目的机会在于把“检索到什么”进一步推进到“在当前问题和时间条件下，哪些记忆仍然有效”。LoCoMo 长期多会话对话提供了对话、问答、证据轮次和事件摘要，可用于构建可追溯记忆，并检验动态状态解析能否改善回答。

= Business Objectives

本课程项目希望交付一个可运行、可检查的动态记忆原型，覆盖从原始对话到结构化 Memory、从问题到有效记忆、从有效记忆到答案的完整流程。

*成功标准*以课程要求和可复现的测试结果为准：

- 对课程选定的 6 段 LoCoMo 对话完成处理，其中 4 段用于开发，2 段作为独立测试集；导出统一格式的结构化 Memory JSON。
- 对输入问题自动检索相关历史 Memory，判断保留、更新／替代及无法消解的矛盾，确定与问题及时间条件匹配的有效 Memory，并生成答案。
- 在 Web 端能查看结构化记忆、原始证据、相关历史 Memory、状态关系和最终答案。
- 在独立测试集上报告问题回答 F1、证据记忆检索 Recall\@K、动态状态更新判断准确率，并与 Full Text 和不做状态关系判断的 Vector RAG 对照。具体数值目标与 K 值在评测方案中确定，不在提案阶段预设结果。

= Product Vision

产品是面向长对话的动态记忆管理与问答 Web 应用。它主要供项目评测人员和开发、研究成员使用：前者通过界面检查答案与证据，后者导入对话、检查 Memory 质量并分析状态变化。

核心价值是让回答建立在*可追溯且当前有效*的记忆之上。与直接使用全文上下文或仅按相似度召回 Memory 的方式相比，本系统显式记录记忆的来源和时间，并在回答前解析记忆间的状态关系；旧事实仍作为历史证据保留，而不会被默认当作当前状态。

= Users / Stakeholders

#table(
  columns: (1.35fr, 3.65fr),
  inset: 5pt,
  stroke: 0.45pt,
  [*角色*], [*主要关注与操作*],
  [评测人员／演示观众], [输入问题，查看答案、有效记忆、历史证据和状态解析过程；了解评测结果。],
  [开发与研究成员], [导入课程对话，构建和检查结构化 Memory，运行查询与对照评测，分析错误。],
  [课程团队／项目干系人], [检查功能范围、交付物、过程记录，以及结果是否符合课程要求。],
)

LoCoMo 数据集是外部数据来源，不是直接操作系统的用户。

= Project Scope

== In Scope

- 使用课程选定的 6 段 LoCoMo 对话；从原始会话中抽取人物、事件、时间、状态等信息，形成至少包含内容、时间和来源会话／轮次的结构化 Memory，并导出统一 JSON。
- 针对问题从完整历史中检索相关 Memory，判断 RETAIN、UPDATE／SUPERSEDE；对证据不足以消解的冲突保留并标记，确定当前有效 Memory，再生成答案。
- 提供 Web 页面，用于浏览 Memory 与原始证据，以及查看问题、候选记忆、状态关系、有效记忆和答案。
- 进行功能测试和独立测试集评测，报告规定指标与 Full Text、Vector RAG 对照结果；交付源代码、Memory JSON、测试结果、报告和展示材料。

== Out of Scope

- 面向任意数据源的通用对话平台、生产环境部署、多用户权限和实时在线同步。
- Graph Memory、多跳关系建模、Memory 合并与压缩、自适应检索及复杂时间推理。这些属于后续扩展，只有核心流程稳定后才考虑。

== Limitations / Exclusions

项目评测以课程选定的数据和问题为主，结论不能直接推广到所有真实对话场景。状态是否有效依赖抽取质量、时间信息和可获得的证据；遇到证据不足或互相矛盾的记忆，系统应呈现冲突及来源，避免把不确定结论伪装成已确认事实。具体模型、阈值和定量验收线将在系统设计与 SRS 中细化。

= Scope Model

下图是本提案的上下文图，标出系统边界、输入和输出。团队完成 UML 用例图后，可用正式用例图替换或补充此图；建议覆盖“导入对话、查看 Memory、输入问题、查看证据与状态关系、导出 JSON、运行评测”。

6.1 System Context Diagram

展示 LoCoMo、系统、Evaluator/Developer、输入输出。

6.2 Use Case Diagram

展示两个主要 actor 与核心 use cases。

#figure(
  table(
    columns: (1.35fr, 0.45fr, 2.2fr, 0.45fr, 1.35fr),
    inset: 6pt,
    stroke: 0.45pt,
    align: center,
    [*LoCoMo 课程数据* #linebreak() 对话、问答与证据], [→],
    [*动态记忆管理系统* #linebreak() Memory 构建 · 状态解析 · 问答 · 可视化], [←],
    [*评测人员／开发成员* #linebreak() 导入、查询、检查],
    [], [], [], [→], [答案 · 证据 · 关系 · JSON · 指标],
  ),
  caption: [系统上下文图（提案版）],
)

// 团队 UML 用例图完成后，可将图片放在本目录，并在此处插入：
// #figure(image("use-case-diagram.svg", width: 90%), caption: [系统用例图])

= Core Features

#table(
  columns: (0.95fr, 2.2fr, 2.45fr),
  inset: 5pt,
  stroke: 0.45pt,
  [*功能*], [*用户能够做什么*], [*系统提供的结果*],
  [记忆构建], [导入并浏览多会话对话。], [抽取结构化 Memory；展示内容、时间、来源，并可导出 JSON。],
  [问题查询], [输入与对话历史相关的问题。], [从完整历史自动检索候选 Memory，生成有依据的答案。],
  [状态解析], [查看候选记忆如何影响当前答案。], [显示 RETAIN、UPDATE／SUPERSEDE 或冲突关系，以及最终有效 Memory。],
  [证据追溯], [从答案或 Memory 返回原始对话。], [展示来源会话、轮次和相关历史记录。],
  [结果评估], [查看系统与对照方法的表现。], [提供 F1、Recall\@K、状态更新判断准确率及对照分析。],
)

= Feature Roadmap

#table(
  columns: (1.05fr, 0.9fr, 3.2fr),
  inset: 5pt,
  stroke: 0.45pt,
  [*阶段*], [*优先级*], [*计划能力与可检查产出*],
  [阶段 1：基础闭环], [核心], [确定 JSON 结构和数据划分；完成 6 段对话导入、Memory 抽取与来源追溯；实现基础查询和 Web 浏览，形成可演示流程。],
  [阶段 2：动态解析], [核心], [加入相关记忆检索、RETAIN 与 UPDATE／SUPERSEDE 判断、冲突标记和有效记忆选择；在 Web 中呈现解析链路并生成答案。],
  [阶段 3：验证交付], [核心], [在独立测试集上运行三项指标和 Full Text、Vector RAG 对照；修复主要问题，交付应用、JSON、测试结果和报告。],
  [后续扩展], [可选], [视时间与核心结果，尝试 Graph Memory、多跳关系、记忆合并压缩、自适应检索或更复杂的时间推理。],
)

上述阶段表示功能依赖顺序，具体负责人和日期以团队工作流程与阶段计划为准。扩展功能不影响核心交付的完成判定。
