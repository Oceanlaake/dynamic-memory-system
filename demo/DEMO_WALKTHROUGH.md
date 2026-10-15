# Jon 与 Gina：动态记忆系统完整演示解说

## 1. 演示目标

这个案例用于完整展示下面这条链路：

```text
LoCoMo 长对话
→ 抽取结构化 Memory
→ 根据问题检索 Candidate Memory
→ 判断 RETAIN / UPDATE / SUPERSEDE / CONFLICT
→ 选择 Effective Memory
→ 生成答案并展示原始证据
```

案例来自真实 LoCoMo 样本 `conv-30`，对话参与者是 Jon 和 Gina。为了让现场演示短而完整，只选择三个跨时间的 session，并保留其中 12 个与案例有关的 turn。

演示中的原始对话、session 时间和 `dia_id` 都来自 `data/raw/locomo10.json`。Memory 是人工抽取的；检索分数与关系判断是中期 Demo 的固定预期结果，不代表已经完成真实 embedding 或 LLM 调用。

## 2. 场景背景

Jon 原本是一名银行职员。失业后，他决定把自己从小热爱的舞蹈发展成一项事业，开设舞蹈工作室。几个月后，工作室即将正式开业；再过一个月，工作室遇到了资金压力，Jon 开始寻找投资人并修改商业计划。

这条经历具有明显的时间变化：

```text
2023-01-20：决定开舞蹈工作室
        ↓
2023-06-19：正式开业时间定为第二天
        ↓
2023-07-21：工作室经营承压，寻找投资
```

因此它比一个静态偏好更适合展示“动态记忆”。

## 3. 第一步：展示真实 LoCoMo 对话

### Session 1：目标形成

时间：2023-01-20 16:04

| Turn | 说话人 | 原始内容要点 |
| --- | --- | --- |
| `D1:2` | Jon | 昨天失去了银行工作，因此准备尝试创业。 |
| `D1:4` | Jon | 想开一家舞蹈工作室，因为自己热爱舞蹈。 |
| `D1:6` | Jon | 从小就喜欢舞蹈，希望把舞蹈的快乐带给别人。 |
| `D1:8` | Jon | 最喜欢的舞种是 contemporary dance。 |

解说词：

> 第一段对话里同时出现了事件、目标、原因和偏好。系统不应该把整段聊天存成一个大摘要，而应拆成可以独立检索和更新的事实单元。

### Session 15：目标进入开业阶段

时间：2023-06-19 10:04

| Turn | 说话人 | 原始内容要点 |
| --- | --- | --- |
| `D15:3` | Jon | 仍在为开舞蹈工作室而努力。 |
| `D15:5` | Jon | 正式开业就在明天。 |
| `D15:6` | Gina | 工作室看起来很棒，并祝贺 Jon 明天开业。 |
| `D15:13` | Jon | 再次确认明天是 grand opening。 |

解说词：

> 五个月后，“想开工作室”已经不再是最新阶段。新的对话给出了明确的开业日期，而且 Gina 的回应提供了交叉确认。

### Session 18：出现新的经营状态

时间：2023-07-21 17:44

| Turn | 说话人 | 原始内容要点 |
| --- | --- | --- |
| `D18:1` | Gina | 询问舞蹈工作室近况。 |
| `D18:2` | Jon | 工作室目前处境不稳；自己找了临时工作补贴开支，并在寻找投资人。 |
| `D18:8` | Jon | 在活动中见到了投资人并得到了建议。 |
| `D18:10` | Jon | 正在修改商业计划和投资人 pitch，并建设线上展示平台。 |

解说词：

> 到最新一次对话，工作室又出现了新的经营状态。这个信息仍应进入 Memory Store，但在回答“开业花了多久”时应被检索或有效记忆选择阶段过滤掉。

完整原文和本案例使用的原始 QA 可以在 `data/demo/selected_sessions.json` 中展示。

## 4. 第二步：抽取结构化 Memory

本 Demo 采用“一个可独立使用的事件、状态、目标或偏好对应一条 Memory”的粒度，而不是简单地一条 turn 对应一条 Memory。

### Memory 1：失业事件

```json
{
  "memory_id": "mem-conv30-001",
  "subject": "Jon",
  "type": "event",
  "attribute": "employment_event",
  "value": "lost_banking_job",
  "content": "Jon lost his job as a banker on 19 January 2023.",
  "status": "historical",
  "time": {
    "resolved_date": "2023-01-19",
    "basis": "session time minus one day"
  },
  "evidence": ["session_1/D1:2"]
}
```

### Memory 2：开工作室的初始目标

```json
{
  "memory_id": "mem-conv30-002",
  "subject": "Jon",
  "type": "goal",
  "attribute": "dance_studio.lifecycle_stage",
  "value": "planned",
  "content": "Jon plans to open a dance studio to share his lifelong passion for dance with others.",
  "status": "superseded",
  "evidence": ["session_1/D1:4", "session_1/D1:6"]
}
```

