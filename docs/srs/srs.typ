// 智能体动态记忆管理系统 · 软件需求规格说明书（SRS）
// 负责人 A：Introduction / Business Requirements / User Requirements / Constraints / 排版整合

#set document(
  title: "智能体动态记忆管理系统：软件需求规格说明书",
  author: "喵喵喵喵喵",
)

#set page(
  paper: "a4",
  margin: (top: 2.2cm, bottom: 2.2cm, left: 2.2cm, right: 2.2cm),
  footer: context [
    #set text(size: 7.8pt, fill: luma(120))
    #line(length: 100%, stroke: 0.4pt + luma(205))
    #v(0.15em)
    智能体动态记忆管理系统 · 软件需求规格说明书
    #h(1fr)
    第 #counter(page).display() 页
  ],
)

#set text(
  font: ("Times New Roman", "STSong", "SimSun"),
  size: 9.6pt,
  lang: "zh",
)

#set par(
  justify: true,
  leading: 0.85em,   // 行间距：数值越大，行与行越松
  spacing: 0.8em,    // 段与段之间的间距
  first-line-indent: (amount: 2em, all: true),
)


#set heading(numbering: "1.")
#set list(spacing: 0.55em)
#set list(indent: 0.9em, spacing: 0.32em)

// 黑白版式：不设彩色，靠字号与字重区分层级
#show heading.where(level: 1): it => block(above: 1.6em, below: 1.2em)[
  #set text(
    font: ("Microsoft YaHei", "SimHei"),
    size: 15pt,
    weight: "bold",
    fill: black,
  )
  #it
  #v(-0.3em)
  #line(length: 100%, stroke: 0.8pt + luma(110))
]
#show heading.where(level: 2): it => block(above: 1.6em, below: 1.2em)[
  #set text(
    font: ("Microsoft YaHei", "SimHei"),
    size: 12pt,
    weight: "bold",
    fill: black,
  )
  #it
]
#show heading.where(level: 3): set text(size: 10.8pt, weight: "bold", fill: black)

// 表格：细黑边框 + 浅灰表头，取消表格内首行缩进
#set table(stroke: 0.4pt + luma(110), inset: (x: 4pt, y: 3pt))
#show table: set text(size: 8.7pt)
#show table.cell.where(y: 0): set table.cell(fill: luma(238))
#show table.cell: it => {
  set par(justify: false, first-line-indent: 0em)
  it
}

#let note(body) = block(
  width: 100%,
  fill: luma(246),
  stroke: (left: 2pt + luma(110)),
  inset: (x: 7pt, y: 5pt),
  radius: 2pt,
  {
    set par(first-line-indent: 0em)
    body
  },
)

#align(center)[
  #text(
    font: ("Microsoft YaHei", "SimHei"),
    size: 18pt,
    weight: "bold",
    fill: black,
  )[智能体动态记忆管理系统]

  #v(0.12em)
  #text(size: 12.5pt, weight: "bold", fill: black)[软件需求规格说明书（SRS）]

  #v(0.3em)
  #text(size: 9pt, fill: luma(80))[
    软件需求工程　|　团队：喵喵喵喵喵　|　版本：v1.4　|　2026-10-20
  ]
]
#v(0.35em)
#line(length: 100%, stroke: 0.8pt + luma(110))
#v(0.45em)

= Introduction

== 目的与读者

本文定义智能体动态记忆管理系统的需求基线：问题、业务目标、参与者与用例、功能与数据要求、外部接口、质量属性、约束，以及需求到用例、接口与测试的追溯关系。读者为课程评审、开发测试与演示人员。需求分 UR／FR／CON，优先级 M／S／C 表示必须／应该／可选，编号全文稳定引用，第 9 章给出统一追溯表。

#note[
  *阅读约定*　M 为验收必备；S 为应完成、允许标注未完成；C 为本期可选。验收均为可观察、可执行的条件。
]

== 背景与问题

