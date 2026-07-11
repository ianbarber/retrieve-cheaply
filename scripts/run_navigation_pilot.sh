#!/usr/bin/env bash
# Local-only apparatus pilot. No API calls and no monetary spend.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
MODEL="${MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct}"
REVISION="${REVISION:-c03e6d358207e414f1eca0bb1891e29f1db0e242}"
NAMES="${NAMES:-nav_pilot_17011,nav_pilot_17027}"
RUN_ID="${RUN_ID:?set RUN_ID to a model/run tag, for example qwen25coder14b}"
if [[ ! "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "RUN_ID may contain only letters, digits, dot, underscore, and hyphen" >&2
  exit 64
fi
OUT_PREFIX="runs/pilot/navigation_v2_${RUN_ID}"
for out in "${OUT_PREFIX}_positive.json" "${OUT_PREFIX}_span_control.json" "${OUT_PREFIX}_all.json"; do
  if [ -e "$out" ]; then
    echo "refusing to overwrite navigation pilot output: $out" >&2
    exit 2
  fi
done

"$PY" scripts/experiments/navigation_tasks.py --split pilot \
  --out runs/protocol/navigation_v2_pilot_validation.json
"$PY" scripts/experiments/run_navigation.py "${OUT_PREFIX}_positive.json" \
  --model "$MODEL" --revision "$REVISION" --split pilot --cells positive --names "$NAMES" \
  --temperature 0 --seeds 1 --seed-start 0 --max-new 400 --max-turns 12 --max-reads 12 --gpu-only
"$PY" scripts/experiments/run_navigation.py "${OUT_PREFIX}_span_control.json" \
  --model "$MODEL" --revision "$REVISION" --split pilot --cells span-control --names "$NAMES" \
  --temperature 0 --seeds 1 --seed-start 0 --max-new 1000 --max-turns 12 --max-reads 12 --gpu-only
"$PY" scripts/experiments/run_navigation.py "${OUT_PREFIX}_all.json" \
  --model "$MODEL" --revision "$REVISION" --split pilot --cells all --names "$NAMES" \
  --temperature 0 --seeds 1 --seed-start 0 --max-new 1000 --max-turns 12 --max-reads 12 --gpu-only
