# Graph Memory 离线消融结果（2026-11-08）

本页包含两个互补实验：确定性的证据召回消融，以及使用同一 DeepSeek 模型的成对答案
F1/EM 对照。逐题检索结果见
[`evaluation/results/graph-memory-v1.json`](../evaluation/results/graph-memory-v1.json)，答案聚合结果见
[`graph-answer-deepseek-v2-summary.json`](../evaluation/results/graph-answer-deepseek-v2-summary.json)。

## 配置

- 数据：冻结的自定测试集 `conv-47`、`conv-48`，340 道可映射 category 1–4 QA。
- Memory：`outputs/final-test-v1/memories`。
- 初始检索：Hybrid，BM25 0.4 + `all-MiniLM-L6-v2` 0.6，K=5。
- Graph：最大 3 跳，最多新增 5 条 Memory。
- Gold 用途：只在 Graph 检索完成后计算 Memory 集合召回和原始证据 Turn 召回；建图和遍历不读取 Gold。

## 证据召回结果

| 方法 | Memory 集合召回 | 原始证据 Turn 召回 | 平均候选 |
|---|---:|---:|---:|
| Hybrid K=5 | 59.92% | 68.07% | 5.00 |
| Hybrid K=5 + Graph Memory | 65.30% | 73.17% | 9.25 |

- Memory 召回提高 5.38 个百分点；32/340 题改善，308 题不变，没有下降题。
- 原始证据 Turn 召回提高 5.10 个百分点；28/340 题改善，312 题不变，没有下降题。
- 327 题新增了 Graph 候选；其中 232 题达到“最多新增 5 条”的预算上限。
- 平均访问 254.33 个图节点。访问节点只是本地遍历，不进入 LLM 上下文；只有选中的新增 Memory 进入回答链路。

## DeepSeek 答案 F1/EM

答案对照使用冻结的 `bonus-test-cases.json` 340 题、`deepseek-flash`、相同 Hybrid K=5
种子、rules、提示词、温度与 128 token 输出上限。标准答案只在模型生成结束后用于本地英文
token F1/EM 评分。Graph 组最多新增 5 条、最多 3 跳。646 个唯一上下文全部请求成功，
API 错误为 0。

| 方法 | F1 | EM | 证据召回 | 平均候选 | 平均输入 Token | 拒答 |
|---|---:|---:|---:|---:|---:|---:|
| Hybrid K=5 | 0.3896 | 0.2000 | 59.92% | 5.00 | 669.1 | 114 |
| Hybrid K=5 + Graph | 0.3992 | 0.1882 | 65.30% | 9.25 | 1030.6 | 108 |

- Graph 的平均 F1 增加 0.0096，即约 0.96 个百分点；33 题提高、34 题下降、273 题不变。
- EM 下降 1.18 个百分点。Graph 找回更多证据并减少 6 次拒答，但更长答案和无关上下文也会降低严格匹配。
- 平均输入 Token 增加 54.0%，平均总 Token 增加 52.5%。因此这是小幅 F1 收益与明显上下文成本的折中，不是全面胜出。
- 646 个唯一上下文共 565,410 Token，API 错误为 0；认证信息未写入结果。完整逐请求 checkpoint 仅保留在本地 Git 忽略目录。

## 解释边界

证据召回提升并不等价于每题答案质量提升。本次同模型对照观察到小幅平均 F1 上升，但改善题
改善和下降题数量接近，且 EM 与上下文效率下降。它与固定 K=10、现有查询补检的候选预算并不
相同，因此不能直接宣称更高效或全面更优。

该结果证明当前实现能够通过显式状态槽位和证据 Turn 路径找回 Top-K 外的相关 Memory，且
路径可在 Web 和结果 JSON 中审计。最终材料必须同时报告 F1、EM、Token、错误与拒答，不能
只选择召回或 F1 中较好的一项。