长程多轮对话中，人物的计划、偏好与状态会随时间变化。全文阅读或普通向量检索能找到相关历史内容，却可能同时返回新旧状态，从而依据过时信息作答。本项目的重点不是“检索到相关文本”，而是在当前时间语境下判断哪些记忆仍然有效、答案能否只由这些记忆支撑。系统以 LoCoMo 为输入，构建可追溯 Memory、检索候选、判定关系并生成带证据的答案；旧事实仅作历史证据。

固定 Top-K 检索只能保证候选与问题在检索分数上的相关性，不能保证同一主体、同一属性的完整状态历史都进入候选集；而状态解析只能处理已经进入候选集的 Memory。当关键前序状态、后续更新或时间锚点被 Top-K 截断时，即使解析规则正确，也无法重构完整状态链。因此，系统以现有混合检索作为可复现基线，并将“由初始候选触发、面向同一状态槽位的局部历史扩展”列为后续应该实现和对照评测的能力。

== 系统范围

系统覆盖“对话导入 → Memory 构建 → 初始检索 → 局部状态历史扩展 → 状态解析 → 作答 → 评测”闭环。输入为 LoCoMo 对话、问题及标注；输出为 Memory JSON、候选与有效 Memory、状态关系、带证据的答案及指标，均可回溯到会话与轮次。本期交付单用户 Web 原型：后端提供检索与全链路查询 API，前端展示数据设置、提问、候选记忆、动态状态、答案与证据。其中初始检索和状态解析为当前基线，局部状态历史扩展为 S 级演进需求。系统不面向任意数据集或实时聊天平台，不提供生产部署、账号权限、多人协同与移动端适配，也不自动裁决冲突；完整 Cue–Tag–Content Graph、开放式多跳智能体、Memory 合并压缩与复杂时间推理仅作 Bonus。

== 术语

*Memory* 是可独立检索的结构化事实单元，含主体、类型、内容、时间与证据；*初始候选* 是检索器返回的 Top-K；*状态槽位* 是由主体与可比较属性标识的一组状态 Memory；*扩展候选* 是以初始候选为种子、从同一状态槽位补充的历史 Memory；*有效记忆* 是在当前问题语境下仍成立、可用于作答的 Memory。*RETAIN／UPDATE／SUPERSEDE／CONFLICT* 分别表示确认保留、同主题补充、旧值被取代、先后不可定；*Recall\@K* 是答案所需记忆出现在前 K 条初始候选中的比例；*dia_id* 是原始对话轮次的稳定标识。

= Business Requirements

== 业务目标

#table(
  columns: (0.55fr, 1.55fr, 3.0fr),
  inset: (x: 4pt, y: 3pt),
  table.header([*编号*], [*业务目标*], [*成功标准*]),
  [BO-01], [结构化记忆构建], [10 个样本抽成统一 Schema 的 Memory；正式产物 4340 条，QA evidence 覆盖率 96.4%，全部通过校验。],
  [BO-02], [动态状态解析], [输出四类关系并选出有效记忆；冲突或证据不足时返回空答案，不编造结论。],
  [BO-03], [有依据的问答], [答案仅引用有效记忆的证据，100% 可回链 session／turn；检索分数不作为真假或新旧依据。],
  [BO-04], [可复现评测与展示], [一条命令生成三策略 Recall\@K、MRR 与关系准确率；Web 完整展示全链路；测试与构建可重复通过。],
)

业务价值是降低“依据过时信息作答”的风险。Proposal 中的答案 F1 与 Full Text／Vector RAG 对照属后续目标；本期以 Recall\@K、状态关系准确率和答案可信性为指标，并如实标注未完成项。

== 产品愿景

产品是面向课程评审与研发成员的长对话动态记忆问答 Web 应用：评测人员输入问题即可查看答案、候选、状态关系与原始证据；开发成员可导入对话、检查 Memory、运行评测并分析错误。与全文上下文或纯相似度检索相比，本系统显式记录来源与时间并在作答前解析状态关系，目标不是“召回更多内容”，而是“依据的记忆当前有效且可追溯”；证据不足时返回空答案。

= User Requirements

== 参与者

