import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DMS_MEMORY_DIR", str(REPO_ROOT / "data" / "memories"))
# 测试不依赖模型下载：默认用离线可跑的 BM25
os.environ.setdefault("DMS_RETRIEVER", "bm25")


import pytest


@pytest.fixture(autouse=True)
def fake_answer_dependency():
    """Unit HTTP tests must not consume paid APIs or fall back to templates."""
    from backend.api.routes import get_answer_generator
    from backend.main import app
    from tests.fakes import FixtureAnswerGenerator
    previous = app.dependency_overrides.get(get_answer_generator)
    app.dependency_overrides[get_answer_generator] = lambda: FixtureAnswerGenerator()
    yield
    if previous is None:
        app.dependency_overrides.pop(get_answer_generator, None)
    else:
        app.dependency_overrides[get_answer_generator] = previous
