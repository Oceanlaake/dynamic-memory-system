import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DMS_MEMORY_DIR", str(REPO_ROOT / "data" / "memories"))
# 测试不依赖模型下载：默认用离线可跑的 BM25
os.environ.setdefault("DMS_RETRIEVER", "bm25")
