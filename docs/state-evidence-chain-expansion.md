# 查询驱动的状态证据链补全

## 1. 背景与问题

当前系统先使用 BM25、Embedding 或 Hybrid Retriever，从一个样本的 Memory Store 中返回固定 Top-K 候选，再在候选内部判断动态状态关系并选择 Effective Memory。

这一流程能够判断已经召回的 Memory 之间的关系，但固定 Top-K 只按相关性截取候选，不能保证同一状态演化过程中的历史 Memory 全部进入候选集。当关键的前序状态、后续更新或时间锚点被截断时，状态解析规则即使判断正确，也只能得到一条残缺的状态证据链。

因此，下一阶段拟研究：以初始候选及其关系为种子，返回样本的全量 Memory 补充同状态槽位的历史，然后重新构建关系链并判断证据是否足以回答问题。

本文使用“状态证据链”，而不使用“思维链”。前者指由 Memory 节点和显式 Relation 边组成、可以展示和验证的系统数据；后者容易被理解为大模型不可见的内部推理过程。

## 2. 当前系统已经实现的能力

### 2.1 Memory 结构

每条 Memory 已包含以下与状态比较有关的字段：

- `memory_id`：Memory 的唯一标识。
- `subject`：事实所属主体。
- `attribute`：可比较的状态维度。
- `value`：该状态维度的取值。
- `time`：对话时间与事实生效时间。
- `evidence`：原始 Session、Turn 和引用文本。

系统在抽取后对 attribute 词表进行归一，尽量减少同一状态维度使用不同名称的问题。

### 2.2 候选内部的关系构建

动态状态解析器会把 Top-K 候选按照 `(subject, attribute)` 分组，在组内按时间排序，并为相邻 Memory 输出关系：

- `RETAIN`：后续信息确认原状态仍成立。
- `UPDATE`：后续信息补充兼容内容。
- `SUPERSEDE`：新状态取代旧状态。
- `CONFLICT`：信息不兼容且无法可靠判断先后。

每条 Relation 包含 `from`、`to`、`relation` 和 `reason`。因此，当前输出已经可以解释为一个局部关系图：Memory 是节点，Relation 是有向边。

### 2.3 当前实现的限制

当前系统尚未实现一个可主动搜索和补全的图结构：

- Relation 只在本次 Top-K 候选内部生成。
- 没有持久化的状态槽位索引或邻接表。
- 没有路径搜索、连通性分析和通用的证据链完整性判断。
- 前端 Relation Timeline 主要负责展示 Relation，并不执行图搜索。
- Memory Schema 中没有独立的 `state_slot` 或 `entity` 字段。

因此，当前能力应描述为“构建候选 Memory 之间的局部关系边”，不能描述为“已经建立完整的 Memory Graph”。

## 3. 核心思路

该方案包含两个核心步骤。

### 3.1 构建初始状态证据链

Retriever 首先返回 Top-K 候选，现有状态解析器随后构建候选之间的 Relation，形成初始局部关系图：

```text
用户问题
   ↓
Hybrid Top-K
   ↓
候选 Memory 节点
   ↓
关系解析
   ↓
初始状态证据链
```

初始链的作用是提供状态槽位种子，而不是直接假定候选已经完整。

### 3.2 对已识别槽位执行历史闭包扩展

系统从与问题相关的候选节点中提取 `(subject, attribute)`，回到该样本的全量 Memory，补充属于相同槽位的历史节点：

```text
Top-K 中的状态种子
   ↓ 提取 subject + attribute
扫描该样本的全量 Memory
   ↓
补充同槽位历史节点
   ↓
重新构建 Relation
   ↓
扩展后的状态证据链
```

这里的第二阶段不再使用原问题重复执行相同的相似度 Top-K，而是利用 Memory 已有的结构化字段进行筛选。第一版可以直接扫描单个样本的全部 Memory：

```python
slots = {
    (memory.subject, memory.attribute)
    for memory in initial_candidates
    if memory.attribute is not None
}

expanded_memories = [
    memory
    for memory in all_sample_memories
    if (memory.subject, memory.attribute) in slots
]
```

LoCoMo 单个样本的 Memory 数量有限，直接扫描即可验证方案有效性。若后续需要优化性能，可在加载数据时建立内存索引：

```python
slot_index[(sample_id, subject, attribute)] = [memory_1, memory_2, ...]
```

该索引只是性能优化，不是方案成立的前提。

## 4. 为什么不先判断“是否存在遗漏”

只观察残缺候选，系统通常无法知道候选集之外是否还有相关 Memory。例如，Top-K 中只有“Jon 正式开设工作室”，系统无法仅凭该节点判断 Memory Store 中是否还保存了计划、准备或经营阶段。

因此，第一版不尝试预测某个未知节点是否存在，而采用确定性的触发方式：

> 当问题涉及动态状态，且初始候选中出现可比较的 `subject + attribute` 时，对相关状态槽位自动执行一次有界的历史扩展。

