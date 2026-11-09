#!/usr/bin/env bash
# 最终版重测（2026-11-09）：在当前答案提示词下补齐缺失对照。
#
# 用法（仓库根目录，macOS 终端）：
#   ./scripts/rerun_final.sh plan      # 只规划上下文、写 manifest，不调用 API
#   ./scripts/rerun_final.sh run       # 真实调用 DeepSeek（可中断，重跑同一命令即从 checkpoint 续跑）
#   ./scripts/rerun_final.sh publish   # 把聚合结果复制到可提交目录
#
# 三组实验（全部 deepseek-flash、温度 0、最大输出 128 token、Hybrid K=5、Graph 4 跳 / 8 条）：
#   1. test-graph     测试集 340 题：Fixed K5 / Forced Graph / Adaptive Graph（复现报告主表）
#   2. test-baselines 测试集 340 题：Full Text / Embedding K5 / Hybrid K5 / K5+补检 / Hybrid K10
#   3. dev-graph      开发集 650 题：Fixed K5 / Forced Graph / Adaptive Graph（确认没有过拟合测试集）
# 密钥从 .env 的 DEEPSEEK_API_KEY 读取，不写入任何结果文件。
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-}"
PY="${PY:-.venv/bin/python}"
TAG="${TAG:-final-rerun-2026-11-09}"
RAW="evaluation/results/llm-comparison/${TAG}"   # 完整 checkpoint，Git 忽略
PUB="${PUB:-evaluation/results/run-v2-2026-11-09}"  # 聚合结果，提交到 Git
CASES="evaluation/results/split-v1"
MEM="outputs/final-test-v1/memories"
export HF_HOME="$PWD/data/cache/huggingface" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

[[ -x "$PY" ]] || { echo "找不到 ${PY}，请先按 README 创建 .venv"; exit 1; }
[[ -d "$MEM" ]] || { echo "找不到冻结 Memory 目录 $MEM"; exit 1; }

PLAN=()
[[ "$MODE" == "plan" ]] && PLAN=(--plan-only)

graph() {  # $1=名称 $2=题单
  echo "=== ${1} ==="
  "$PY" -m evaluation.graph_answer \
    --cases "$2" --memory-dir "$MEM" --output-dir "$RAW/$1" \
    --provider deepseek --model deepseek-flash \
    --top-k 5 --max-hops 4 --max-graph-memories 8 --max-output-tokens 128 ${PLAN[@]+"${PLAN[@]}"}
}

baselines() {
  echo "=== baselines-test ==="
  "$PY" -m evaluation.final.large_scale \
    --models-file evaluation/answer-models.deepseek.json \
    --cases "$CASES/bonus-test-cases.json" \
    --raw data/raw/locomo10.json --memory-dir "$MEM" \
    --output-dir "$RAW/baselines-test" \
    --top-k 5 --larger-k 10 --max-expansion-memories 50 --max-output-tokens 128 ${PLAN[@]+"${PLAN[@]}"}
}

case "$MODE" in
  plan|run)
    if [[ "$MODE" == "run" ]] && ! grep -q '^DEEPSEEK_API_KEY=.\+' .env 2>/dev/null && [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
      echo "未找到 DEEPSEEK_API_KEY（.env 或环境变量）"; exit 1
    fi
    graph graph-test "$CASES/bonus-test-cases.json"
    baselines
    graph graph-dev "$CASES/bonus-dev-cases.json"
    echo "完成：${MODE}。真实运行结束后执行 ./scripts/rerun_final.sh publish"
    ;;
  publish)
    mkdir -p "$PUB"
    # 原始目录名（llm-comparison 下）→ 提交目录名
    for pair in "graph-test:test-graph" "graph-dev:dev-graph"; do
      src="${pair%%:*}"; dst="${pair##*:}"
      [[ -f "$RAW/$src/summary.json" ]] || { echo "缺少 $RAW/$src/summary.json，请先 run"; exit 1; }
      mkdir -p "$PUB/$dst"
      cp "$RAW/$src/manifest.json" "$RAW/$src/summary.json" "$RAW/$src/results.json" "$PUB/$dst/"
    done
    [[ -f "$RAW/baselines-test/summary.json" ]] || { echo "缺少 baselines-test 结果，请先 run"; exit 1; }
    rm -rf "$PUB/test-baselines.tmp"
    "$PY" -m evaluation.final.export_submission --source "$RAW/baselines-test" --output "$PUB/test-baselines.tmp"
    rm -rf "$PUB/test-baselines" && mv "$PUB/test-baselines.tmp" "$PUB/test-baselines"
    cat > "$PUB/test-baselines/README.md" <<'MD'
# 测试集整体方法对照（v2 最终运行）

340 题，deepseek-flash，最大输出 128 token，与 Graph 三组使用同一版答案提示词。
五组：Full Text / Embedding K5 / Hybrid K5 + rules / K5 + 补检 + rules / Hybrid K10 + rules。

- `summary.md` / `summary.json`：方法汇总与配对计数。
- `per-question.csv`：逐题标准答案、生成答案、F1/EM、状态、Memory ID 与 usage。
- `manifest.json`：冻结配置与数据 / 源码哈希；`actual-usage.json`：实际请求账本。
MD
    "$PY" scripts/summarize_rerun.py "$PUB" > "$PUB/README.md"
    "$PY" scripts/consolidate_results.py > /dev/null
    echo "已写入 ${PUB} 与合并结果，可 git add 提交。"
    ;;
  *)
    sed -n 2,15p "$0"; exit 1 ;;
esac
