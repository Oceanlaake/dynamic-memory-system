# 最终提交口径（自定划分）

更新：2026-11-01。本文是报告与 PPT 的统一数字来源，所有结论以此为准。

## 划分与总体定位

课程仅提供 10 段 LoCoMo，未下发官方 4 开发 + 2 测试划分、动态标注与评分脚本。
本组自定：开发 conv-41/42/43/44，测试 conv-47/48。
题单、标准答案、评分口径均由本组从 LoCoMo QA 自行整理，属自定设计，
不是官方独立测试集成绩；官方标注与 F1 脚本不会下发，不再等待。

## 创新点与机制分析

### 问题定义

B1 Top-K 检索为控制候选规模，会把同一主体同一槽位的早期历史截断。
对“当前状态 / 变化 / 持续时间”类问题，缺少被截断的历史会导致：
当前状态判错、变化题缺一端而无法建立有序前后关系、持续时间题缺起点或终点锚点。

### 机制：查询驱动的状态槽位历史补全

- 从初始 Top-K 候选提取 `(subject, attribute)` 槽位，按问题相关性选择种子槽位。
- 在同一对话样本内按槽位单轮闭包补齐同槽位历史；新增候选 `score=0`、
  `candidate_source=slot_expansion`，初始排序保持不变，不伪造相关度。
- 补检后只调用一次动态状态解析器，不重复解析。
- 新增上限 50 条，超限截断并保守拒答。
- 不引入图数据库、通用多跳、多轮 Agent、跨属性生命周期映射或压缩。

设计边界：只针对“状态历史被 Top-K 截断”这一具体失败模式，不做通用 RAG 增强。

### 消融方法与隔离口径

固定同一 Retriever、同一 Resolver、同一数据与参数，三组对照：固定 K、更大 K、Top-K+补检。
与“更大 K”对比用于排除“收益只是多放候选”；原始 Recall@K 与补检后集合证据召回分开命名，不混用。

### 结果与瓶颈定位

- 目标场景有效：16 题状态专项上，Hybrid 证据召回 65.63% → 93.75%，平均候选 3 → 6。
- 未转化为答案 F1：可回答题 F1 0.330 → 0.294；原因在答案层——有效记忆选择取 rank-1、
  模板答案、就业链冲突、空 attribute 锚点。
- 宽口径 QA 上几乎不触发：340 题触发 2 题、50 题触发 0 题；LoCoMo QA 绝大多数是事实题，动态题本身稀缺。
- 整体 QA F1 无净收益：状态 Top-K 0.310 与 Bonus 0.334 的差异为模型随机，低于纯 Vector RAG 0.340 与 Full Text 0.461。
- 结论：瓶颈在下游答案生成与有效记忆选择，而非检索；补检是窄机制，在召回层有效，在 QA 层不构成提升。

### 迭代修正

- 多值偏好属性（favorite_activity / activity）误判为互斥状态 → 归入集合槽位，消除 false-conflict 拒答。
- 问时间的题优先选带有效日期的事件记忆，并直接输出日期。
- 上述修正消除了一类误拒答，但未改变“答案 F1 无净收益”的总体结论。

## 冻结配置