同槽位扩展完成后，再判断现有证据是否足以回答。这样可以避免“先知道缺什么，才能搜索缺什么”的循环问题。

本阶段暂不处理 Top-K 中完全没有相关种子的情况。该问题需要额外的查询解析、高召回检索或主体识别路线，不属于第一版状态证据链补全的范围。

## 5. 状态证据链的完整性判断

“完整”不表示收集人物的全部历史，而表示当前问题所需的证据角色已经齐全。系统应先识别问题类型，再检查相应条件。

### 5.1 当前状态问题

例如：“Jon 的工作室现在是什么状态？”

最低要求：

- 存在与问题相关的状态槽位。
- 槽位内 Memory 可以按事实时间或可靠的替代时间排序。
- 存在未被后续 `SUPERSEDE` 的状态节点。
- 最新状态不存在未解决的 `CONFLICT`。

满足条件后，选择链末端仍然有效的节点作为 `current_state`。

### 5.2 状态变化问题

例如：“Jon 的工作室状态发生了什么变化？”

最低要求：

- 至少存在两个同槽位节点。
- 节点之间存在可靠顺序。
- 至少形成一条 `RETAIN`、`UPDATE` 或 `SUPERSEDE` 边。

如果只有一个节点，系统可以回答当前事实，但不能据此说明发生了变化。

### 5.3 持续时间问题

例如：“Jon 花了多长时间开设工作室？”

最低要求：

- 存在 `start_time` 节点。
- 存在 `opening_time` 或 `end_time` 节点。
- 两个节点都有可比较的事实时间。

当前状态解析器已经对持续时间问题执行双锚点检查，但检查对象仍局限于 Top-K 候选。后续应先扩展相关历史，再重新寻找起点和终点。

### 5.4 冲突与停止条件

出现以下任一情况时停止作答：

- 扩展后仍缺少问题所需的关键角色。
- 关键节点无法排序。
- 关键状态之间存在未解决的 `CONFLICT`。
- 扩展没有加入新节点。
- 达到配置的最大扩展轮数或候选数量。

停止时返回 `answer=null`，并记录缺失角色或冲突原因。

## 6. 最小实现方案

第一版可直接复用当前 Memory Schema 和状态解析器，不引入完整 Graph 框架。

1. Retriever 返回初始 Top-K。
2. 现有解析器生成初始 Relation。
3. 从与问题相关的候选中提取 `(subject, attribute)`。
4. 从当前样本的全量 Memory 中补充相同槽位节点。
5. 将扩展节点与初始候选去重合并，并标记节点来源。
6. 重新执行时间排序和关系解析。
7. 根据问题类型检查证据角色。
8. 证据充分则生成答案，否则返回证据不足。

建议增加以下内部数据，但第一版不必修改持久化 Memory Schema：

```text
candidate_source: initial | slot_expansion
expanded_slot: subject + attribute
stop_reason: sufficient | no_new_memory | missing_anchor | conflict
```

## 7. 后续扩展

相同 `(subject, attribute)` 只能处理已经完成属性归一的状态链。如果生命周期的不同阶段使用了不同属性，例如：

```text
business_plan
opening_date
business_status
```

第一版无法自动认定它们都属于 `studio_lifecycle`。后续可以研究：

- 在 Memory Schema 中增加 `entity` 和 `state_slot`。
- 建立受控的属性别名与生命周期映射。
- 使用 LLM 对无法规则归一的属性进行结构化分类。
- 在显式状态槽位上建立图索引和多轮证据补全。

上述能力属于第二阶段，不应在中期展示中表述为已经实现。

## 8. 评测方案

评测应在同一批问题上比较以下方案：

1. 固定 Top-K 基线：使用当前 Hybrid Retriever 和状态解析器。
2. Top-K 加同槽位扩展：初始检索后补充相同 `(subject, attribute)` 的历史。
3. 后续扩展方案：加入跨属性 `state_slot` 和证据不足驱动的定向检索。

第一阶段至少报告：

- 答案所需 Memory 召回率。
- Effective Memory 判断准确率。
- 最终答案正确率或 F1。
- 每个问题增加的候选数量。
- 状态解析或 LLM 调用次数。
- 因证据不足而拒答的数量。

专项测试应优先覆盖“Top-K 已找到至少一个正确种子，但遗漏同槽位历史”的案例，因为这是第一版方案明确要解决的问题。

## 9. 中期展示表述

可在中期展示中概括为：

> 当前系统能够在 Top-K 候选内部构建 Memory 关系，但固定 Top-K 可能截断同一状态链。下一阶段将把候选关系图作为种子，返回样本的全量 Memory 补充同主体、同属性的历史，再重新构建关系并按照问题所需的证据角色判断是否能够作答。

需要明确区分：

- 已实现：结构化 Memory、Hybrid 检索、候选内部关系判断、Effective Memory 选择与证据展示。
- 计划实现：同槽位历史扩展、扩展来源记录、状态证据链完整性判断与对照评测。