### Memory 3：稳定偏好

```json
{
  "memory_id": "mem-conv30-003",
  "subject": "Jon",
  "type": "preference",
  "attribute": "favorite_dance_style",
  "value": "contemporary",
  "content": "Jon's favorite dance style is contemporary dance.",
  "status": "current",
  "evidence": ["session_1/D1:8"]
}
```

### Memory 4：正式开业安排

```json
{
  "memory_id": "mem-conv30-004",
  "subject": "Jon",
  "type": "event",
  "attribute": "dance_studio.lifecycle_stage",
  "value": "opening_scheduled",
  "content": "Jon scheduled the official opening of his dance studio for 20 June 2023.",
  "status": "historical",
  "time": {
    "resolved_date": "2023-06-20",
    "basis": "tomorrow relative to session time"
  },
    "evidence": ["session_15/D15:3", "session_15/D15:5", "session_15/D15:6", "session_15/D15:13"]
}
```

### Memory 5：最新经营状态

```json
{
  "memory_id": "mem-conv30-005",
  "subject": "Jon",
  "type": "state",
  "attribute": "dance_studio.business_health",
  "value": "financially_tenuous",
  "content": "Jon's dance studio is on tenuous financial ground; he took a temporary job, is seeking investors, and is revising his business plan and investor pitch.",
  "status": "current",
  "evidence": ["session_18/D18:2", "session_18/D18:8", "session_18/D18:10"]
}
```

解说词：

> 一条 Memory 可以引用多个 turn。`content` 给人和 LLM 阅读，`subject / attribute / value` 用于检索和状态比较，`evidence` 用于回到原始对话。相对时间“明天”依据 session 时间解析成 2023-06-20，同时保留解析依据。

## 5. 第三步：用户提出问题

本案例直接使用 `conv-30` 的真实 LoCoMo QA，不另外编造问题：

```text
Question: How long did it take for Jon to open his studio?
Answer: six months
Evidence: [D1:2, D15:13]
```

页面传给后端的输入只包含数据集原有的问题内容：

```json
{
  "question": "How long did it take for Jon to open his studio?"
}
```

`sample_id` 可以来自页面当前选择的数据，不属于 question；`top_k` 是后端配置，也不属于 question。session 时间用于后端排序、解析“yesterday / tomorrow”等相对时间，同样不添加到用户问题里。

## 6. 第四步：检索 Candidate Memory

演示阶段先固定下面的检索结果。分数用于说明排序，不应宣称是已经运行的 embedding 结果。

| 排名 | Memory | 演示分数 | 入选原因 |
| --- | --- | ---: | --- |
| 1 | `mem-conv30-004` | 0.95 | 给出 grand opening 的结束时间点。 |
| 2 | `mem-conv30-002` | 0.89 | 给出 Jon 开工作室的初始目标。 |
| 3 | `mem-conv30-001` | 0.84 | 给出失业并开始创业的起始时间点。 |
| 4 | `mem-conv30-005` | 0.57 | 与工作室有关，但发生在开业之后，不用于计算答案。 |

`mem-conv30-003` 只描述 Jon 喜欢的舞种，与开业耗时无关，因此没有进入 Top-4。它仍保存在 Memory Store 中，并没有被删除。

解说词：

> Retrieval 只负责缩小范围，不直接决定最终答案。旧记忆和当前记忆可能同时被召回，因此下一步还要判断它们之间的时间和状态关系。

## 7. 第五步：动态状态判断

### 四种关系的演示定义

| 关系 | 定义 |
| --- | --- |
| `RETAIN` | 新信息与旧信息无冲突，旧 Memory 仍可独立成立。 |
| `UPDATE` | 新信息为同一实体或事件补充兼容的新属性，旧信息仍保留。 |
| `SUPERSEDE` | 新信息代表同一状态槽位的更新阶段；旧事实保留为历史，但不再作为当前值。 |
| `CONFLICT` | 两条信息在同一时间或无法确定先后时互不相容，需要保留冲突并等待进一步证据。 |

### 本案例的判断结果

```text
mem-conv30-001  Jon 失去银行工作
        └── RETAIN：历史事件仍成立，是创业背景

mem-conv30-002  工作室处于 planned 阶段
        ↓ SUPERSEDE
mem-conv30-004  已确定正式开业日期
        └── RETAIN：作为开业时间点参与答案计算

mem-conv30-005  开业后的经营状态
        └── UPDATE：补充后续状态，但不影响“开业花了多久”的答案

mem-conv30-003  Jon 喜欢 contemporary dance
        └── RETAIN：仍有效，但与本次问题无关
```

具体输出：

```json
[
  {
    "from": "mem-conv30-002",
    "to": "mem-conv30-004",
    "relation": "SUPERSEDE",
    "reason": "The studio lifecycle advanced from a plan to a scheduled opening."
  },
  {
    "from": "mem-conv30-004",
    "to": "mem-conv30-005",
    "relation": "UPDATE",
    "reason": "The later memory adds the studio's current financial condition and recovery actions without invalidating the opening event."
  }
]
```

