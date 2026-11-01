# 最终测试与组员交接清单

更新：2026-10-31。读者：测试同学、统筹同学、报告与 PPT 同学。

## 先看结论

先完成课程要求的三项指标与两个对照，再做 Bonus 消融。可以增加“相较中期的 Recall@K”条目，但必须同数据、同题目、同 K 比较。
后期没有修改原始 Hybrid 排序算法；主要变化发生在 Top-K 之后，因此优先验证“补检后的证据集合召回”，不能把超过 K 条的结果冒充 Recall@K 提升。

测试同学负责实际运行、保存逐题结果和初步分析；不要只提交截图或挑选提升的数字。
本文件是执行计划，不表示列出的正式测试已经完成。代码变化说明见 [中期后代码变化](post-midterm-changes.md)。

## 1. 项目要求与必须交付的证据

依据 [项目要求大纲](项目要求大纲.pdf) 第 9–11 页：

| 要求 | 最终测试必须提供什么 |
|---|---|
| 课程选定 6 段 LoCoMo：4 开发 + 2 独立测试 | 明确 sample_id 清单、用途、版本和历史使用情况；正式结果单列测试集 |
| 结构化 Memory：内容、时间、来源、JSON、Web | 指定样本均可加载，契约校验，证据能回链，JSON 交付；至少一组 Web 全流程截图 |
| 动态检索、关系判断、有效 Memory、回答 | 从完整历史自动检索的逐题记录；不能把正确 Memory 手工塞给最终系统 |
| 问题回答 F1 | 正式 QA 与统一评分口径下的 F1、题数、拒答数和逐题预测 |
| 证据记忆检索 Recall@K | 同一标注下的原始 Top-K 结果，建议 K=1/3/5/10，同时说明证据映射和排除题数 |
| 动态状态更新判断准确率 | 课程动态题上的关系预测、正确标签、分标签统计；有效 Memory 判断单独报告 |
| 对照方法 Full Text / Vector RAG | 全文回答、不作状态判断的纯向量 RAG 与最终系统的同题对照 |
| 实验结果与对照分析 | 正式汇总表、原始 JSON/CSV、配置、成功与失败例、局限 |

MRR、耗时、候选数量、补检召回率是补充指标，不替代课程三项指标。
大纲写有展示材料；按目前分工制作 PPT/PDF，不额外安排现场演示流程。课程最新通知优先于旧大纲。

## 2. 分工与交接顺序

| 角色 | 具体任务 | 交付给谁 |
|---|---|---|
| 你：统筹与代码负责人 | 确认课程数据、冻结并同步代码/Memory；补齐必要评测入口；处理阻塞性错误；最终检查与打包 | 全组 |
| 测试同学：1 人 | 执行 T00–T05，保存日志与结果；整理一张主结果表、Bonus 表和案例；发现问题先记录 | 报告同学、PPT B、你 |
| 设计与需求报告同学：1 人 | 阅读变化说明，更新需求实现状态、系统设计、接口与限制；整合测试同学提供的实验章节材料 | 你、PPT A |
| PPT A：1 人 | 背景/需求、架构、中期到末期变化、Bonus 流程图与界面 | PPT B、你 |
| PPT B：1 人 | 测试方法、最终图表、收益与失败案例、局限；与 A 统一风格和数字 | 你 |

流程：统一版本与数据 → 测试；报告/PPT 的结构可同时写 → 测试交表后填入最终数字 → 统一核对、导出 PDF、打包。
正文与 PPT 不各自重算指标；统一采用测试同学提供且经核对的表。

## 3. T00：开始前必须确认的事项

优先级 P0，统筹与测试同学共同完成。

