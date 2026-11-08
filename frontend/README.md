# 前端 Web Demo（C）

React + TypeScript + Vite + Ant Design 单页应用，负责展示完整链路：

```
问题 → 候选记忆（B1） → 关系与有效记忆（B2） → 答案与证据
```

前端只通过 HTTP API 消费数据，不包含任何算法逻辑。

## 启动

先在仓库根目录启动后端：

```bash
pip install -r backend/requirements.txt

# 默认读取 data/memories（仓库内的少量测试数据）
uvicorn backend.main:app --reload

# 读取 A2 产出的真实提取数据（outputs/memories，10 个样本）
DMS_MEMORY_DIR=outputs/memories uvicorn backend.main:app --reload
```

再启动前端：

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`（见 `vite.config.ts`）。

生产构建检查：

```bash
npm run build
```

## 数据模式

当前页面只调用真实 `POST /api/query`，不再自动降级到前端模拟。查询设置可分别开启
“查询驱动证据补检”和“Graph Memory 多跳检索”；Graph 结果显示访问节点数、新增 Memory
以及每条新增候选的节点/边路径。

## 与 B2 的对接

`src/api/mock.ts` 是历史阶段保留的临时适配器，当前 `App.tsx` 不再导入或执行它。

- 规则只覆盖可机械判断的情况：同 subject + 同 attribute 的新旧值 → `SUPERSEDE` / `CONFLICT`；内容完全一致 → `RETAIN`；
- 不生成 `UPDATE`，也不伪造冲突或 LLM 答案；
- B2 已实现 `/api/query`（规则模式，可用 `DMS_STATE_RESOLVER=hybrid` 开启 LLM），默认「自动」模式现在走真实链路；
- mock 只用于追溯中期实现，不得作为当前系统或正式截图。

## 代码结构

| 文件 | 职责 |
|---|---|
| `src/types/api.ts` | 与 `APIs/*.schema.json` 一一对应的类型（含 B2 的 `time.effective_at`） |
| `src/api/client.ts` | fetch 封装、`ErrorResponse` 解析、501 识别、中文错误提示 |
| `src/api/mock.ts` | B2 的前端模拟适配器 |
| `src/App.tsx` | 页面状态与数据流 |
| `src/components/` | 五个展示区域：样本选择、提问、候选记忆、关系时间线、答案与证据 |
| `src/components/GraphMemoryPanel.tsx` | Graph 节点类型、边和多跳路径展示 |

契约变更时只需要改 `src/types/api.ts` 和 `src/api/`，页面组件不受影响。

## 已知限制

- 证据回链目前只展示 Memory 内嵌的 `session_id / dia_id / quote`。仓库还没有「读取原始对话 turn」的 API；若要做到点击证据跳回完整对话，需要后端补 `GET /api/samples/{sample_id}/turns`。
- 样本与记忆数据完全来自后端 `/api/samples`，不硬编码 `conv-30`；A 的真实数据上线后重启后端即可看到。
- 关系图属于 bonus，本 Demo 按文档要求使用时间线 + 关系列表。
