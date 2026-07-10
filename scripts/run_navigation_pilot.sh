#!/usr/bin/env bash
# Local-only apparatus pilot. No API calls and no monetary spend.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
MODEL="${MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct}"
REVISION="${REVISION:-c03e6d358207e414f1eca0bb1891e29f1db0e242}"
NAMES="${NAMES:-nav_pilot_17011,nav_pilot_17027}"

"$PY" scripts/experiments/navigation_tasks.py --split pilot \
  --out runs/protocol/navigation_v2_pilot_validation.json
"$PY" scripts/experiments/run_navigation.py runs/pilot/navigation_v2_positive.json \
  --model "$MODEL" --revision "$REVISION" --split pilot --cells positive --names "$NAMES" \
  --temperature 0 --seeds 1 --seed-start 0 --max-new 400 --max-turns 12 --max-reads 12 --gpu-only
"$PY" scripts/experiments/run_navigation.py runs/pilot/navigation_v2_span_control.json \
  --model "$MODEL" --revision "$REVISION" --split pilot --cells span-control --names "$NAMES" \
  --temperature 0 --seeds 1 --seed-start 0 --max-new 1000 --max-turns 12 --max-reads 12 --gpu-only
"$PY" scripts/experiments/run_navigation.py runs/pilot/navigation_v2_all.json \
  --model "$MODEL" --revision "$REVISION" --split pilot --cells all --names "$NAMES" \
  --temperature 0 --seeds 1 --seed-start 0 --max-new 1000 --max-turns 12 --max-reads 12 --gpu-only
