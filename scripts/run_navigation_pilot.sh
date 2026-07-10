#!/usr/bin/env bash
# Local-only apparatus pilot. No API calls and no monetary spend.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
MODEL="${MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct}"
NAMES="${NAMES:-nav_pilot_17011,nav_pilot_17027}"

"$PY" scripts/experiments/navigation_tasks.py --split pilot \
  --out runs/protocol/navigation_pilot_validation.json
"$PY" scripts/experiments/run_navigation.py runs/pilot/navigation_positive.json \
  --model "$MODEL" --split pilot --cells positive --names "$NAMES" --gpu-only
"$PY" scripts/experiments/run_navigation.py runs/pilot/navigation_core.json \
  --model "$MODEL" --split pilot --cells core --names "$NAMES" --gpu-only
"$PY" scripts/experiments/run_navigation.py runs/pilot/navigation_deployment.json \
  --model "$MODEL" --split pilot --cells deployment --names "$NAMES" --gpu-only
