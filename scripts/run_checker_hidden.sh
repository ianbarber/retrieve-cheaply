#!/usr/bin/env bash
# Controlled checker-only hidden-defect case series; local model, no API spend.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

MODEL="${MODEL:-Qwen/Qwen3.5-27B}"
REVISION="${REVISION:-b7ca741b86de18df552fd2cc952861e04621a4bd}"
DRAFTS="${DRAFTS:-runs/protocol/checker_hidden_v1_multiline.json}"
OUT="${OUT:-runs/pilot/checker_hidden_qwen35_27b_multiline_pilot3.json}"
NAMES="${NAMES:-auth_cart_typeddict,auth_multimap_generic,auth_graph_edges}"

if [ -e "$OUT" ]; then
  echo "refusing to overwrite checker hidden-defect output: $OUT" >&2
  exit 2
fi

"$PY" scripts/experiments/checker_paired.py revise "$DRAFTS" "$OUT" \
  --model "$MODEL" --revision "$REVISION" \
  --names "$NAMES" \
  --arms control,diagnostics,gate --checker-positive-only \
  --temperature 0 --seed 0 --seeds 1 \
  --max-new 1000 --max-turns 8 --max-reads 4 --gpu-only

"$PY" scripts/analysis/analyze_checker_paired.py --drafts "$DRAFTS" --revisions "$OUT"