#table(
  columns: (1.15fr, 1.35fr, 2.6fr),
  [*参与者*], [*关注点*], [*主要操作*],
  [评测人员／演示观众], [答案是否正确、依据是否可见], [选样本与 Top-K，提问，查看候选、关系、有效记忆、答案与证据。],
  [开发与研究成员], [抽取质量、检索与判断是否可复现], [构建 Memory，配置检索与解析模式，运行评测与错误分析。],
  [课程团队／项目负责人], [是否满足课程要求、结果是否可信], [查看 Web 演示、评测指标与追溯材料。],
)

LoCoMo 是数据源而非 Actor；抽取、嵌入与状态解析器均为系统内部实现。

== 用户需求与用例

#table(
  columns: (0.5fr, 0.5fr, 3.2fr, 1.5fr),
  inset: (x: 4pt, y: 3pt),
  table.header([*需求*], [*用例*], [*目标与主要流程*], [*关联功能*]),
  [UR-01], [UC-01], [开发成员：解析 session／turn → 逐 session 抽取 → 补抽未引用 turn → 清洗、合并、校验并导出 JSON。], [FR-MEM-01–05],
  [UR-02], [UC-02], [评测人员：选样本与 Top-K 后提问；系统检索候选、解析状态、选有效记忆并返回答案与证据。], [FR-RET、FR-STS、FR-API],
  [UR-03], [UC-03], [评测人员：按排名查看内容、类型、相关度与命中来源，展开查看完整 Memory 与证据。], [FR-RET、FR-UI-02/03],
  [UR-04], [UC-04], [评测人员：以时间线查看四类关系、新旧内容与理由，并查看有效记忆及角色。], [FR-STS、FR-UI-04],
  [UR-05], [UC-05], [评测人员：由答案或 Memory 定位 session／turn 与原文；当前展示 dia_id 与 quote，完整回跳待 turns 接口。], [FR-UI-06、FR-API-05],
  [UR-06], [UC-06], [开发成员：由 qa.evidence 生成用例，比较三策略 Recall\@K 与 MRR，统计关系准确率与混淆矩阵。], [FR-EVL-01–04],
  [UR-07], [UC-07], [开发／演示：切换记忆目录、检索策略、解析模式与前端数据模式，确认降级提示与模拟标注。], [FR-API-02/03、FR-UI-01/02/05],
  [UR-08], [UC-08], [开发／评测：对当前状态、状态变化与持续时间问题，以初始候选为种子补充同一状态槽位的相关历史，再解析关系；证据仍不足时返回不确定，并与固定 Top-K 基线对照。], [FR-RET-07、FR-STS-09、FR-EVL-06],
)

用例关系：UC-02 包含 UC-03、UC-04，UC-05 在追溯证据时扩展 UC-02，UC-01 是 UC-02 与 UC-06 的前置条件；UC-07 为贯穿演示与评测的配置能力；UC-08 在初始检索可能缺失状态链证据时扩展 UC-02。全部用户需求均有对应功能需求与验收路径，详见第 9 章。




= Functional Requirements

系统以证据链为主线运行：Memory 构建把原始 turn 转为可比较事实；检索生成相关候选但不判断新旧；状态解析依据属性、时间和必要的模型判断选出有效记忆；API 与 Web 展示过程及答案；评测验证召回、关系和答案。各阶段保留 `sample_id`、`memory_id` 与 `dia_id` 的关联；证据不足、冲突未解或依赖失败时保守返回空结果。

下表按模块汇总 39 条细分需求。M／S／C 分别表示必须／应该／可选；“未实现”需求属于后续演进，不计入当前基线成果。

