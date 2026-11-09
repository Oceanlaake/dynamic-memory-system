# LoCoMo 动态记忆系统 Demo

## Web Demo（推荐现场使用）

前后端已经通过 `/api` 接通。首次运行先安装依赖：

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm ci && cd ..
```

一条命令启动后端和前端：

```bash
cp .env.example .env
# 填写答案生成模型对应的 API Key。
./demo/start_demo.sh --final   # 最终版：6 个冻结样本 + Hybrid 检索，可开启 Graph Memory
./demo/start_demo.sh           # 中期演示数据：conv-30 的 15 条 Memory
```

启用 DeepSeek 辅助判断模糊的 B2 Memory 关系：

```bash
./demo/start_demo.sh --deepseek
```

DeepSeek 密钥从 `DEEPSEEK_API_KEY` 环境变量、被 Git 忽略的 `.env` 或项目专用 macOS
Keychain 条目读取；不要把密钥提交到仓库。该模式只增强关系分类，不改变 B1 检索和最终答案生成。

当前最终答案均由 `DMS_ANSWER_PROVIDER / DMS_ANSWER_MODEL` 配置的 LLM 生成。
`--deepseek` 是额外的关系判断开关；默认 rules 不调用关系 LLM，但仍调用答案模型。
接口失败、无效引用或证据不足会明确记录状态，不回退到模板答案。

打开 <http://127.0.0.1:5173>。页面里的“场景 1～4”会填入预设问题；现场主流程使用
`conv-30` 的 15 条 Memory（5 条主链路记忆 + 10 条来自正式抽取结果的真实干扰记忆），
Top-K=5 能稳定展示检索筛选、`SUPERSEDE / UPDATE`、Effective Memory、答案和证据回链。

如正式抽取结果发生变化，可重新生成演示数据：

```bash
.venv/bin/python demo/prepare_demo_store.py
```

要验证所有 10 个正式抽取样本（4,340 条 Memory）也已接通，可切换数据目录：

```bash
DMS_MEMORY_DIR=outputs/memories ./demo/start_demo.sh
```

正式数据模式用于浏览全部样本和测试真实召回效果。当前 BM25 对主讲的时长问题不能在 Top-K
内同时召回两个时间锚点，因此现场主案例默认使用可追溯的精选数据；这不会修改或伪装正式数据。

## 多场景验收

```bash
.venv/bin/python demo/verify_demo.py --stub-llm
```

脚本覆盖：完整时长链路、稳定偏好、工作室生命周期、无匹配不编造、未知样本 404、空问题 422，
以及健康检查和 Demo 数据检查。
`--stub-llm` 明确使用测试替身，只验证服务连接、引用与状态；不用于真实 F1 或 Token 表。
去掉此选项会调用真实已配置模型，集成检查只验证输出与证据结构，不保证固定措辞。
完整质量与消耗对照见 [v1 + v2 合并实验结果](../docs/results/results-v1-v2.md)。

## 数据准备演示

完整的动态记忆演示流程、页面设计和现场解说词见 [`DEMO_WALKTHROUGH.md`](DEMO_WALKTHROUGH.md)。

这个 demo 只回答一个问题：**一小段真实长期对话，如何变成可追溯的 Memory JSON？**

## 演示范围

- 数据源：`data/raw/locomo10.json`
- 样本：`conv-30`（Jon 与 Gina）
- 会话：`session_1`、`session_15`、`session_18`
- 展示：从三个 session 中挑出 12 个有记忆价值的 turn
- 产物：人工整理的 5 条 Memory

这里故意不接 LLM、不做向量库，也不声称已经实现自动抽取。脚本的职责只有两个：

1. 从原始 LoCoMo 文件复制指定的真实 turn；
2. 校验每条 Memory 引用的 `dia_id` 确实存在，并把原文证据带进最终 JSON。

## 运行

在仓库根目录执行：

```bash
python3 demo/prepare_locomo_demo.py
```

预期输出：

```text
Built demo from 3 sessions: 12 selected turns -> 5 memories
```

生成的两个文件：

- `data/demo/selected_sessions.json`：包含选中的真实 turn 和原始 QA；
- `data/demo/memories.json`：适合随后展示“系统最终存了什么”。

## 建议的现场讲解顺序

先打开 `selected_sessions.json`，按 session 时间顺序读几个关键句，例如：

1. `D1:2`、`D1:4`、`D1:6`：Jon 失业后决定开舞蹈工作室；
2. `D15:3`、`D15:5`：几个月后，工作室定于次日正式开业；
3. `D18:2`、`D18:8`、`D18:10`：开业后经营承压，Jon 开始找投资并调整商业计划。

再打开 `memories.json`，说明 Memory 不是整段对话摘要，而是可复用、可更新、可回溯的事实单元。每条记录保留：

- `subject`：记忆属于谁；
- `type`：目标、偏好、事件或要求；
- `content`：归一化后的自然语言事实；
- `status`：当前、进行中或已完成；
- `confidence`：抽取置信度；
- `time`：有明确时间时才记录；
- `evidence`：原 session、`dia_id` 和原文；
- `extraction`：本 demo 明确标记为人工抽取并已复核。

## 一条 Memory 的形态

```json
{
  "memory_id": "mem-conv30-003",
  "subject": "Jon",
  "type": "preference",
  "content": "Jon's favorite dance style is contemporary dance.",
  "status": "current",
  "confidence": 0.99,
  "evidence": [
    {
      "session_id": "session_1",
      "dia_id": "D1:8",
      "quote": "Cool, Gina! I love all dances, but contemporary is my top pick..."
    }
  ],
  "extraction": {
    "method": "manual",
    "reviewed": true
  }
}
```

演示时可以把整条数据流概括成：

```text
LoCoMo 原始样本
  → 选定同一人物对跨时间的 3 个 session
  → 标出 12 个有记忆价值的 turn
  → 人工归一化、去重、合并证据
  → 5 条带证据回链的 Memory JSON
```

后续若接入 LLM，只需要替换“人工归一化”这一步；输入、Memory schema 和证据校验仍然可以保留。
