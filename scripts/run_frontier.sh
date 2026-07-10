#!/usr/bin/env bash
# Frontier API validation (tool-calling modality): does a frontier model elect <defn> and is the
# efficiency win present? effic_real2 with-defn vs read-only (--no-defn), via OpenRouter. Budget-capped
# per command. Resumable (skip existing outputs). pyrefly-free (api_agent skips pyrefly w/o --with-check).
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
SEEDS="${SEEDS:-2}"
RR="--suite effic_real2 --seeds $SEEDS --max-reads 6 --max-turns 14 --temperature 0.7"
# model : tag : withdefn-budget$ : readonly-budget$   (read-only is the cost driver — it reads big files)
SPECS=(
  "deepseek/deepseek-chat-v3.1:deepseek:1:3"
  "anthropic/claude-sonnet-4.5:sonnet45:3:12"
)
for spec in "${SPECS[@]}"; do
  IFS=: read -r MODEL TAG WDB ROB <<< "$spec"
  if [ ! -f runs/agent/fr_${TAG}_withdefn.json ]; then
    echo "[fr-$TAG-wd-start $(date +%T)]"
    $PY scripts/api_agent.py runs/agent/fr_${TAG}_withdefn.json $RR --model "$MODEL" --budget-usd "$WDB"
    echo "[fr-$TAG-wd-done exit $? $(date +%T)]"
  else echo "[fr-$TAG-wd-skip]"; fi
  if [ ! -f runs/agent/fr_${TAG}_readonly.json ]; then
    echo "[fr-$TAG-ro-start $(date +%T)]"
    $PY scripts/api_agent.py runs/agent/fr_${TAG}_readonly.json $RR --model "$MODEL" --no-defn --budget-usd "$ROB"
    echo "[fr-$TAG-ro-done exit $? $(date +%T)]"
  else echo "[fr-$TAG-ro-skip]"; fi
done
echo "[ALL-FRONTIER-DONE $(date +%T)]"
