#!/usr/bin/env bash
# Gap D FAIR inference test: does a check_types() tool reduce LATENT bugs a frontier model
# would otherwise ship? gapd2 uses held-out-path scoring — the agent runs a VISIBLE test (which
# the wrong fix passes) and we score on a HELD-OUT test (which the wrong fix fails). With vs
# without check_types; defn/read available in both, so the only difference is the type checker.
# `resolved` = held-out score; `visible_pass` = the test the agent could run. Needs OPENROUTER_API_KEY.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
SEEDS="${SEEDS:-2}"
GG="--suite gapd2 --seeds $SEEDS --max-reads 6 --max-turns 10 --temperature 0.7"
for spec in "deepseek/deepseek-chat-v3.1:deepseek:4" "anthropic/claude-sonnet-4.5:sonnet45:10"; do
  IFS=: read -r MODEL TAG BUD <<< "$spec"
  if [ ! -f runs/agent/gd2_${TAG}_nocheck.json ]; then
    echo "[gd2-$TAG-nocheck-start $(date +%T)]"
    $PY scripts/api_agent.py runs/agent/gd2_${TAG}_nocheck.json $GG --model "$MODEL" --budget-usd "$BUD"
    echo "[gd2-$TAG-nocheck-done exit $? $(date +%T)]"
  else echo "[gd2-$TAG-nocheck-skip]"; fi
  if [ ! -f runs/agent/gd2_${TAG}_withcheck.json ]; then
    echo "[gd2-$TAG-withcheck-start $(date +%T)]"
    $PY scripts/api_agent.py runs/agent/gd2_${TAG}_withcheck.json $GG --model "$MODEL" --with-check --budget-usd "$BUD"
    echo "[gd2-$TAG-withcheck-done exit $? $(date +%T)]"
  else echo "[gd2-$TAG-withcheck-skip]"; fi
done
echo "[ALL-GAPD2-DONE $(date +%T)]"