本案例不产生 `CONFLICT`。`planned → opening_scheduled` 是按时间推进的状态变化；后续资金压力也不会改变已经发生的开业时间点。演示时不能为了覆盖标签而伪造冲突。

## 8. 第六步：选择 Effective Memory

针对问题“How long did it take for Jon to open his studio?”，选择：

```json
[
  {
    "memory_id": "mem-conv30-001",
    "role": "start_time"
  },
  {
    "memory_id": "mem-conv30-004",
    "role": "opening_time"
  }
]
```

不选择其他 Memory 的原因：

- `mem-conv30-002` 说明目标内容，但没有提供额外时间点；
- `mem-conv30-003` 是舞种偏好，与问题无关。
- `mem-conv30-005` 是开业后的经营状态，不影响开业耗时。

这里需要两条 Effective Memory，因为耗时问题必须同时具备起点和终点。系统不应该强制所有问题只能留下唯一一条 Memory。

## 9. 第七步：生成答案并展示证据

### 最终答案

> It took Jon six months to open his studio.

### 证据

| 结论 | Source | 原文 |
| --- | --- | --- |
| 起点：Jon 失业后开始尝试创业 | `session_1/D1:2` | “Lost my job as a banker yesterday, so I'm gonna take a shot at starting my own business.” |
| 终点：grand opening 在第二天举行 | `session_15/D15:13` | “Let's make some awesome memories tomorrow at the grand opening!” |

最终答案严格采用 LoCoMo 自带的标准答案 `six months`，并展示数据集指定的证据 `D1:2` 和 `D15:13`。本 Demo 不自行重新定义数据集的计时口径。

## 10. 前后端统一返回格式

演示接口建议返回：

```json
{
  "question": "How long did it take for Jon to open his studio?",
  "candidate_memories": [
    {"memory_id": "mem-conv30-004", "score": 0.95},
    {"memory_id": "mem-conv30-002", "score": 0.89},
    {"memory_id": "mem-conv30-001", "score": 0.84},
    {"memory_id": "mem-conv30-005", "score": 0.57}
  ],
  "relations": [
    {
      "from": "mem-conv30-002",
      "to": "mem-conv30-004",
      "relation": "SUPERSEDE"
    },
    {
      "from": "mem-conv30-004",
      "to": "mem-conv30-005",
      "relation": "UPDATE"
    }
  ],
  "effective_memories": ["mem-conv30-001", "mem-conv30-004"],
  "answer": "It took Jon six months to open his studio.",
  "evidence": [
    {"session_id": "session_1", "dia_id": "D1:2"},
    {"session_id": "session_15", "dia_id": "D15:13"}
  ]
}
```

## 11. Web Demo 页面流程

建议只做一个页面，按从左到右或从上到下的五个区域展示：

1. **Conversation**：选择 `conv-30`，展开三个 session，关键 turn 高亮；
2. **Extracted Memories**：显示 5 张 Memory 卡片，点击可定位原始 turn；
3. **Question & Retrieval**：显示 LoCoMo 原始 question、Top-4 和演示分数；
4. **Dynamic State**：用时间线展示 `lost job / planned → opening_scheduled`，并标记 `RETAIN / SUPERSEDE`；
5. **Answer & Evidence**：显示最终答案，点击证据跳回 Conversation。

内部字段如 embedding、完整 prompt 和模型原始输出默认折叠；用户主要看到 `content / time / relation / evidence`。

## 12. 现场解说顺序（约 4 分钟）

1. 展示 `conv-30` 中 Jon 和 Gina 跨 session 的真实对话；
2. 说明对话如何被拆成事件、目标、偏好和状态 Memory；
3. 展示数据集原始问题，而不是另行输入时间点；
4. 展示候选 Memory，并说明为什么开业后的经营状态不能回答“花了多久”；
5. 展示 `planned → opening_scheduled` 的状态变化；
6. 选择包含起点和终点的两条 Effective Memory；
7. 输出 LoCoMo 标准答案 `six months`，并回链到 `D1:2`、`D15:13`。

## 13. 演示通过标准

- Question、Answer、Evidence 与 LoCoMo `qa` 字段完全一致；
- Question 输入中不添加 `as_of`、`top_k` 等系统参数；
- 能生成 3 个 session、12 个 turn 和 5 条 Memory；
- 每条 Memory 至少有一个真实的 `session_id + dia_id` 证据；
- 能从候选 Memory 中选出计算答案所需的起点和终点；
- 最终答案使用数据集标准答案，证据使用数据集指定 turn；
- 明确区分原始数据、人工抽取结果和演示期模拟结果。





运行数据准备脚本：

```bash
python3 demo/prepare_locomo_demo.py
```

脚本只负责复制真实 turn、生成 Memory JSON 和校验证据引用；检索、关系判断与答案生成目前由本文档规定预期输入输出，后续再替换为真实后端调用。
