# 统一 LLM 作答与实验复现

材料入口：[最终报告与 PPT](final/README.md)。正式成绩以 [340 题结果](large-scale-results-2026-11-05.md) 与 [提交结果包](../evaluation/results/submission-v1/README.md) 为准。

## 共享生产链路

问题 → 初始检索 → 可选补检 → 规则关系/时间分析 → 证据包 → LLM 答案与引用 → 校验与展示。
`/api/query` 与正式评测共享 `backend/qa.py`。规则不生成最终模板答案；全部有界候选和引文保留，规则选中/历史/冲突仅作提示。
无候选、无相关补检种子或严格状态历史截断时可跳过生成。不是只让模型看到 rank-1，也不是无条件相信规则提示。

`effective_memories` 是规则建议，`answer_memory_ids` 是模型声明的支持记忆。
非空答案必须引用输入中的有效 Memory ID；合法 ID 不等于语义正确。
Full Text 没有 Memory ID，要求引用数组为空。不使用模板兜底，也不调用外部搜索。

## 调用与配置

检索、补检和默认 `rules` 均不调用生成 LLM；本地 embedding 编码另计资源。
答案通常调用一次 LLM；可选 `hybrid` Judge 额外调用，正式实验固定 `rules`。

```dotenv
DMS_STATE_RESOLVER=rules
DMS_ANSWER_PROVIDER=glm
DMS_ANSWER_MODEL=glm-4.7-flash
DMS_ANSWER_MAX_TOKENS=1024
GLM_API_KEY=填写本机密钥
```

支持 `deepseek`、`glm`、`openai`。DeepSeek 使用 `DEEPSEEK_API_KEY`；GLM 使用 `GLM_API_KEY`（兼容 `ZAI_API_KEY`）；OpenAI 使用 `OPENAI_API_KEY`。
GLM 标准地址为 `https://open.bigmodel.cn/api/paas/v4/`，可用 `GLM_BASE_URL` 覆盖，不是 Coding Plan 专用地址。
GLM 新系列显式关闭思考，旧 Flash 不发送 thinking。变更配置后重启后端；不要提交或展示密钥。
1024 为正式实验预算，代码/.env.example 默认仍为 256，复现必须显式传参。

## 正式复现入口

```bash
HF_HOME="$PWD/data/cache/huggingface" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -m evaluation.final.large_scale \
  --models-file evaluation/answer-models.example.json \
  --cases evaluation/results/final/final-test-v1/bonus-test-cases.json \
  --raw data/raw/locomo10.json --memory-dir outputs/final-test-v1/memories \
  --output-dir evaluation/results/llm-comparison/reproduction-v1 \
  --top-k 5 --larger-k 10 --max-expansion-memories 50 --max-output-tokens 1024
```

这会请求真实 API；离线变量只禁止下载检索模型。选新目录，恢复须保持 manifest 一致。
模型示例含 DeepSeek、GLM-4.7 和旧 Flash；4.7 本轮 429/1305，不构成有效成绩，复现前按可用性配置。
runner 覆盖全文、Embedding K5、Hybrid K5+rules、K5+补检+rules、Hybrid K10+rules；逐请求落盘、有限 API 错误重试与恢复，最后共享评分。
`model_compare.py` 保留旧四组兼容；正式五组优先 `large_scale.py`，不要两套重复运行。

## 结果与口径

- `evaluation/results/submission-v1/`：提交的轻量结果，含全部逐题答案/评分、配置、用量和校验。
- `evaluation/results/llm-comparison/`：本地原始审计与 checkpoint，Git 忽略；不删除，不作远端链接。
- `python -m evaluation.final.export_submission --source <完整结果目录> --output <新空目录>`：导出结果，不调用 API。

usage 缺失为 null；缓存是输入子集，推理是输出子集，不能重复相加。
方法比较用独立请求的等价用量，实验支出用实际请求账本；复用不意味着部署免费。
Token 不等于费用，当前仅统计答案模型，不含抽取/embedding/Judge。
`generation.status` 区分 answered/refused/error/skipped；错误不能当正确拒答。
`--stub-llm` 只验证集成；`--legacy-templates` 只复现旧诊断，都不能形成正式模型成绩。
自定已暴露划分、单轮与缺少官方动态关系金标等边界必须保留。
