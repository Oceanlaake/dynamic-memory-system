#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "Missing Python environment. Run: python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt" >&2
  exit 1
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "Missing frontend dependencies. Run: cd frontend && npm ci" >&2
  exit 1
fi

memory_dir="${DMS_MEMORY_DIR:-data/memories}"
echo "Starting backend with memory data: $memory_dir"
DMS_MEMORY_DIR="$memory_dir" \
DMS_RETRIEVER="${DMS_RETRIEVER:-bm25}" \
DMS_STATE_RESOLVER="${DMS_STATE_RESOLVER:-rules}" \
  .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
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

echo "Backend ready: http://127.0.0.1:8000/docs"
echo "Frontend:      http://127.0.0.1:5173"
cd frontend
npm run dev -- --host 127.0.0.1
