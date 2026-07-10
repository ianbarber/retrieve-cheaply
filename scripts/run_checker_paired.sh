#!/usr/bin/env bash
# Local-only checker calibration and paired revisions. No API calls.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
MODEL="${MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct}"
NAMES="${NAMES:-auth_shapes_protocol,auth_machine_enum,auth_graph_edges}"
DRAFTS="runs/pilot/checker_drafts_7b.json"

"$PY" scripts/experiments/checker_paired.py generate "$DRAFTS" \
  --model "$MODEL" --names "$NAMES" --temperature 0.7 --seed 0 --gpu-only
"$PY" scripts/experiments/checker_paired.py calibrate "$DRAFTS" \
  --minimum 0.2 --maximum 0.7 --min-coherent 2
"$PY" scripts/experiments/checker_paired.py revise "$DRAFTS" \
  runs/pilot/checker_revisions_7b.json --model "$MODEL" \
  --arms control,diagnostics,gate,noisy --gpu-only
