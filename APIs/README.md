# APIs 接口清单

本目录是前后端与模块之间**唯一权威**的接口定义。代码里的 Pydantic 模型（`backend/schemas.py`）与前端类型（`frontend/src/types/api.ts`）都必须与这里的 JSON Schema 一致，由 `tests/test_contract.py` 强制校验。

## 文件

| 文件 | 内容 | 负责人 | 变更需通知 |
|---|---|---|---|
| `memory_schema.json` | 结构化 Memory 的字段、必填项、枚举 | A / Schema | A、B、C |
| `memory_sechema.md` | Memory 字段的中文说明与示例 | A / Schema | A、B、C |
| `retrieval.schema.json` | **B1 检索契约**：`RetrievalRequest` / `CandidateMemory` / `RetrievalResult` | **B / Retrieval** | B2、C |
| `query.schema.json` | **全链路契约**：`QueryRequest` / `QueryResponse` / `Relation` / `EffectiveMemory` / `ErrorResponse` | B / Retrieval + C | B2、C |
| `graph.schema.json` | **Graph Memory 契约**：节点、边、多跳路径、查询 trace 与完整导出 | B / Graph | B2、C |

`retrieval.schema.json` 与 `query.schema.json` 通过相对 `$ref` 引用 `memory_schema.json` 和彼此，**不重复定义 Memory 字段**。A 改字段时 B、C 会立刻在契约层暴露出来。

## HTTP 接口

| 方法 | 路径 | 请求 | 响应 | 状态 |
|---|---|---|---|---|
| GET | `/api/health` | — | `{status: "ok"}` | ✅ 可用 |
| GET | `/api/samples` | — | `SampleSummary[]` | ✅ 可用 |
| GET | `/api/samples/{sample_id}/memories` | — | `Memory[]` | ✅ 可用 |
| POST | `/api/retrieve` | `RetrievalRequest` | `RetrievalResult` | ✅ 可用（默认 hybrid） |
| POST | `/api/query` | `QueryRequest` | `QueryResponse` | ✅ 可用（规则分析 + 可选补检 + LLM 作答） |

### 为什么 `/api/retrieve` 必须单独存在

它是 B1 的独立交付面：B2 未完成、C 未接入时，检索仍可单独运行和评测（Recall@K）。`/api/query` 的 `candidate_memories` 与 `/api/retrieve` 的 `candidates` **完全同构**，避免两套格式分叉。

## 关键约定

1. **`question` 只放问题本身**。`sample_id`、`top_k` 是系统参数，不塞进问题文本。
2. **`score` 范围 0~1，越大越相关**。初始候选的语义随 `strategy` 变化：`bm25` 为本次查询内相对得分（最高分 = 1.0），`embedding` 为 cosine 相似度；`graph_expansion` 为 Graph 路径与问题相关度的联合分数。**不能跨来源或跨查询比较**。
3. **`candidates[].memory` 是完整 Memory 对象**。C 不需要再请求一次 `/memories`，B2 直接拿到 `time` 与 `evidence`。
4. **`degraded=true` 表示检索退化**（无命中、空索引、策略回退）。C 必须显示提示，不能当成正常空结果。
5. **`answer` 可以是 `null`**。证据不足、模型拒答或生成失败时返回 `null`；用 `generation.status` 区分原因，不回退模板。
6. **错误统一为 `ErrorResponse`**，`error.code` 机器可读：`SAMPLE_NOT_FOUND`、`INVALID_REQUEST`。
7. **`top_k` 默认 5，上限 50**。
8. **检索分数不表示新旧或真假**。B2 只用时间与状态槽位判断动态关系，不能用更高 `score` 覆盖较低分 Memory。

## Bonus：查询驱动的证据补检（v3）

`POST /api/query` 支持两个可选参数：

| 参数 | 默认值 | 作用 |
|---|---|---|
| `expand_slots` | `false` | 开启查询驱动补检；沿用字段名兼容现有调用，现同时支持同槽位历史与原文邻近证据 |
| `max_expansion_memories` | `50` | 最多新增的记忆数量，范围 1–200；不包含原 Top-K 候选 |

```json
{
  "sample_id": "conv-30",
  "question": "What is Jon's studio status now?",
  "top_k": 3,
  "expand_slots": true,
  "max_expansion_memories": 50
}
```

Web 默认开启补检，可关闭后重新提交相同问题进行对照。接口默认关闭，便于兼容已有调用。
`/api/retrieve` 仍只返回原始 Top-K，不执行补检。

