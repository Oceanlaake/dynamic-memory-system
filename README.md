# Dynamic Memory System Demo

将长期对话转换为可检索、可更新、可追溯的记忆，并演示 B1 Top-K 检索与 B2 动态状态解析。

## 启动

需要 Python 3.10+、Node.js 18+，在仓库根目录执行：

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm ci)
./demo/start_demo.sh
```

浏览器打开 <http://127.0.0.1:5173>，选择“仅真实链路”，点击任一预设场景即可演示。

默认模式完全离线。需要 DeepSeek 辅助判断 B2 记忆关系时：

```bash
cp .env.example .env
# 在 .env 中填写 DEEPSEEK_API_KEY
./demo/start_demo.sh --deepseek
```

验证 Demo：

```bash
.venv/bin/python demo/verify_demo.py
```

更完整的说明见 [`demo/README.md`](demo/README.md)，接口文档见 [`APIs/README.md`](APIs/README.md)。
