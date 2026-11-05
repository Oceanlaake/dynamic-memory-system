#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

resolver="${DMS_STATE_RESOLVER:-rules}"
provider="${DMS_LLM_PROVIDER:-}"
model="${DMS_LLM_MODEL:-}"

if [[ "${1:-}" == "--deepseek" ]]; then
  resolver="hybrid"
  provider="deepseek"
  model="${DMS_LLM_MODEL:-deepseek-flash}"
  shift
fi

if [[ $# -ne 0 ]]; then
  echo "Usage: ./demo/start_demo.sh [--deepseek]" >&2
  exit 2
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

memory_dir="${DMS_MEMORY_DIR:-data/demo_memories}"
echo "Starting backend with memory data: $memory_dir"
echo "B2 resolver: $resolver${provider:+ / $provider}${model:+ / $model}"
echo "Final answers use the configured LLM (DMS_ANSWER_PROVIDER / DMS_ANSWER_MODEL); no template fallback."
backend_env=(
  "DMS_MEMORY_DIR=$memory_dir"
  "DMS_RETRIEVER=${DMS_RETRIEVER:-bm25}"
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
