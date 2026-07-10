#!/usr/bin/env bash
# Gap D (information win) frontier test: does a pyrefly check_types() tool help a frontier model on
# INFERENCE-HARD tasks, over read+defn alone? Suite gapd, with-check vs without — the ONLY difference is
# whether the type-checker is available. If with-check >> without, the LSP's type INFERENCE is a
# non-redundant info channel; if ~equal, the model self-derives the types by reading (info redundant).
# Budget-capped per command. Resumable. (with-check uses pyrefly; run after the pyrefly-free effic_real2 run.)
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
SEEDS="${SEEDS:-2}"
GG="--suite gapd --seeds $SEEDS --max-reads 6 --max-turns 14 --temperature 0.7"
SPECS=(
  "deepseek/deepseek-chat-v3.1:deepseek:2"
  "anthropic/claude-sonnet-4.5:sonnet45:6"
)
for spec in "${SPECS[@]}"; do
  IFS=: read -r MODEL TAG BUD <<< "$spec"
  if [ ! -f runs/agent/gd_${TAG}_nocheck.json ]; then
    echo "[gd-$TAG-nocheck-start $(date +%T)]"
    $PY scripts/api_agent.py runs/agent/gd_${TAG}_nocheck.json $GG --model "$MODEL" --budget-usd "$BUD"
    echo "[gd-$TAG-nocheck-done exit $? $(date +%T)]"
  else echo "[gd-$TAG-nocheck-skip]"; fi
  if [ ! -f runs/agent/gd_${TAG}_withcheck.json ]; then
    echo "[gd-$TAG-withcheck-start $(date +%T)]"
    $PY scripts/api_agent.py runs/agent/gd_${TAG}_withcheck.json $GG --model "$MODEL" --with-check --budget-usd "$BUD"
    echo "[gd-$TAG-withcheck-done exit $? $(date +%T)]"
  else echo "[gd-$TAG-withcheck-skip]"; fi
done
echo "[ALL-GAPD-FRONTIER-DONE $(date +%T)]"