- [ ] 写明课程指定的 4 段开发与 2 段测试 sample_id，不凭仓库现有全部 10 段自行代替。
- [ ] 领取课程统一筛选的动态题、关系与有效 Memory 标注；没有拿到时先标“待领取”，不要用自建 16 题顶替。
- [ ] 核对历史暴露：旧 SRS/检索记录采用过“8 开发 + conv-49、conv-50 测试”，与课程 4+2 口径不同；conv-49 还进入过已使用的关系样例。按课程指定名单评测，并如实说明历史使用，不能把它们声称为从未看过的数据。
- [ ] 当前优化仍有未提交/未跟踪文件。先形成包含新增模块、文档、测试入口的统一提交并同步，再让组员拉取。不要只发旧 main 的提交号。
- [ ] 单独共享 Memory JSON、原始数据与课程标注，核对文件哈希；代码版本相同不代表本地数据相同。
- [ ] 当前 `outputs/memories` 实际为 10 段、4,340 条 Memory；旧决策记录写过 4,336 条。先确认版本差异，不能默认中期与现在的数据完全相同。
- [ ] 冻结配置：Retriever、Embedding 型号/版本、融合权重/阈值、Resolver、LLM 型号、Top-K、扩展上限、答案生成方式、F1 口径。
- [ ] 在开发集确认命令可运行后再执行正式测试；看到正式测试分数后不继续调权重/规则再冒充首次独立结果。

发现真实阻塞性缺陷可修，但要记录修复与重新评测，不能删除失败题或重命名测试集来隐藏调试过程。

## 4. 必做测试

### T01：运行、数据、契约与 Web 验收

优先级 P0。目的：证明交付物可运行、可追溯。

执行已有检查：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python demo/verify_demo.py
cd frontend
npm run build
```

现有开发机记录为 128 项后端测试、8 项 Demo 检查、前端构建通过；组员需在冻结版本复跑并保存自己的结果。
Demo 只验证小样本；契约测试主要使用 `data/memories`，它们不等于正式 Memory 全量验证。
另对课程选定 6 段的全部 Memory 验证可加载、字段符合 schema、source session/turn 存在，记录空属性/时间缺失和证据覆盖情况。

Web 至少核对：样本选择；补检开/关；候选及来源；关系理由；有效 Memory；答案与证据；无相关证据时不编造；接口参数越界被拒绝。
保存 3 组图即可：普通正确回答、补检找回历史的成功例、冲突/缺失锚点的失败例。
截图必须对应真实配置与数据，不用人工演示 Memory 证明正式性能。

启动正式数据页面时，可用：

```bash
DMS_MEMORY_DIR=outputs/memories DMS_RETRIEVER=hybrid DMS_STATE_RESOLVER=rules ./demo/start_demo.sh
```

按测试配置替换为指定数据目录。需要本地 Node/npm、依赖和向量模型；不要把开发机专用的绝对路径复制给其他同学。

### T02：严格的 Recall@K 与中期对比

优先级 P0。主表报告正式测试集的原始 R@1/3/5/10。中期对比另列。

1. 使用相同原始对话、Memory JSON、QA 清单、证据标注、类别排除规则及 K。
2. 基线代码可参照提交 `9aff5a8`；经核对其 backend/frontend/evaluation 与中期材料提交 `888dc32` 相同。末期使用最终冻结提交。
3. 建议分目录或独立 checkout 运行，保存两份结果；不要覆盖中期存档。
4. 原始 B1 未改变时，同条件结果应基本一致。不得通过增加 K、缩小题集、换标注分母或更多候选来宣称排序提升。

历史参考值来自 [中期真实数据结果](../evaluation/results/real_summary.json)，Hybrid、1,515 题：

| 原始指标 | 历史值 |
|---|---:|
| R@1 | 0.3344 |
| R@3 | 0.5101 |
| R@5 | 0.5776 |
| R@10 | 0.6660 |

这是历史全量 10 段的参考，不是课程 2 段独立测试集成绩。不能拿当前 conv-30 的 77 题或专项 16 题直接与其比较。
如果无法恢复历史同版本 Memory/题单，只写“历史参考值”，不写严格提升百分比。

现有可用命令：

```bash
.venv/bin/python -m evaluation.recall_at_k \
  --cases evaluation/final/final-test-cases.json \
  --memory-dir outputs/memories \
  --retrievers bm25 embedding hybrid --ks 1,3,5,10 \
  --json-out evaluation/results/final/recall.json
