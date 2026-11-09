#!/usr/bin/env bash
# 生成最终提交物到 submission/（Git 忽略）：
#   1. 最终报告 PDF        2. 最终展示 PPT（pptx + pdf）
#   3. 可运行项目代码 zip  4. 过程记录 zip
# 用法：./scripts/package_submission.sh
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="喵喵喵喵喵-智能体动态记忆管理系统"
OUT="submission"
mkdir -p "$OUT"
rm -f "$OUT"/*.zip "$OUT"/*.pdf "$OUT"/*.pptx

cp docs/final/final-report.pdf        "$OUT/1-最终报告.pdf"
# 可编辑 PPT 不入库；放在 docs/final/final-presentation.pptx 时一并打包
[[ -f docs/final/final-presentation.pptx ]] && cp docs/final/final-presentation.pptx "$OUT/2-最终展示.pptx"
cp docs/final/final-presentation.pdf  "$OUT/2-最终展示.pdf"

# 3. 项目代码：不含依赖目录、密钥、Git 历史、本地审计日志、历史归档结果与单独提交的大文件；
#    只保留复现最终结论所需的结果（冻结题单、最终重测、11/5 结果包、召回消融、合并汇总）。附带检索模型缓存以便离线运行。
zip -qr "$OUT/3-项目代码-dynamic-memory-system.zip" . \
  -x ".git/*" ".venv/*" "frontend/node_modules/*" "frontend/dist/*" ".env" \
     ".local-archive/*" "Claude outputs/*" "submission/*" "milestones/*" "process/*" \
     "evaluation/results/llm-comparison/*" "evaluation/results/diagnostics/*" \
     "evaluation/results/evidence-expansion-v3/*" "evaluation/results/archive/*" \
     "docs/final/final-presentation.pptx" \
     "*/__pycache__/*" "*.pyc" "*.DS_Store" ".pytest_cache/*" ".vscode/*" \
     "data/cache/embeddings/*" "data/cache/huggingface/xet/*" "data/cache/huggingface/hub/blobs/*" \
     "data/cache/huggingface/hub/models--*/blobs/*"

# 4. 过程记录：会议纪要、技术决策、协作截图、过程大纲与团队工作流程。
tmp="$(mktemp -d)"
mkdir -p "$tmp/过程记录"
cp -R process/. "$tmp/过程记录/"
cp docs/course/team_workflow.pdf "$tmp/过程记录/team_workflow.pdf"
find "$tmp" -name ".DS_Store" -delete 2>/dev/null || true
(cd "$tmp" && zip -qr - "过程记录") > "$OUT/4-过程记录.zip"
rm -rf "$tmp"

ls -lh "$OUT"
