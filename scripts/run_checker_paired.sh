#!/usr/bin/env bash
# Local-only checker calibration and paired revisions. No API calls.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
MODEL_7B="${MODEL_7B:-Qwen/Qwen2.5-Coder-7B-Instruct}"
MODEL_14B="${MODEL_14B:-Qwen/Qwen2.5-Coder-14B-Instruct}"
REVISION_7B="${REVISION_7B:-c03e6d358207e414f1eca0bb1891e29f1db0e242}"
REVISION_14B="${REVISION_14B:-aedcc2d42b622764e023cf882b6652e646b95671}"
NAMES_BASE="auth_shapes_protocol,auth_machine_enum,auth_graph_edges"
NAMES_EXT="auth_bank_dataclass,auth_multimap_generic,auth_tokenizer_namedtuple,auth_fold_callable,auth_pipeline_handler"

"$PY" scripts/experiments/checker_paired.py generate runs/pilot/checker_drafts_7b.json \
  --model "$MODEL_7B" --revision "$REVISION_7B" --names "$NAMES_BASE" --temperature 0.7 --seed 0 \
  --max-new 1400 --max-turns 12 --max-reads 6 --gpu-only
"$PY" scripts/experiments/checker_paired.py generate runs/pilot/checker_drafts_14b.json \
  --model "$MODEL_14B" --revision "$REVISION_14B" --names "$NAMES_BASE" --temperature 0.7 --seed 0 \
  --max-new 1400 --max-turns 12 --max-reads 6 --gpu-only
"$PY" scripts/experiments/checker_paired.py generate runs/pilot/checker_drafts_14b_ext.json \
  --model "$MODEL_14B" --revision "$REVISION_14B" --names "$NAMES_EXT" --temperature 0.7 --seed 1 \
  --max-new 1400 --max-turns 12 --max-reads 6 --gpu-only

set +e
"$PY" scripts/experiments/checker_paired.py calibrate runs/pilot/checker_drafts_7b.json \
  --minimum 0.2 --maximum 0.7 --min-coherent 2
gate_7b=$?
if [ "$gate_7b" -ne 0 ] && [ "$gate_7b" -ne 2 ]; then
  set -e
  echo "7B calibration failed operationally with exit $gate_7b" >&2
  exit "$gate_7b"
fi
"$PY" scripts/analysis/analyze_checker_calibration.py \
  runs/pilot/checker_drafts_14b.json runs/pilot/checker_drafts_14b_ext.json --enforce
gate_14b=$?
if [ "$gate_14b" -ne 0 ] && [ "$gate_14b" -ne 2 ]; then
  set -e
  echo "14B calibration failed operationally with exit $gate_14b" >&2
  exit "$gate_14b"
fi
set -e
if [ "$gate_7b" -eq 0 ] || [ "$gate_14b" -eq 0 ]; then
  echo "A calibration passed; freeze a paired-revision run specification before continuing." >&2
  exit 2
fi
echo "Both documented calibration regimes failed the opportunity gate; paired revisions remain blocked."
exit 2