```

`evaluation/final/final-test-cases.json` 是需要测试同学按课程数据整理的输入，本仓库尚未提供该文件；`final/` 结果目录也不是已有最终成绩。
题单至少含 `sample_id`、`question`、`required_memory_ids`；没有官方 Memory ID 时按官方证据映射并记录方法，人工检查歧义，不把代理标注说成官方金标。

`build_cases.py` 会跳过完全没有 Memory 映射的题。正式结果不能静默删除这些题：另外报告抽取覆盖率与排除清单；
只有可映射题的 Recall 应注明“条件召回”。有原始证据轮次标注时，优先在轮次级对全部适用题计算召回，未覆盖证据记为未命中。
端到端 F1 仍须保留这些题，不能因为抽取失败就从 QA 分母移除。

计算口径：每题 `|TopK ∩ Gold| / |Gold|` 后取题目平均，同时报告分对话结果。
若 Gold 使用原始轮次，则同样在轮次级比较，不能混用 Memory 级分母。

### T03：动态关系与有效 Memory 判断

优先级 P0，使用课程动态题及正式标注。

- **端到端状态评测**：系统从该样本完整 Memory 自动检索；对标注关系逐一判断，未召回/未输出的必需关系算缺失，不只评已预测的正确边。
- **关系准确率**：按课程规则优先；若没有额外说明，记录正确关系数/标注关系数，区分 RETAIN、UPDATE、SUPERSEDE、CONFLICT，保留无预测数量。
- 校验有向关系的 from/to，不能只检查两端 ID 的无向集合。
- **有效 Memory**：单独统计与金标集合的一致性或课程规定指标，说明允许的等价证据/多起止节点；不能把它叫作关系准确率。
- **关系模块辅助测试**：给定正确两条 Memory，测试 Resolver 自身，报告为“relation-only”，不得顶替自动检索后的成绩。

已有 16 对关系回归可运行：

```bash
.venv/bin/python -m evaluation.state_accuracy \
  --resolver rules --json-out evaluation/results/final/relation-regression.json
```

该入口接受 `first_memory`、`second_memory`、`expected_relation` 格式，且当前匹配节点对时不校验方向，只适合辅助复测。
官方动态题的端到端评测与方向校验需要适配，当前不能声称已有完整自动入口。
中期 PPT 中 rules 9/16、DeepSeek 16/16 是小型关系模块实验，不是完整 QA 的准确率；LLM 复测需记录实际模型、调用失败与回退。

### T04：课程要求的答案 F1 和 Full Text / Vector RAG 对照

优先级 P0。下列四种系统尽量采用同一答案生成器、模型/参数和输出预算，区别只在送入的上下文及状态处理。

| 方法 | 输入上下文 | 是否作状态判断 |
|---|---|---|
| Full Text | 该问题对应对话的完整原始文本 | 否 |
| Vector RAG | 纯 Embedding 检索的 Top-K Memory | 否 |
| 固定 Top-K 状态系统 | Hybrid Top-K 后选择有效记忆 | 是 |
| 最终 Bonus 系统 | 相同 Hybrid Top-K + 槽位补检后选择有效记忆 | 是 |

纯 Embedding 的检索 Recall 表不是 Vector RAG 的 QA F1；Full Text 也不是“把所有 Memory 送入现有 Resolver”。
Full Text 若超出上下文窗口，记录处理策略和截断；不能截断后继续称完整全文而不说明。
如果最终系统保留模板答案、对照使用 LLM，则可以报告真实端到端表现，但必须说明生成方式不同，不能把差异全部归因于状态判断。

**对照入口**：`evaluation/final/qa_compare.py` 提供 Full Text / Vector RAG / 状态系统统一 QA 对照，四种方法共用同一 LLM 答案生成器（`backend/answer.py`），仅输入上下文不同。

```bash
.venv/bin/python -m evaluation.final.qa_compare \
  --cases evaluation/final/final-test-cases.json \
  --raw data/raw/locomo10.json --memory-dir outputs/memories \
  --top-k 5 --resolver rules --json-out evaluation/results/final/qa_compare.json