- 问题类型使用英文规则识别：显式的 now/current/status/still/latest、偏好或居住地问题归为 `current_state`，变化问题为 `change`，严格匹配 `How long did it take for … to …` 的问题为 `duration`。普通 `What is/does` 不再自动视为状态问题，其他问法归为 `factual`。
- 问题类型不再决定“允不允许补检”。事实题也进入证据检查；只有主体名匹配而缺少问题主题线索时不使用该候选作种子。
- 对当前状态/变化问题，优先选问题词与属性名重合最多的槽位，再按初始排名打破平局，每个相关主体选择一个主要槽位。持续时间问题允许保留多个非集合型种子，但不推断它们之间的生命周期映射。
- 事实题以及只有集合型/无属性候选的情况使用 `query_evidence` 策略：从相关初始候选取得事实槽位及原始 turn 邻域，查找同槽位、同 turn 或相邻 1 个 turn 的相关 Memory。集合属性可以作检索线索，空属性不被合并为一个共享槽位。
- 邻域候选需要问题主题重合与主体范围检查，按 BM25 及来源关联排序；最多新增 `min(初始唯一候选数, max_expansion_memories)` 条，因此普通事实检索通常不超过原候选数的两倍。
- plan/goal/venture/project/possession/activity 等集合属性仍不被当作可替代状态维度。显式可比较的动态槽位使用 `state_history` 历史闭包，继续受新增总上限保护。
- 只扫描请求样本的 Memory；新增原文邻域连接可以跨属性，但没有推断跨属性生命周期映射。
- `candidate_source` 为 `initial`、`slot_expansion` 或 `context_expansion`；`expansion_reason` 解释 `same_slot`、`same_turn` 或 `adjacent_turn`。初始排序和分数保留，追加候选 `score=0` 为占位，Web 不将其显示为相关度。
- `expansion` 除已有字段外增加 `expansion_policy`、`eligible_count` 和 `budget_limited`。`truncated` 专门表示未完成的强制状态历史闭包；`budget_limited` 表示相关事实按预算选取，不因此自动拒答。
- 停止原因继续兼容原有枚举，`not_dynamic` 和 `not_comparable` 仅保留用于历史结果；新策略不再因这些原因跳过相关事实补检。正常结果为 `disabled`、`no_seed`、`no_new_memory`、`expanded` 或 `candidate_limit`。
- `evidence_status` 独立记录 `sufficient`、`insufficient`、`missing_anchor`、`missing_transition`、`conflict`、`unorderable`；兼容消费者也可遇到默认 `not_checked`。
- 无新增证据仍可充分作答；没有相关证据种子，或强制状态历史被上限截断时，保守返回 `answer=null`。普通事实证据预算与状态历史截断不混用。
- 状态变化问题返回有可靠顺序的同槽位历史；持续时间检查起止标记和可比较日期，不能仅因存在两个日期就作答。
- 充分性只表示通过当前规则检查，不是对语义相关性或真实答案正确性的保证。任意历史时点查询、未识别的问法、无种子和跨属性锚点均未被本版解决。

集合型属性、普通事实题中的不同 value 不自动生成 CONFLICT、SUPERSEDE 或 UPDATE；保留原文，关系不确定时不强行建边。
明确的对立值、同一对象的状态对立或直接否定仍进入冲突/时间解析，包含被其他集合事实隔开的非相邻节点。
配置了语义 Judge 时仍可对不确定关系作进一步判断；缺省离线规则不会把“没有关系边”解释为已经证明两事实兼容。
规则分析保留槽位内冲突提示，其他槽位关系仍可在 Web 中查看。最终作答采用下述统一生成流程。

## 统一答案生成与用量

`/api/query` 与正式 QA/补检评测共用 `backend/qa.py`：检索/补检 → 规则分析 → 证据包 → LLM 答案与引用。
规则分析不生成模板答案。全部有界候选及来源引文交给模型，规则选中/历史/冲突作为提示；
不因一条记忆未被规则选中就删除它。无候选、补检无相关种子、强制状态历史截断时跳过生成。
其他规则充分性提示由模型结合证据判断，`evidence_status` 不等于最终模型结论。

- `effective_memories`：规则选中的记忆，不等于模型实际使用的证据。
- `answer_memory_ids`：模型声明的支持记忆；非空答案必须引用输入中的有效 ID。此校验不证明答案语义正确。
- `evidence`：由实际引用的 Memory 汇集、去重的来源，不代表模型逐句完成了引文蕴含验证。
- `generation`：provider、请求/返回模型、耗时、上下文哈希、输出上限及真实 API usage。
- `generation.status`：`answered` / `refused` / `error` / `skipped`。调用/格式/引用错误独立记录 `error_code`，没有模板回退。
- 用量含输入、输出、缓存输入、非缓存输入、推理 Token；未报告为 `null`。缓存是输入子集，推理是输出子集，不能重复相加。

答案模型用 `DMS_ANSWER_PROVIDER`、`DMS_ANSWER_MODEL`、`DMS_ANSWER_MAX_TOKENS` 配置，并设置对应 API Key。
`DMS_ANSWER_PROVIDER=glm` 支持智谱标准 API，密钥为 `GLM_API_KEY`（兼容 `ZAI_API_KEY`），默认模型为 `glm-4.7-flash`；可用 `GLM_BASE_URL` 覆盖标准地址。
检索和补检本身不调用生成 LLM。完整运行与对照说明见 [统一 LLM 作答与评测](../docs/unified-llm-qa.md)。

