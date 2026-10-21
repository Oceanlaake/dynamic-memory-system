系统流程是：
**LoCoMo 长对话 → 抽取结构化 Memory → 根据问题检索相关 Memory → 判断 RETAIN / UPDATE / SUPERSEDE / CONFLICT → 选当前有效 Memory → 生成答案并展示证据。**

```
一个 LoCoMo sample
│
├── conversation
│   ├── session_1
│   │   ├── D1:1
│   │   ├── D1:2
│   │   └── ...
│   ├── session_2
│   └── ...
│
├── qa
│   ├── question
│   ├── answer
│   └── evidence: [D2:3, D5:7, ...]
│
├── event_summary
├── session_summary
└── 其他辅助标注
```



分工：

```
A. 数据与 Memory
LoCoMo 数据 → Structured Memory
如何定义这个struct memory是一个比较关键的事情，也是整个项目里面最重要的事情，因为后续基本都是调用llm
核心问题是定义一条 Memory 到底长什么样，包括：
memory_id
content
entity / event
attribute
value
timestamp
source session / turn
...

struct memory json格式需要A和B进行同步的

B. Retrieval + Dynamic State
问题 →（检索） Candidate Memory →（选出） Effective Memory
这个任务不要求我们训练AI，我么要做的是进行调用，以及做好提示词工程
主要工作是：
- 调用现有 embedding / LLM；
- 完成 Memory Retrieval；
- 设计 RETAIN / UPDATE / SUPERSEDE / CONFLICT 的判断规则；
- 做 Prompt Engineering；
- 规定结构化输出格式。

C. Web Demo
把整条链路展示出来，需要定义好后端与A，B功能的接口，至于自己的后端和前端的接口，可以不用对接，自行调用AI

初步计划是这周结束前先把ABC完成，然后下周开始做DEF
第一次的pre都没有进行，但是最坏情况就是下周四直接两场pre一起也是有可能的，所以最好还是提前将pre要用的材料和同学准备好

（注意，srs理论上来说应该是要在做项目之前写的,但是我觉得这样舒服一点）
D. SRS文档撰写，SRS老师在上课的时候提到过一些要点，我后续会进行整理
E. test
F. PPT / Presentation



```

具体ABC分工

| 人   | 主任务                  | 本周必须产出                                      |
| ---- | ----------------------- | ------------------------------------------------- |
| 胡海洋 | A：Memory Schema 负责人 | 定 JSON Schema、字段含义、Memory 粒度             |
| 路巨聪 | A：数据/抽取负责人      | 跑通 LoCoMo 解析，产出一批真实 Memory JSON        |
| 石子吟 | B：Retrieval 负责人     | Query → Top-K Candidate Memory                    |
| 叶首状 | B：Dynamic State 负责人 | UPDATE/SUPERSEDE/CONFLICT 判断 + Effective Memory |
| 廖若言 | C：Web / Integration    | 页面、API 约定、把 A/B 输出接进 Demo              |



前端 React + TypeScript，后端 Python + FastAPI，所有模块之间统一使用 JSON 作为数据格式，A/B 的算法与 LLM 调用全部放后端，前端只负责通过 API 调用和展示





我建议你们至少把下面这些定义清楚。

- **Memory Schema**：字段有哪些、哪些必填、字段类型是什么。比如 `memory_id / content / entity / attribute / value / timestamp / source_session / source_turn`。你们现在已经意识到 A 和 B 必须同步这个。   同步颗粒度
- **Memory 粒度**：一个事件/状态抽一条
- **Memory 的语义定义**：`entity / event / attribute / value` 到底怎么理解，哪些字段是给检索用，哪些是给状态判断用。
- **时间表示**：绝对时间、session 时间、相对时间怎么处理；没有明确时间时怎么存。
- **source 的可追溯规则**：一条 Memory 对应一个 turn，还是可以对应多个 turn；前端点击证据时怎么回到原始对话。

然后 A 和 B 之间还要统一：

- **Retrieval 输入输出**：B 读到的到底是完整 Memory JSON，还是只读其中部分字段。
- **Top-K**：先暂定一个值，比如 5，不用一开始就调优。
- **状态关系集合**：你们至少要把 `RETAIN / UPDATE / SUPERSEDE / CONFLICT` 的定义写成一句话，尤其 UPDATE 和 SUPERSEDE 怎么区分。你们文档里 B 已经明确要做这几个判断。   同步颗粒度
- **Effective Memory 判定**：关系判断之后，到底怎么选最终有效 Memory；允许多个 effective memory 还是只能一个。
- **异常情况**：检索不到、证据冲突、LLM 输出格式错了怎么办。

B 和 C 之间要统一：

- **最终接口返回格式**，这个特别重要。建议直接固定成：

```
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
}{
  "query": "",
  "candidate_memories": [],
  "relations": [],
  "effective_memories": [],
  "answer": "",
  "evidence": []
}
```

- **Web 到底展示哪些东西**：别一开始什么都展示。至少展示 Query、Candidate Memory、Relation、Effective Memory、Answer、Source。
- **哪些字段给用户看，哪些只是内部字段**。
- **Demo 的固定流程**：用户是先选 conversation 再提问，还是直接输入 question；是否允许切换 sample。



还有一类是全组必须统一的，不属于某个模块：

- **中期最小完成标准**：不是“每块做完”，而是完整链路能跑通。
- **Demo Case**：提前选 3～5 个例子，至少覆盖 UPDATE、SUPERSEDE、CONFLICT。
- **临时方案和正式方案要区分**：比如当前先用 LLM 做 relation classification，可以明确写成中期实现，不要假装这是最终最优方案。
- **代码目录和接口负责人**：谁有权改 Schema，谁有权改 B 的输出格式，不能大家同时随便改。
