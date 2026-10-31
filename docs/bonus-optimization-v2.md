# 第二轮优化：收紧补检范围与避免伪冲突

日期：2026-10-31。

## 结果

在与第一轮相同的 conv-30、280 条 Memory、77 道 QA 上复测：
本轮消除了第一版补检引入的 6 道额外拒答，Hybrid 的答案 F1 恢复到固定 Top-3 基线。
目前没有证据表明新补检方案在这批真实问题上提高了答案 F1，不能将“消除负收益”描述为“超越基线”。

| Hybrid 方案 | 证据集合召回率 | 平均候选数 | 答案 F1 | 拒答数 |
|---|---:|---:|---:|---:|
| 第一轮 Top-3 基线 | 54.76% | 3.00 | 0.130 | 3 |
| 第一版 Top-3 + 补检 | 55.09% | 4.17 | 0.119 | 9 |
| 本轮 Top-3 基线（共享新解析器） | 54.76% | 3.00 | 0.130 | 3 |
| 本轮 Top-3 + 补检 | 54.76% | 3.14 | 0.130 | 3 |
| 本轮 Top-10（共享新解析器） | 63.79% | 9.96 | 0.129 | 2 |

Hybrid 平均补检量从每题约 1.17 条降到 0.14 条。收紧策略也撤回了部分第一版带来的召回，
因此证据召回率回到基线；没有试图用大量无关候选换取表面上的召回增长。

| BM25 方案 | 证据集合召回率 | 平均候选数 | 答案 F1 | 拒答数 |
|---|---:|---:|---:|---:|
| 第一轮 Top-3 基线 | 52.38% | 3.00 | 0.142 | 2 |
| 第一版 Top-3 + 补检 | 53.03% | 3.82 | 0.131 | 8 |
| 本轮 Top-3 基线（共享新解析器） | 52.38% | 3.00 | 0.141 | 2 |
| 本轮 Top-3 + 补检 | 53.03% | 3.25 | 0.141 | 2 |
| 本轮 Top-10（共享新解析器） | 61.41% | 9.94 | 0.129 | 2 |

BM25 相对本轮基线仍保留了约 0.65 个百分点的证据召回增长，但没有转化成答案 F1 增长。
共享解析器的改动也改变了两道 BM25 基线问题的回答措辞，一题 F1 上升、一题下降；
本轮基线 F1 比第一轮低约 0.0011。因此分别列出前后基线，不能把所有前后差异归功于补检。

## 修改内容

### 查询与槽位选择

- 去除“所有 What is/does 都是当前状态问题”的规则；保留显式时间/状态词、偏好、居住地、状态变化和受支持的持续时间问题。
- 当前状态和变化问题优先匹配属性名，按初始候选排名打破平局，每个相关主体选择一个主要槽位。
- 例如“favorite dance style”优先选 favorite_dance_style，而不是同时扩展 favorite_activity。
- 当前状态解析也使用同一槽位选择逻辑；其他槽位中的旁支冲突不会自动否定目标状态，但关系仍保留供展示。
- 持续时间问题保留多个相关的非集合型种子；没有增加跨属性生命周期映射。

### 区分状态维度与集合型事实

- plan、goal、venture、project、possession、hobby、offering 等宽泛属性可能存放多个独立事实，不作为可替代状态链扩展。
- 显式包含 status/stage/state/lifecycle 的细分维度仍可扩展。这是通用属性规则，不包含题目 ID、人物名或标准答案。
- 只有集合型相关候选时返回 `not_comparable`，保留原始候选交给解析器，不把它误报为“没有证据”。
- 同集合中不同 value 不能证明存在冲突或替代，也不能证明兼容；离线规则不强行生成关系边，保留原始证据。
- 配置语义 Judge 时仍可判断这些不确定关系。

### 保留真实冲突与证据边界

- open/closed、active/inactive 等直接对立值仍然比较时间，无可靠先后时仍拒答。
- 支持同对象上下文中的对立值，如 library_open / library_closed，及直接否定，如 opening_library / not_opening_library。
- 集合型属性还检查上述明确对立值的非相邻节点，避免一个无关中间事实遮蔽冲突。
- library_open / cafe_closed 指向不同对象，不因此判为冲突。
- 两条 Memory 的 value 都为空，不再仅因 null == null 就判 RETAIN；还需内容相同才可确认重复。
- 普通未知属性、未被规则识别的否定或语义矛盾仍然存在局限，本轮没有宣称实现通用冲突消解。

## 逐题检查

第一轮两道直接损失答案信息的问题已恢复：

- “What is Jon offering to the dancers at his dance studio?”：由 null 恢复为一对一指导与训练，F1 从 0 恢复到 0.400。
- “What is Jon working on opening?”：由 null 恢复为开舞蹈工作室，F1 从 0 恢复到 0.444。

77 道题中，规则识别的动态问题从 14 道降为 5 道（4 道 current_state、1 道 duration）。
BM25 与 Hybrid 都只有 2 道实际补入新节点，另 3 道没有新历史，其余 72 道不扩展。
这批原始 QA 没有显式 change 问题，因此它并不足以评估完整的状态链能力。

新增专项回归在另一个人物/领域中确认：Top-K 仅命中旧的图书馆状态时，补检仍能找回较新的关闭状态并改变回答。
同槽位真实冲突、集合属性内的真实对立/否定、非相邻矛盾、无时间锚点、候选上限、样本隔离等均保留测试。
这些是机制回归，不能混入上表充当真实 QA 的效果提升。

## 验证与复现

- 后端：128 项测试通过。
- Demo：8 项检查通过。
- 前端：TypeScript 检查与生产构建通过；保留原有的大包体积提示。
- JSON Schema、Python 与 TypeScript 均增加 `not_comparable` 停止原因。
- 本轮没有修改 Memory JSON、QA 标准答案或评分规则，没有使用其他对话调参，也没有调用付费 LLM。

```bash
.venv/bin/python -m pytest -q
.venv/bin/python demo/verify_demo.py
HF_HOME="$PWD/data/cache/huggingface" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -m evaluation.quick_check \
  --output-dir evaluation/results/bonus_quick_check_v2
```

原始结果：[第一轮](../evaluation/results/bonus_quick_check/)；
本轮结果：[BM25](../evaluation/results/bonus_quick_check_v2/bm25.json)、[Hybrid](../evaluation/results/bonus_quick_check_v2/hybrid.json)、[用例来源](../evaluation/results/bonus_quick_check_v2/cases.json)。
第一轮文件完整保留，未覆盖。

## 下一步

先在开发数据整理有人工检查的真实状态变化题及有效 Memory 标注，明确哪些属性是可比较状态、哪些是可累积事实。
之后再判断是否需要受控的槽位细分/别名映射或语义关系辅助，最后冻结参数，运行独立测试集。
本轮结论是“移除已知负收益并保留补检能力”，而不是“Bonus 已取得显著准确率提升”。
