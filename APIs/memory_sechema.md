## 1. memory结构

## **注意B后续添加的字段不要重名** 

A部分总体要求

Input:
LoCoMo conversation JSON

Output:
Structured Memory JSON

| 字段 | 类型 | 必填 | 中文含义 | 备注 |
|---|---|---:|---|---|
| `memory_id` | `string` | 是 | Memory 唯一标识 | 建议全局唯一，如 `mem-conv30-001` |
| `subject` | `string` | 是 | 这条记忆主要描述的对象/人物 | 例如 `Jon` |
| `type` | `string(enum)` | 是 | Memory 类型 | 初版可限定 `state / event / goal / preference / requirement` |
| `content` | `string` | 是 | 这条 Memory 的自然语言描述 | 给人和 LLM 直接阅读 |
| `attribute` | `string \| null` | 否 | Memory 描述的状态维度/属性 | 如 `dance_studio_status` |
| `value` | `string \| null` | 否 | 该属性对应的具体值 | 如 `searching_for_location` |
| `time` | `object` | 是 | Memory 对应的时间信息 | 至少保留 session 信息 |
| `time.session_id` | `string` | 是 | 来源 session | 如 `session_3` |
| `time.date_time` | `string \| null` | 否 | 该 session 的时间 | 可以先保留原始字符串 |
| `evidence` | `array<object>` | 是 | 支撑该 Memory 的原始对话证据 | 至少 1 条 |
| `evidence[].session_id` | `string` | 是 | 证据所在 session | 用于追溯 |
| `evidence[].dia_id` | `string` | 是 | 原始对话 turn ID | 如 `D3:1` |
| `evidence[].quote` | `string \| null` | 否 | 原始对话文本 | Demo 阶段建议保留 |
| `confidence` | `number \| null` | 否 | Memory 抽取置信度 | 建议范围 0~1 |
||||||
注意：如果type是event的话，attribute和value可以为空，其他建议让llm提供这两个内容，便于后续理解

示例：

```
{
  "sample_id": "conv-30",
  "memories": [
    {
      "memory_id": "mem-conv30-001",

      "subject": "Jon",
      "type": "goal",

      "attribute": "dance_studio_status",
      "value": "planning_to_open",

      "content": "Jon wants to open a dance studio and share his passion for dance with others.",

      "time": {
        "session_id": "session_1",
        "date_time": "20 January, 2023"
      },

      "evidence": [
        {
          "session_id": "session_1",
          "dia_id": "D1:4",
          "quote": "I'm starting a dance studio because I'm passionate about dancing."
        }
      ],

      "confidence": 0.98
    },

    {
      "memory_id": "mem-conv30-002",

      "subject": "Jon",
      "type": "state",

      "attribute": "dance_studio_status",
      "value": "searching_for_location",

      "content": "Jon is searching for a suitable location for his dance studio.",

      "time": {
        "session_id": "session_3",
        "date_time": "1 February, 2023"
      },

      "evidence": [
        {
          "session_id": "session_3",
          "dia_id": "D3:1",
          "quote": "I'm still searching for a place to open my dance studio."
        }
      ],

      "confidence": 0.99
    }
  ]
}
```


locomo conversation示例
```
{
  "sample_id": "conv-30",
  "conversation": {
    "speaker_a": "Jon",
    "speaker_b": "Gina",

    "session_1_date_time": "4:04 pm on 20 January, 2023",
    "session_1": [
      {
        "speaker": "Jon",
        "dia_id": "D1:1",
        "text": "..."
      }
    ],

    "session_2_date_time": "2:32 pm on 29 January, 2023",
    "session_2": [
      {
        "speaker": "Gina",
        "dia_id": "D2:1",
        "text": "..."
      }
    ]
  }
}
```

