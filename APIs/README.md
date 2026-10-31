# APIs 接口清单

本目录是前后端与模块之间**唯一权威**的接口定义。代码里的 Pydantic 模型（`backend/schemas.py`）与前端类型（`frontend/src/types/api.ts`）都必须与这里的 JSON Schema 一致，由 `tests/test_contract.py` 强制校验。

## 文件

| 文件 | 内容 | 负责人 | 变更需通知 |
|---|---|---|---|
| `memory_schema.json` | 结构化 Memory 的字段、必填项、枚举 | A / Schema | A、B、C |
| `memory_sechema.md` | Memory 字段的中文说明与示例 | A / Schema | A、B、C |
| `retrieval.schema.json` | **B1 检索契约**：`RetrievalRequest` / `CandidateMemory` / `RetrievalResult` | **B / Retrieval** | B2、C |
| `query.schema.json` | **全链路契约**：`QueryRequest` / `QueryResponse` / `Relation` / `EffectiveMemory` / `ErrorResponse` | B / Retrieval + C | B2、C |

`retrieval.schema.json` 与 `query.schema.json` 通过相对 `$ref` 引用 `memory_schema.json` 和彼此，**不重复定义 Memory 字段**。A 改字段时 B、C 会立刻在契约层暴露出来。

## HTTP 接口

| 方法 | 路径 | 请求 | 响应 | 状态 |
|---|---|---|---|---|
| GET | `/api/health` | — | `{status: "ok"}` | ✅ 可用 |
| GET | `/api/samples` | — | `SampleSummary[]` | ✅ 可用 |
| GET | `/api/samples/{sample_id}/memories` | — | `Memory[]` | ✅ 可用 |
| POST | `/api/retrieve` | `RetrievalRequest` | `RetrievalResult` | ✅ 可用（默认 hybrid） |
| POST | `/api/query` | `QueryRequest` | `QueryResponse` | ✅ 可用（B2 规则 + 可选 LLM + 同槽位补检） |

### 为什么 `/api/retrieve` 必须单独存在

它是 B1 的独立交付面：B2 未完成、C 未接入时，检索仍可单独运行和评测（Recall@K）。`/api/query` 的 `candidate_memories` 与 `/api/retrieve` 的 `candidates` **完全同构**，避免两套格式分叉。

## 关键约定

1. **`question` 只放问题本身**。`sample_id`、`top_k` 是系统参数，不塞进问题文本。
2. **`score` 范围 0~1，越大越相关**。语义随 `strategy` 变化：`bm25` 为本次查询内相对得分（最高分 = 1.0），`embedding` 为 cosine 相似度。**不能跨查询比较**。
3. **`candidates[].memory` 是完整 Memory 对象**。C 不需要再请求一次 `/memories`，B2 直接拿到 `time` 与 `evidence`。
4. **`degraded=true` 表示检索退化**（无命中、空索引、策略回退）。C 必须显示提示，不能当成正常空结果。
5. **`answer` 可以是 `null`**。证据不足或冲突未消解时返回 `null`，不编造答案。
6. **错误统一为 `ErrorResponse`**，`error.code` 机器可读：`SAMPLE_NOT_FOUND`、`INVALID_REQUEST`。
7. **`top_k` 默认 5，上限 50**。
8. **检索分数不表示新旧或真假**。B2 只用时间与状态槽位判断动态关系，不能用更高 `score` 覆盖较低分 Memory。

## Bonus：查询驱动的同槽位补检

`POST /api/query` 支持两个可选参数：

| 参数 | 默认值 | 作用 |
|---|---|---|
| `expand_slots` | `false` | 开启单轮同槽位历史补检；关闭时仍使用相同状态解析器，仅不扩大候选集合 |
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
- 动态问题从与问题内容相关的候选提取 `(subject, attribute)`；键忽略大小写及首尾空格。事实类问题不扩展，空属性和仅匹配主体名的候选不作为种子。
- 对当前状态/变化问题，优先选问题词与属性名重合最多的槽位，再按初始排名打破平局，每个相关主体选择一个主要槽位。持续时间问题允许保留多个非集合型种子，但不推断它们之间的生命周期映射。
- plan/goal/venture/project/possession 等集合型属性不作为可替代状态链扩展；显式带 status/stage/state/lifecycle 的细分属性除外。规则是属性层面的启发式分类，不能替代语义理解。
- 只扫描请求样本的 Memory；不推断属性别名或跨属性生命周期关系。
- `candidate_source` 为 `initial` 或 `slot_expansion`。初始候选保留原排序和分数；补检候选追加在后，`score=0` 只是占位，Web 显示“未计算相关度”。扩展集合可超过初始 `top_k`。
- 响应 `expansion` 记录类型、初始数量、补检 ID、槽位、截断状态和停止原因。
- `expansion.stop_reason` 为 `disabled`、`not_dynamic`、`not_comparable`、`no_seed`、`no_new_memory`、`expanded` 或 `candidate_limit`。`not_comparable` 表示只找到集合型属性，保留原始候选交给解析器；它不同于缺少相关种子而拒答。
- `evidence_status` 独立记录 `sufficient`、`insufficient`、`missing_anchor`、`missing_transition`、`conflict`、`unorderable`；兼容消费者也可遇到默认 `not_checked`。
- 无新增历史仍可充分作答；动态问题没有相关槽位种子，或补检达到上限且存在未加入的节点时，保守返回 `answer=null`。
- 状态变化问题返回有可靠顺序的同槽位历史；持续时间检查起止标记和可比较日期，不能仅因存在两个日期就作答。
- 充分性只表示通过当前规则检查，不是对语义相关性或真实答案正确性的保证。任意历史时点查询、未识别的问法、无种子和跨属性锚点均未被本版解决。

集合型属性中的不同 value 不自动生成 CONFLICT、SUPERSEDE 或 UPDATE；保留原文，关系不确定时不强行建边。
明确的对立值、同一对象的状态对立或直接否定仍进入冲突/时间解析，包含被其他集合事实隔开的非相邻节点。
配置了语义 Judge 时仍可对不确定关系作进一步判断；缺省离线规则不会把“没有关系边”解释为已经证明两事实兼容。
状态回答只由主要槽位内的相关冲突阻止，其他槽位关系仍可在 Web 中查看。

实现计划和评测边界见 [后期计划](../docs/bonus-implementation-plan.md)。

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

`DMS_STATE_RESOLVER=rules`（默认）完全离线。设置为 `hybrid` 后，确定性规则仍优先；无序矛盾、
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

**数据来源**：后端默认读取 A 抽取产出的 `outputs/memories/`（10 个样本、4336 条 Memory）；
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
