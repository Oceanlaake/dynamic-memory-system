# Dynamic Memory System Demo

将长期对话转换为可检索、可更新、可追溯的记忆，并演示 B1 Top-K 检索、B2 动态状态解析与 Bonus Graph Memory 多跳检索。

**最终提交材料：**[最终报告（PDF）](docs/final/final-report.pdf) · [报告源文件](docs/final/final-report.typ) · [最终 PPT](docs/final/final-presentation.pdf) · [材料入口说明](docs/final/README.md)。

最终数字以最终报告与 [合并实验结果](docs/results/results-v1-v2.md) 为准：11 月 9 日最终运行（DeepSeek，340 题测试集）中 Hybrid K5 / K5 + 补检 / Adaptive Graph / Hybrid K10 / Full Text 的 F1 分别为 0.4611 / 0.4823 / 0.4837 / 0.5014 / 0.5692，开发集 650 题复核了补选收益。11 月 5 日的 [多模型 / 补检对照](docs/results/run-v1-2026-11-05.md) 使用旧版答案提示词，已作为 v1 并入合并结果，只做同题配对的版本对照。逐请求日志与重复上下文仅在本地保留，不进入 GitHub。

## 仓库结构

| 路径 | 内容 |
|---|---|
| `backend/`、`frontend/`、`APIs/` | FastAPI 后端、React 前端与 JSON Schema 接口契约 |
| `evaluation/` | 评测脚本；结果见 [`evaluation/results/`](evaluation/results/README.md) |
| `scripts/` | [`rerun_final.sh`](scripts/rerun_final.sh)：最终版一键重测（DeepSeek，可续跑） |
| `docs/` | [文档索引](docs/README.md)：最终提交物、设计说明、实验结果、课程材料、历史归档 |
| `process/` | [过程管理记录](process/README.md)：组会纪要、技术决策、协作截图 |
| `demo/`、`tests/` | Demo 启动与验收、自动化测试 |

## 复现最终实验

```bash
./scripts/rerun_final.sh plan      # 只规划上下文，不调用 API
./scripts/rerun_final.sh run       # 调用 DeepSeek（读取 .env 的 DEEPSEEK_API_KEY；中断后重跑即续跑）
./scripts/rerun_final.sh publish   # 汇总到 evaluation/results/run-v2-2026-11-09/
```

## 启动

需要 Python 3.10+、Node.js 18+，在仓库根目录执行：

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm ci)
cp .env.example .env
# 填写 DEEPSEEK_API_KEY；状态分析默认 rules（本地），最终答案由 DeepSeek 生成。
./demo/start_demo.sh --final
```

`--final` 使用最终实验的 6 个冻结样本（`outputs/final-test-v1/memories`）与 Hybrid 检索，可在页面中开启 Graph Memory，复现报告中的 conv-41 “Maria's dogs' names” 等案例；不加 `--final` 时为中期演示数据（conv-30 的 15 条 Memory）。检索模型 `all-MiniLM-L6-v2`：提交的代码压缩包已在 `data/cache/huggingface` 附带缓存，启动脚本会自动使用、无需联网；从 GitHub 克隆时首次运行会自动下载（国内网络可先设置 `export HF_ENDPOINT=https://hf-mirror.com`）。

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
Graph 节点、边、导出和离线消融见 [`docs/design/supplement-graph-memory.md`](docs/design/supplement-graph-memory.md)，
340 题结果见 [`docs/results/graph-early-2026-11-08.md`](docs/results/graph-early-2026-11-08.md)。

上述校验明确使用测试替身，只验证集成，不代表模型 F1。真实模型的质量与 Token 对照见 [v1 + v2 合并实验结果](docs/results/results-v1-v2.md)。
