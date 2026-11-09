#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

resolver="${DMS_STATE_RESOLVER:-rules}"
provider="${DMS_LLM_PROVIDER:-}"
model="${DMS_LLM_MODEL:-}"

final_mode=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --deepseek)
      resolver="hybrid"
      provider="deepseek"
      model="${DMS_LLM_MODEL:-deepseek-flash}"
      ;;
    --final)
      # 最终版：6 个冻结样本（含 conv-41 等 Graph 案例）+ Hybrid 检索，与最终实验配置一致。
      final_mode=1
      ;;
    *)
      echo "Usage: ./demo/start_demo.sh [--final] [--deepseek]" >&2
      exit 2
      ;;
  esac
  shift
done

# 优先使用仓库自带的检索模型缓存（data/cache/huggingface），无需访问 HuggingFace。
if [[ -z "${HF_HOME:-}" && -d data/cache/huggingface ]]; then
  export HF_HOME="$repo_root/data/cache/huggingface"
fi

if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "Missing Python environment. Run: python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt" >&2
  exit 1
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "Missing frontend dependencies. Run: cd frontend && npm ci" >&2
  exit 1
fi

for port in 8000 5173; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Stop the existing Demo process before starting a new one." >&2
    exit 1
  fi
done

default_dir="data/demo_memories"
default_retriever="bm25"
if [[ "$final_mode" == 1 ]]; then
  default_dir="outputs/final-test-v1/memories"
  default_retriever="hybrid"
fi
memory_dir="${DMS_MEMORY_DIR:-$default_dir}"
echo "Starting backend with memory data: $memory_dir"
echo "B2 resolver: $resolver${provider:+ / $provider}${model:+ / $model}"
echo "Final answers use the configured LLM (DMS_ANSWER_PROVIDER / DMS_ANSWER_MODEL); no template fallback."
backend_env=(
  "DMS_MEMORY_DIR=$memory_dir"
  "DMS_RETRIEVER=${DMS_RETRIEVER:-$default_retriever}"
  "DMS_STATE_RESOLVER=$resolver"
)
if [[ -n "$provider" ]]; then
  backend_env+=("DMS_LLM_PROVIDER=$provider")
fi
if [[ -n "$model" ]]; then
  backend_env+=("DMS_LLM_MODEL=$model")
fi
env "${backend_env[@]}" .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!

cleanup() {
  kill "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in {1..30}; do
  if curl --noproxy '*' --silent --fail http://127.0.0.1:8000/api/health >/dev/null; then
    break
  fi
  if ! kill -0 "$backend_pid" 2>/dev/null; then
    echo "Backend stopped before becoming ready." >&2
    exit 1
  fi
  sleep 0.2
done

if ! curl --noproxy '*' --silent --fail http://127.0.0.1:8000/api/health >/dev/null; then
  echo "Backend did not become ready at http://127.0.0.1:8000." >&2
  exit 1
fi
if ! kill -0 "$backend_pid" 2>/dev/null; then
  echo "Backend stopped unexpectedly during startup." >&2
  exit 1
fi

echo "Backend ready: http://127.0.0.1:8000/docs"
echo "Frontend:      http://127.0.0.1:5173"
cd frontend
npm run dev -- --host 127.0.0.1 --strictPort