#table(
  columns: (0.8fr, 1.05fr, 2.85fr, 1.65fr),
  inset: (x: 3pt, y: 2.4pt),
  table.header([*模块*], [*需求编号*], [*核心行为*], [*验收重点／状态*]),
  [Memory 构建], [FR-MEM-01–05], [解析 session／turn，按 Schema 抽取；合并同事实证据但保留 A→B→A 状态变化；ID 唯一可复现，并有离线基线。], [Schema 100% 通过；QA evidence 覆盖率 ≥ 90%；证据可回链。],
  [初始检索], [FR-RET-01–06], [按样本返回 Top-K；支持 BM25／Embedding／Hybrid；分数归一、结果稳定；依赖异常时退回 BM25；完整 Memory 与时间不被修改。], [排序、`strategy`、`matched_by` 可检查；无命中或回退标记 `degraded`。],
  [历史扩展], [FR-RET-07、FR-STS-09], [以初始候选为种子补充同主体、属性的历史，再重建局部状态链；仍缺锚点或冲突未解时停止。], [专项用例中召回被 Top-K 遗漏的关键历史；S，未实现。],
  [状态与答案], [FR-STS-01–08], [按同槽位与时间判定 RETAIN／UPDATE／SUPERSEDE／CONFLICT，选择有效记忆；语义模糊时调用模型，失败回退规则。], [关系含理由；持续时间具备双锚点；冲突或证据不足时 `answer=null`；答案只引用有效记忆。],
  [服务接口], [FR-API-01–05], [提供健康、样本、记忆、检索、查询端点；Schema 为唯一契约；统一错误结构并限制 `top_k`；提供接口文档。], [契约测试通过；404／422 可复现；原始 turn 端点 S，未实现。],
  [Web 展示], [FR-UI-01–07], [展示数据设置、提问、候选、状态、答案与证据；支持模式切换、候选展开、关系高亮和退化提示。], [主链路可操作；模拟结果明确标注；证据回跳部分实现，评测页面未实现。],
  [评测], [FR-EVL-01–06], [由 QA evidence 生成检索用例，报告 Recall\@K、MRR 与关系指标；运行端到端异常测试，并规划答案及历史扩展对照。], [基线评测可复现；答案 F1、Vector RAG 与扩展方案对照未实现。],
)

= Data Requirements

原始数据为 `data/raw/locomo10.json`：10 个样本、292 个 session、5882 个 turn（1226 条带图片说明），开发集 8 个、测试集 2 个（conv-49、conv-50）。每样本一个记忆 JSON，含 `memory_id`、`subject`、`type`、`content`、`attribute`、`value`、`time`、`evidence`、`confidence` 与 `sample_id`；`attribute`、`value`、`confidence` 可选，其余必填，`evidence` 至少一条。

时间分三层：`session_id` 为来源会话，`date_time` 为对话时间（保留原串、可空），`effective_at` 为事件生效时间（`YYYY-MM-DD`，不确定必须为空）。追溯要求 `dia_id` 真实存在、`session_id` 由 `dia_id` 反推、`quote` 为原文连续子串否则置空但保留 `dia_id`。

数据分三档：`outputs/memories/` 为正式产物（4340 条），`data/demo_memories/` 为演示集（conv-30 的 15 条，由 5 条主链路记忆加 10 条干扰记忆组成），`data/memories/` 为 5 条回归样本；三者由 `DMS_MEMORY_DIR` 切换。实测被引用 turn 4143 个、QA evidence 覆盖率 96.4%，无重复 ID 与悬空 `dia_id`；仅处理课程公开数据，密钥只存于环境变量、`.env` 或 Keychain。

= External Interface Requirements

数据契约由 `APIs/` 三份 JSON Schema 构成，后两份通过 `$ref` 复用记忆定义；前端仅提交 `sample_id`、`question`、`top_k`，契约耦合集中在类型定义与请求封装。

配置分四组：检索侧 `DMS_RETRIEVER`、`DMS_EMBEDDING_MODEL`、`DMS_MEMORY_DIR`；状态侧 `DMS_STATE_RESOLVER`、`DMS_LLM_PROVIDER`、`DMS_LLM_MODEL` 及密钥（默认 `rules` 不联网）；前端 `DMS_API_TARGET` 指定代理目标并使用 `/api`；命令行提供启动、数据重建、验收及抽取、评测、测试命令。外部模型采用 OpenAI 兼容 REST，要求超时、重试与结构化校验，失败回退规则。

= Quality Attributes

*可追溯性*最高：4340 条正式记忆与演示集 15 条均至少一条有效证据，答案证据全部来自有效记忆，可回链率 100%。