| 项 | 值 |
|---|---|
| 检索 | Hybrid：BM25 0.4 + all-MiniLM-L6-v2 0.6 |
| Embedding 模型 | sentence-transformers/all-MiniLM-L6-v2，revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` |
| 状态解析 | rules（默认）；关系辅助对照用 deepseek-flash |
| Top-K | 5 |
| 补检上限 | 新增 50 条 |
| 答案生成 | 四种对照方法共用 deepseek-flash 生成器，仅输入上下文不同 |
| F1 | 本地英文 token 口径：小写字母数字分词，去 a/an/the；拒绝计 0 |
| 依赖 | sentence-transformers 6.1.0，openai 3.35.1，fastapi 0.150.0 |

## 最终结果

### T02 检索 Recall@K（测试集，轮次级）

| 方法 | R@1 | R@3 | R@5 | R@10 |
|---|---:|---:|---:|---:|
| BM25 | 35.87% | 52.91% | 61.05% | 67.76% |
| Embedding | 39.11% | 60.94% | 68.54% | 75.26% |
| Hybrid | 43.43% | 60.29% | 67.87% | 75.03% |

### T03 关系模块辅助回归（16 对，直接提供两条 Memory）

| 模式 | 正确 | 准确率 |
|---|---:|---:|
| rules | 9/16 | 56.25% |
| deepseek-flash | 16/16 | 100.00% |

非端到端动态题成绩；方向校验与有效 Memory 端到端指标缺官方标注，未评测。

### T04 统一 QA 对照（50 题，seed 7，deepseek-flash 作答）

| 方法 | 答案 F1 | 拒答 | 平均上下文 |
|---|---:|---:|---:|
| Full Text | 0.461 | 9 | 83,740 字符 |
| Vector RAG | 0.340 | 20 | 723 字符 |
| 状态 Top-K | 0.310 | 22 | 754 字符 |
| 状态 Bonus | 0.334 | 22 | 754 字符 |

50 题中补检触发 0 次，Bonus 与 Top-K 输入候选相同，两者 F1 差为模型随机，不计为补检收益。

### T05 补检消融（测试集 340 题，模板作答）

| 方案 | Memory 集合召回 | 模板 F1 | 平均候选 | 拒答 |
|---|---:|---:|---:|---:|
| K=5 | 59.92% | 0.1257 | 5.00 | 9 |
| K=10 | 67.45% | 0.1173 | 9.99 | 17 |
| K=5+补检 | 59.92% | 0.1252 | 5.07 | 11 |

### 状态专项诊断（conv-30，16 题，自建暂定标注）

Hybrid：补检使证据召回 65.63% → 93.75%，平均候选 3 → 6；
可回答题 F1 0.330 → 0.294。证明机制能找回被 Top-K 截断的历史，但未转化为答案 F1。

### 六段 Memory 校验

共 2,882 条，ID 全部唯一，证据引用缺失 0，时间字段缺失 0；
空 attribute 791 条（27.4%），与“开业/录取等事件无槽位、补检无法连线”的现象一致。

## 复现命令

```bash
# 检索
.venv/bin/python -m evaluation.recall_at_k \
  --cases evaluation/results/final/final-test-v1/recall-test-cases.json \
  --memory-dir outputs/final-test-v1/memories --retrievers bm25 embedding hybrid \
  --ks 1,3,5,10 --json-out evaluation/results/final/recall.json

# 补检消融
.venv/bin/python -m evaluation.slot_expansion \
  --cases evaluation/results/final/final-test-v1/recall-test-cases.json \
  --memory-dir outputs/final-test-v1/memories --retriever hybrid --resolver rules \
  --top-k 5 --larger-k 10 --max-expansion-memories 50 \
  --json-out evaluation/results/final/bonus-ablation.json

# 统一 QA 对照（50 题）
HF_HOME="$PWD/data/cache/huggingface" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.venv/bin/python -m evaluation.final.qa_compare \
  --cases evaluation/results/final/qa-compare-v1/qa-50-cases.json \
  --raw data/raw/locomo10.json --memory-dir outputs/final-test-v1/memories \
  --top-k 5 --resolver rules --provider deepseek --model deepseek-flash \
  --json-out evaluation/results/final/qa-compare-v1/qa-50.json

# 六段 Memory 校验
.venv/bin/python -m evaluation.final.validate_memories \
  --json-out evaluation/results/final/qa-compare-v1/memory-validation.json
```

## 边界与诚实声明

- 补检在宽口径 QA 上无答案 F1 收益，只在其目标场景（状态历史截断）上有召回级收益。
- 状态系统以约 0.9% 的上下文取得 Full Text 约 67% 的 F1，并额外提供证据可追溯与动态状态维护；
  绝对 F1 低于 Full Text，也略低于纯 Vector RAG。
- 50 题为单一种子样本；正式结论不建议外推到 340 题或宣称统计显著性。
- 所有关系/有效 Memory 端到端指标缺官方标注，仅能报告辅助回归与自建专项诊断。