```

答案生成默认读取 `DMS_LLM_PROVIDER` / `DMS_LLM_MODEL`，也可用 `--provider/--model` 覆盖；需要对应 API Key。仍需测试同学按课程数据整理 `evaluation/final/final-test-cases.json`（该目录与官方题单尚未提供），并在课程官方 F1 脚本到位后优先接入。

要求：同一正式题单；统一官方 F1 脚本（若有）；没有官方脚本则提前固定并写清本地分词规则；包含可回答但系统拒答的题，不能只统计有答案题。
对抗/不可回答题若单列，写明题数与规则；拒答正确率单列，不把 null 匹配算入普通可回答题的 F1。
优先只跑正式必要的模型配置，不增加大量权重扫描。

### T05：Bonus 必要消融——补检究竟带来什么

优先级 P1，但若报告/PPT 申报自适应检索 Bonus，则本项必须有结果。

固定相同 Retriever、同一套当前 Resolver、模型和数据：

| 方案 | 建议配置 |
|---|---|
| 固定 Top-K | K=5，关闭扩展 |
| 更大 K | K=10，关闭扩展 |
| Top-K + 扩展 | K=5，开启扩展，最多新增 50 条 |

主表使用正式测试集，并单列课程动态题；开发专项题仅作辅助。需要重现前期实验时另跑 K=3，不在正式测试后挑 K。
每组至少保存：初始 Recall@K、最终候选集合证据召回、答案 F1、有效 Memory 结果、平均/最大候选数、拒答数、扩展触发数与截断数。
输出三种方向的逐题变化：改善、不变、退化；没有触发补检的题也留在总体分母里。

```bash
.venv/bin/python -m evaluation.slot_expansion \
  --cases evaluation/final/final-test-cases.json --memory-dir outputs/memories \
  --retriever hybrid --resolver rules --top-k 5 --larger-k 10 \
  --max-expansion-memories 50 \
  --json-out evaluation/results/final/bonus-ablation.json