*检索正确性*在 1515 个自动用例上衡量：混合策略 R\@1/3/5/10 为 0.334/0.510/0.578/0.666，MRR 0.588；回归下限建议 R\@5 ≥ 0.55、R\@10 ≥ 0.62。*状态判断正确性*：规则基线 16 组通过 9 组（56.25%，`CONFLICT` 2/2、`UPDATE` 3/4、`SUPERSEDE` 3/7、`RETAIN` 1/3），仅作回归基线。*可信性*：检索退化、冲突未消解、缺时间锚点或仅主体命中时均返回空答案，虚构答案为 0 条。*可复现性与性能*由确定性检索、哈希缓存与脚本用例保证：1515 用例三策略 27 秒、模型加载 5.3 秒；*可维护性*依靠 Protocol 边界与契约测试，85 项测试 1.1 秒全绿。

= Constraints

== 数据与范围约束

- *CON-01（数据范围）*　仅处理 LoCoMo 10 个样本（8 开发、2 测试）；结果不得推广到开放领域或生产环境。
- *CON-02（评测隔离）*　抽取只读 `conversation`，不得用 QA 三字段选择 turn 或指导抽取；QA 仅用于事后评测。
- *CON-03（证据与时间）*　每条 Memory 至少一条真实 `dia_id`；`effective_at` 不确定则 `null`；旧记忆保留。

== 技术与运行约束

- *CON-04（技术栈）*　Python 3.11/FastAPI/Pydantic v2；React 18/TS/Vite；契约 JSON Schema；数据存 JSON。
- *CON-05（离线与降级）*　无网络或无 Key 可运行：BM25 + `rules` 离线；语义或 LLM 不可用时回退规则。
- *CON-06（单机与单用户）*　单机单用户，不要求 GPU；无账号、权限、多租户、并发与高可用；嵌入模型约 90 MB。

== 项目与合规约束

- *CON-07（进度与范围）*　按 DDL 交付；未实现需求须标注，不得用模拟冒充真实输出，模拟链路须常驻提示。
- *CON-08（数据与密钥合规）*　只用公开数据；Key 仅存环境变量、`.env` 或 Keychain，不入仓库、日志或文档，错误不回显。
- *CON-09（交付边界）*　中期核心为 Web 原型、Memory、测试与评测；轻量的同槽位局部历史扩展属于 S 级演进，完整 Cue–Tag–Content Graph、开放式多跳智能体、生产部署、移动端与自动裁决不验收。

= Requirements Traceability

#[
  #set text(size: 8pt)
  #table(
    columns: (1.15fr, 1.5fr, 0.4fr),
    inset: 4pt,
    stroke: 0.45pt,
    [*需求*], [*验证*], [*状态*],
    [UR-01–08（UC-01–08）], [`demo/verify_demo.py` 8 项、Web 验收、`npm run build`；UC-05 仅到 `dia_id`／`quote`；UC-08 通过状态链遗漏专项用例验证], [UC-01–07 已实现，UC-05 部分；UC-08 未实现],
    [FR-MEM-01–05], [`test_extract.py`：完整性、schema、补抽不依赖 QA、状态合并与回环], [实现],
    [FR-RET-01–06、FR-STS-01–08], [`test_retrieval.py`、`test_embedding.py`、`test_dynamic_state.py`、`test_api.py`、`test_llm_relation.py`：排序、降级、关系、双锚点、不虚构、回退], [实现],
    [FR-API-01–04、FR-UI-01–05、FR-EVL-01–04], [`test_api.py`、`test_contract.py`、`demo/verify_demo.py` 8 项检查、`test_evaluation.py`、`npm run build`], [实现],
    [FR-API-05、FR-UI-06–07、FR-EVL-05], [无], [未实现],
    [FR-RET-07、FR-STS-09、FR-EVL-06], [状态链遗漏专项用例；与固定 Top-K 基线比较必需 Memory 召回、有效记忆判断、答案正确率、扩展量与模型调用次数], [S，未实现],
    [CON-01–09], [配置检查、抽取约束测试、密钥扫描与人工复核], [执行中],
  )
]

