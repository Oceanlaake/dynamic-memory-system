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
| POST | `/api/query` | `QueryRequest` | `QueryResponse` | ✅ 可用（B2 规则 + 可选 LLM） || POST | `/api/query` | `QueryRequest` | `QueryResponse` | ✅ 可用（B2 规则 + 可选 LLM） |

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
