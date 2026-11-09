# 智能体动态记忆管理系统（Dynamic Memory System）

将 LoCoMo 长期对话转换为可检索、可更新、可追溯的结构化 Memory：Top-K 检索后进行**补选**（查询驱动补检 / Graph Memory 自适应补选），解析状态的新旧关系，再由 LLM 依据有效证据作答并给出可回链的引用。

**最终提交材料：**[最终报告（PDF）](docs/final/final-report.pdf) · [最终展示（PDF）](docs/final/final-presentation.pdf) · [过程记录](process/README.md) · [文档索引](docs/README.md)

## 快速启动

两种方式任选其一。都需要一个 DeepSeek API Key：检索、补选和状态分析在本地运行，只有最终答案调用模型。

```bash
cp .env.example .env
# 编辑 .env，把 DEEPSEEK_API_KEY=replace-with-your-key 改成真实密钥
```

### 方式一：Docker（推荐，只需安装 Docker）

```bash
docker compose up --build
```

首次构建需要下载 Python / Node 依赖，约几分钟；之后打开 <http://localhost:5173>。国内网络可使用镜像构建：

```bash
docker compose build \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  --build-arg NPM_REGISTRY=https://registry.npmmirror.com
docker compose up
```

容器默认使用最终实验配置：6 个冻结样本（`outputs/final-test-v1/memories`）+ Hybrid 检索。

### 方式二：本地运行（Python 3.10+、Node.js 18+）

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm ci)
./demo/start_demo.sh --final
```

打开 <http://127.0.0.1:5173>。`--final` 与 Docker 使用相同的最终实验配置；不加 `--final` 时为中期演示数据（conv-30 的 15 条 Memory）。加 `--deepseek` 可额外启用 DeepSeek 关系判断。

检索模型 `all-MiniLM-L6-v2` 已在提交压缩包的 `data/cache/huggingface` 中附带，两种方式都会自动使用、无需访问 HuggingFace；从 GitHub 克隆时首次运行会自动下载（国内网络可先 `export HF_ENDPOINT=https://hf-mirror.com`）。

### 使用

1. 在页面中选择对话样本（如 `conv-41`），点击预设问题或输入问题，例如 *What are Maria's dogs' names?*。
2. 打开“Graph Memory 多跳检索”开关，可看到 Top-K 候选、补选路径、状态关系、答案与引用的 Memory ID 及原始对话证据。

## 测试与复现

```bash
.venv/bin/python -m pytest                       # 自动化测试（不调用模型）
.venv/bin/python demo/verify_demo.py --stub-llm  # Demo 集成验收（测试替身，不代表模型 F1）
```

复现最终实验（调用 DeepSeek，中断后重跑同一命令即续跑）：

```bash
./scripts/rerun_final.sh plan      # 只规划请求，不调用 API
./scripts/rerun_final.sh run       # 测试集七种方法 + 开发集 Graph 三组
./scripts/rerun_final.sh publish   # 汇总到 evaluation/results/run-v2-2026-11-09/ 并更新合并结果
```

最终数字以报告与 [v1 + v2 合并实验结果](docs/results/results-v1-v2.md) 为准。v2（11 月 9 日，DeepSeek，340 题测试集）中 Hybrid K5 / K5 + 补检 / Adaptive Graph / Hybrid K10 / Full Text 的 F1 分别为 0.4611 / 0.4823 / 0.4837 / 0.5014 / 0.5692，开发集 650 题复核了补选收益；v1（11 月 5 日）使用旧版答案提示词，只做同题配对的版本对照。

## 仓库结构

| 路径 | 内容 |
|---|---|
| `backend/`、`frontend/`、`APIs/` | FastAPI 后端、React 前端与 JSON Schema 接口契约（[接口文档](APIs/README.md)） |
| `data/`、`outputs/` | LoCoMo 原始数据、演示数据、抽取的 Memory 与冻结样本 |
| `evaluation/` | 评测脚本与结果（[结果索引](evaluation/results/README.md)） |
| `scripts/` | 一键重测、结果汇总 / 合并、提交打包 |
| `demo/`、`tests/` | Demo 启动与验收（[说明](demo/README.md)）、自动化测试 |
| `docker/`、`docker-compose.yml` | Docker 启动配置 |
| `docs/` | [文档索引](docs/README.md)：最终提交物、补选机制说明、实验结果、课程材料 |
| `process/` | [过程管理记录](process/README.md)：五次组会纪要、技术决策、协作截图与过程大纲 |
