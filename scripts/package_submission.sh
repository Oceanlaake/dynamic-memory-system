#!/usr/bin/env bash
# 生成四项最终提交物到 submission/（Git 忽略）：
#   1-最终报告.pdf   2-最终展示.pdf
#   3-可运行项目.zip（完整仓库，可按 README 用 Docker 或本地启动）
#   4-过程记录.zip（process/ 与 docs/）
# 用法：./scripts/package_submission.sh
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="submission"
mkdir -p "$OUT"
rm -f "$OUT"/*.zip "$OUT"/*.pdf "$OUT"/*.pptx

cp docs/final/final-report.pdf       "$OUT/1-最终报告.pdf"
cp docs/final/final-presentation.pdf "$OUT/2-最终展示.pdf"

# 3. 可运行项目：完整仓库，不含依赖目录、密钥、Git 历史、本地原始请求日志与中间诊断；
#    附带检索模型缓存（去掉重复副本），以便离线运行。
zip -qr "$OUT/3-可运行项目-dynamic-memory-system.zip" . \
  -x ".git/*" ".venv/*" "frontend/node_modules/*" "frontend/dist/*" ".env" \
     ".local-archive/*" "Claude outputs/*" "submission/*" "milestones/*" \
     "evaluation/results/llm-comparison/*" "evaluation/results/diagnostics/*" \
     "evaluation/results/evidence-expansion-v3/*" \
     "*/__pycache__/*" "*.pyc" "*.DS_Store" ".pytest_cache/*" ".vscode/*" \
     "data/cache/embeddings/*" "data/cache/huggingface/xet/*" "data/cache/huggingface/hub/blobs/*" \
     "data/cache/huggingface/hub/models--*/blobs/*"

# 4. 过程记录：process/（会议纪要、技术决策、协作截图、过程大纲）与 docs/（报告、设计说明、实验结果、课程材料）。
zip -qr "$OUT/4-过程记录.zip" process docs -x "*.DS_Store"

ls -lh "$OUT"