当前成绩见 [340 题正式结果](../docs/large-scale-results-2026-11-05.md)，机制见 [证据补检 v3](../docs/evidence-expansion-v3.md)。[11 月 1 日历史结果](../docs/final-submission-notes.md) 单独保留，不能与当前数字混用。

## Bonus：Graph Memory / 多跳关系建模

`POST /api/query` 还支持独立的 Graph Memory 扩展：

| 参数 | 默认值 | 作用 |
|---|---:|---|
| `graph_expand` | `false` | 从原 Top-K 种子执行图遍历 |
| `graph_max_hops` | `3` | 最大遍历跳数，范围 1–4 |
| `max_graph_memories` | `5` | 最多新增 Memory，范围 1–50 |

图包含 Memory、人物、状态槽位、取值、Session 和 Turn 节点，并显式保存 `NEXT_STATE`、
`SUPPORTED_BY`、`NEXT_TURN` 等边。新增候选使用 `candidate_source=graph_expansion`，`score`
为问题相关度加权后的 Graph 路径分数，同时返回 `graph_hops` 和 `graph_path`；
`QueryResponse.graph` 提供可视化所需的紧凑子图与完整多跳路径。
Graph 与原有 `expand_slots` 可分别开启，默认都不改变固定 Top-K 行为。完整设计和导出命令见
[Graph Memory Bonus](../docs/graph-memory.md)。

## Memory 的时间字段（B1 输出，B2 消费）

`candidates[].memory.time` 保留全部现有字段，并新增可选的 `effective_at`：

| 字段 | 类型 | 含义 |
|---|---|---|
| `session_id` | `string` | 必填。来源 session |
| `date_time` | `string \| null` | **对话 / Session 发生时间**，保留数据集原始字符串 |
| `effective_at` | `string \| null` | **事件发生或状态生效时间**，`YYYY-MM-DD`；无法确定时为 `null` |

```json
"time": {
  "session_id": "session_15",
  "date_time": "2023-06-19T10:04:00",
  "effective_at": "2023-06-20"
}
```

约定：

- B1 只负责**原样透传**，不修改、不推断、不排序。检索打分不使用时间字段（时间推理属于 B2）。
- `effective_at` 缺失或为 `null` 时，B2 回退到 `date_time` 或 session 顺序。
- 该字段在 `memory_schema.json` 中已定义，`retrieval.schema.json` 与 `query.schema.json` 通过 `$ref` 自动继承。

## B2 关系解析策略

`DMS_STATE_RESOLVER=rules`（默认）表示关系分析完全离线；最终答案仍调用答案模型。设置为 `hybrid` 后，确定性规则仍优先；无序矛盾、
同主题不同属性，以及只有对话/Session 顺序而没有明确事件时间的不同值，会调用 LLM。LLM 请求
失败、拒答或返回无效结构时自动使用保守规则结果。
混合模式还需设置 `DMS_LLM_PROVIDER`、`DMS_LLM_MODEL` 与对应的 API Key。DeepSeek 使用
`DEEPSEEK_API_KEY`，OpenAI 使用 `OPENAI_API_KEY`；两者都不会改变本页定义的请求或响应格式。
macOS 上若未设置 `DEEPSEEK_API_KEY`，B2 还会读取项目专用的
`dynamic-memory-system.deepseek-api-key` Keychain 条目。

## 检索策略

`strategy` 字段告诉调用方本次实际用的策略，取值 `bm25` / `embedding` / `hybrid`。用环境变量切换，无需改代码：

| `DMS_RETRIEVER` | 行为 |
|---|---|
| `auto`（默认） | 优先 hybrid；sentence-transformers 不可用时自动退回 bm25 |
| `bm25` | 纯词法，零依赖，离线可用 |
| `embedding` | 纯语义（`all-MiniLM-L6-v2`，cosine） |
| `hybrid` | BM25 0.4 + embedding 0.6 加权融合 |

对照实验与选型依据见 `process/decisions/2026-10-17-检索策略选型.md`。

**数据来源**：后端默认读取 A 抽取产出的 `outputs/memories/`（10 个样本、4340 条 Memory）；
该目录不存在时退回 `data/memories/`（测试用的最小样本）。可用 `DMS_MEMORY_DIR` 覆盖。

**离线**：模型已缓存时完全离线加载；未缓存时才联网下载。设 `HF_HUB_OFFLINE=1` 可强制离线。

## 本地校验

```bash
python -m pytest tests/test_contract.py -q
```

## 在线文档

```bash
uvicorn backend.main:app --reload
# http://127.0.0.1:8000/docs
```

`/docs` 与 `/openapi.json` 由 FastAPI 从同一套 Pydantic 模型生成，是"可执行"的接口文档。