```

注意输入字段：答案评分需 `expected_answer`，只提供 `answer` 不会自动计算 F1；有效记忆需 `expected_effective_memory_ids`；关系需 `expected_relations`。
缺标注时结果为 null，不能当作已完成该指标。该入口的 `resolver_calls` 不是 LLM 调用数。
输入案例若包含不可回答题，最终汇总应按 T04 口径将其与可回答题 F1 分开；现有入口需要外部汇总或适配，不能直接复制混合分数。

**两类召回必须分开命名**：

```text
原始 Recall@K = 初始 K 条候选覆盖的必需证据 / 全部必需证据
Expanded Evidence Recall = 补检后全部候选覆盖的必需证据 / 全部必需证据
```

原始排名保留不变时，补检后再机械截回前 K 条不会改善原始 Recall@K。
若要写“召回提升”，应明确为“初始 Top-K 的补检后集合证据召回提升”，同时给出候选量、F1 和失败例。

## 5. 必要的补充佐证与可省略测试

| 编号 | 内容 | 是否需要 | 最小产物 |
|---|---|---|---|
| E01 | 补回被 Top-K 截断的关键历史 | 申报 Bonus 时需要机制佐证 | 如有成功例，给出原/新增 ID、原文、关系/答案变化和候选数量；正式集无收益则如实报告，可另用明确标为开发集的案例解释机制 |
| E02 | 失败与非动态题回归 | 需要 | 1 个真实失败例；普通事实/稳定偏好未恶化的汇总；如有误拒答保留并解释 |
| E03 | 已有 16 道真实历史诊断 | 建议复跑，不另造大量题 | 原始/补写题区分、暂定标注说明、逐题结果；不冒充独立金标 |
| E04 | 同候选预算对照 | 只有想主张“更高检索效率”才需要 | 每题补检得到 N 条时，与原始 Top-N 比；预算上限/实际返回量明确记录。现有 CLI 没有逐题动态 N 适配 |
| E05 | 时延、实际 LLM 调用/Token | 只有主张加速或降成本才需要 | 模型预热、重复测量、同缓存策略、实际调用与失败次数；不能用 Resolver 次数代替 |

不建议额外做：全量新模型对比、权重穷举、剩余 4 段扩展数据、多用户压力、生产部署等与本次提交无关的实验。
已有单元测试覆盖数量上限、无种子、样本隔离、真实对立值、非相邻矛盾；T01 复跑即可，不必全部人工重复。

已有专项复现：

```bash
.venv/bin/python -m evaluation.state_diagnostics
```

需要本地向量模型缓存或正常下载权限。此前开发机将模型缓存放在 `data/cache/huggingface`，使用该缓存时设置 `HF_HOME` 指向它；其他机器可沿用自己的缓存目录。

## 6. 测试同学交付什么

建议存放于 `evaluation/results/final/<run-id>/`，不覆盖现有探索结果：

1. `manifest.json`：提交号、dirty 状态、课程划分、数据/标注哈希、模型与依赖版本、所有参数、评分口径、历史使用说明。
2. 原始逐题 JSON/CSV：问题 ID、sample_id、标注、初始/新增/有效 Memory、关系、答案、证据、拒答/停止原因、各项得分。
3. `summary.md`：主结果表、关系/有效记忆表、Bonus 表、按对话/题型拆分、排除数量和原因。
4. 成功/失败案例各至少 1 个，含原文定位；Web 截图与运行日志。
5. 本轮所有运行命令；缺失/失败项清单，不以空白掩盖。

最小配置记录模板：

```yaml
run_id: 待填
code_commit: 待填
working_tree_clean: 待核对
dev_sample_ids: 待填课程指定4段
test_sample_ids: 待填课程指定2段
known_previous_usage: 待填
data_and_annotation_hashes: 待填
retriever: hybrid
embedding_model_and_revision: 待填
lexical_weight: 0.4
resolver_and_judge_model: 待填
answer_generator_and_parameters: 待填
top_k: 5
max_expansion_memories: 50
scoring_script_and_version: 待填
included_and_excluded_question_counts: 待填
```

不要把 API Key 或其他凭据写入配置记录。

供报告/PPT 填数的表：

| 方法 | 对话/题数 | 原始 R@5 | R@10（适用时） | 补检后集合召回 | 动态关系准确率 | 有效记忆指标 | 答案 F1 | 平均候选 | 拒答数 |
|---|---|---|---|---|---|---|---|---|---|
| Full Text | 待测 | 不适用 | 不适用 | 不适用 | 不适用 | 不适用 | 待测 | 全文 Token | 待测 |
| Vector RAG | 待测 | 待测 | 单列配置 | 不适用 | 不适用 | 不适用 | 待测 | K | 待测 |
| 固定 K 状态系统 | 待测 | 待测 | 不适用 | 不适用 | 待测 | 待测 | 待测 | K | 待测 |
| 更大 K 状态系统 | 待测 | 不适用 | 待测 | 不适用 | 待测 | 待测 | 待测 | 10 | 待测 |
| Bonus 系统 | 待测 | 待测 | 不适用 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |

Vector RAG 与 Hybrid 的检索不同；Bonus 的隔离贡献以“相同 Hybrid、相同 Resolver”的三组为依据。

## 7. 最终完成检查

- [ ] 课程数据和动态标注已确认；正式评测与开发探索结果分开。
- [ ] 三项课程指标、Full Text / Vector RAG 对照已完成，或明确标出真实缺口。
- [ ] 原始 Recall@K 与扩展集合召回没有混写，未因中期数据量不同伪造提升。
- [ ] 关系模块/单元测试没有冒充端到端动态准确率。
- [ ] 报告与 PPT 使用同一批最终数字和配置，提升与退化均保留。
- [ ] 可运行代码、Memory JSON、结果、报告 PDF、PPT/PDF、必要过程材料均在提交包中。
