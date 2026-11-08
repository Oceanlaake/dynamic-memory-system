# Dynamic Memory System Demo

将长期对话转换为可检索、可更新、可追溯的记忆，并演示 B1 Top-K 检索、B2 动态状态解析与 Bonus Graph Memory 多跳检索。

最终材料从 [报告与 PPT 入口](docs/final/README.md) 阅读；实验采用 [340 题正式结果](docs/large-scale-results-2026-11-05.md)，可审计数据见 [提交结果包](evaluation/results/submission-v1/README.md)。逐请求日志与重复上下文仅在本地保留，不进入 GitHub。

## 启动

需要 Python 3.10+、Node.js 18+，在仓库根目录执行：

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm ci)
cp .env.example .env
# 填写答案模型的 API Key；默认状态分析 rules，最终答案由 LLM 生成。
./demo/start_demo.sh
```

浏览器打开 <http://127.0.0.1:5173>，点击任一预设场景即可演示。

检索、补检和默认 rules 状态分析在本地运行；最终答案会调用配置的 LLM。需要额外启用 DeepSeek 关系 Judge 时：

```bash
./demo/start_demo.sh --deepseek
```

验证 Demo：

```bash
.venv/bin/python demo/verify_demo.py --stub-llm
```

更完整的说明见 [`demo/README.md`](demo/README.md)，接口文档见 [`APIs/README.md`](APIs/README.md)。
Graph 节点、边、导出和离线消融见 [`docs/graph-memory.md`](docs/graph-memory.md)，
340 题结果见 [`docs/graph-memory-results-2026-11-08.md`](docs/graph-memory-results-2026-11-08.md)。

上述校验明确使用测试替身，只验证集成，不代表模型 F1。真实统一 QA 与多模型/Token 对照见 [统一 LLM 作答与评测](docs/unified-llm-qa.md)。
