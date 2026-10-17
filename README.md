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
- `POST /api/query`：全链路（等 B2 的 Dynamic State）

检索策略由 `DMS_RETRIEVER` 控制，默认 `auto`（hybrid，模型不可用时退回 bm25）：

```bash
DMS_RETRIEVER=embedding uvicorn backend.main:app --reload
```

## 测试与评估

```bash
python -m pytest -q                      # 契约 + 三种检索策略 + HTTP 接口
python -m evaluation.recall_at_k \
    --json-out evaluation/results/recall_conv30.json
```
