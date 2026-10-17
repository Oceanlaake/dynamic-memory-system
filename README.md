# dynamic-memory-system
软件需求工程课程项目

## Demo

仓库内提供了一个不依赖第三方库的 LoCoMo → Memory 最小演示。运行：

```bash
python3 demo/prepare_locomo_demo.py
```

快速运行说明见 [`demo/README.md`](demo/README.md)，完整解说见 [`demo/DEMO_WALKTHROUGH.md`](demo/DEMO_WALKTHROUGH.md)。

## 后端

接口契约见 [`APIs/README.md`](APIs/README.md)，选型与裁决见 [`process/decisions/`](process/decisions)。

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

- 交互式接口文档：<http://127.0.0.1:8000/docs>
- `POST /api/retrieve`：问题 → Top-K 候选记忆（B1，已实现）
- `POST /api/query`：全链路（B1 检索 → B2 动态状态解析 → 答案与证据）

检索策略由 `DMS_RETRIEVER` 控制，默认 `auto`（hybrid，模型不可用时退回 bm25）：

```bash
DMS_RETRIEVER=embedding uvicorn backend.main:app --reload
```

## 测试与评估

```bash
python -m pytest -q                      # 契约 + 三种检索策略 + HTTP 接口 + 评估管道

python -m evaluation.build_cases         # qa.evidence -> memory_id，自动生成用例
python -m evaluation.recall_at_k --cases evaluation/cases/generated.json --ks 1,3,5
python -m evaluation.sweep --cases evaluation/cases/generated.json --ks 1,3,5,10
python -m evaluation.state_accuracy      # B2 四类关系准确率（默认纯规则、零 API 调用）
```

## B2 动态状态解析

`backend/dynamic_state/` 提供“确定性规则 + 可选 LLM 裁决”的混合实现：按实体、属性与时间判断
`RETAIN / UPDATE / SUPERSEDE / CONFLICT`，选择本次回答需要的有效 Memory，并回传原始证据。
明确关系由规则直接处理；语义模糊关系才交给 LLM，调用失败自动退回保守规则。未解决的冲突、
空候选或检索退化不会生成答案。

默认 `rules` 模式完全离线。项目支持 OpenAI 与 DeepSeek；使用 DeepSeek 时可在被 Git 忽略的
`.env` 中配置：

```bash
DMS_STATE_RESOLVER=hybrid
DMS_LLM_PROVIDER=deepseek
DMS_LLM_MODEL=deepseek-flash
DEEPSEEK_API_KEY="..."
```

macOS 本机也支持从 Keychain 服务 `dynamic-memory-system.deepseek-api-key` 读取密钥，优先级低于
`DEEPSEEK_API_KEY`。这样密钥不需要写入项目文件。

安装依赖后正常启动即可自动读取 `.env`：

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload

# 用同一评测集比较混合模式；会产生模型调用
python -m evaluation.state_accuracy --resolver hybrid --provider deepseek
```

B2 默认评测由 `evaluation/cases/b2_relations.json` 和
`evaluation/cases/b2_relations_challenge.json` 组成：7 个基础用例加 9 个语义难例，共 16 组
关系判断。脚本输出总准确率、分标签准确率、混淆矩阵与漏判数。

实现决策与已知限制见
[`process/decisions/2026-10-17-动态状态解析.md`](process/decisions/2026-10-17-动态状态解析.md)。
