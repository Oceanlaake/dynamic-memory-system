# 后端：FastAPI + 本地检索（BM25 / all-MiniLM-L6-v2）+ Graph Memory；最终答案调用 .env 中配置的 LLM。
FROM python:3.12-slim

# 国内网络可在构建时传入镜像，例如：
#   docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple
# 只装 CPU 版 torch，避免下载数 GB 的 CUDA 依赖。
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --index-url "$TORCH_INDEX_URL" torch \
 && pip install --index-url "$PIP_INDEX_URL" -r backend/requirements.txt

COPY . .

# 默认使用最终实验配置：6 个冻结样本 + Hybrid 检索；检索模型使用仓库自带缓存，无需访问 HuggingFace。
ENV DMS_MEMORY_DIR=outputs/final-test-v1/memories \
    DMS_RETRIEVER=hybrid \
    DMS_STATE_RESOLVER=rules \
    HF_HOME=/app/data/cache/huggingface

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
