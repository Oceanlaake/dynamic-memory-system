# LoCoMo → Memory 最小演示

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
