# T04 统一 QA 对照（50 题，自定划分）

日期：2026-11-01。本结果用于填写课程要求的 Full Text / Vector RAG 对照，
不是官方独立测试集成绩。

## 划分口径

课程只提供 10 段 LoCoMo，未下发官方 4 开发 + 2 测试划分与动态标注。
本组自定划分：开发 conv-41/42/43/44，测试 conv-47/48。
题单、标准答案与评分口径均由本组从 LoCoMo QA 自行整理，属自定设计。

## 数据与配置

- Memory：`outputs/final-test-v1/memories`（冻结，6 段共 2,882 条，哈希已复核）。
- 题集：`evaluation/results/final/final-test-v1/recall-test-cases.json` 中随机 50 道（seed 7），
  仅含可映射到 Memory 的 category 1–4 题。
- 检索：Hybrid（BM25 0.4 + all-MiniLM-L6-v2 0.6），Top-K=5。
- 状态解析：rules；补检上限 50 条。
- 答案生成：四种方法共用 deepseek-flash 同一生成器，只换输入上下文。
- F1：本地英文 token 口径（小写字母数字分词，去 a/an/the），拒绝计 0；非官方脚本。

## 结果

| 方法 | 答案 F1 | 拒答 | 平均上下文 |
|---|---:|---:|---:|
| Full Text | 0.461 | 9 | 83,740 字符 |
| Vector RAG | 0.340 | 20 | 723 字符 |
| 状态 Top-K | 0.310 | 22 | 754 字符 |
| 状态 Bonus | 0.334 | 22 | 754 字符 |

## 关键发现

50 道题中补检触发 0 次，全部被判 `not_dynamic` 或 `no_new_memory`。
因此“状态 Bonus”与“状态 Top-K”的输入候选完全相同，两者 F1 之差（0.334 对 0.310）
是 DeepSeek 随机波动，不能解读为补检收益。

状态系统用约 0.9% 的上下文（754 字符 对 83,740 字符）取得 Full Text 约 67% 的 F1，
同时额外提供证据可追溯与动态状态维护；但绝对 F1 低于 Full Text，也略低于纯 Vector RAG。

## 边界

- 50 题、单一种子、本地 token F1、DeepSeek 非确定性，不能外推到全部 340 题或官方口径。
- 仅含可映射题，完全未映射题未计入，QA 分母口径与正式要求不同。
- 官方 F1 脚本与动态标注到位后需重跑。

复现命令：

```bash
HF_HOME="$PWD/data/cache/huggingface" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.venv/bin/python -m evaluation.final.qa_compare \
  --cases evaluation/results/final/qa-compare-v1/qa-50-cases.json \
  --raw data/raw/locomo10.json \
  --memory-dir outputs/final-test-v1/memories \
  --top-k 5 --resolver rules --provider deepseek --model deepseek-flash \
  --json-out evaluation/results/final/qa-compare-v1/qa-50.json
```
