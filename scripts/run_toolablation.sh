#!/usr/bin/env bash
# TOOL-VALUE ABLATION (Gap A): does HAVING the <defn> tool buy anything vs read-only, at MATCHED capability
# and WITHOUT training? This is the contrast the project never ran for the efficiency channel — every prior
# comparison was base-vs-trained (both have the tool). Here we hold the model fixed and toggle the tool.
#   WITH tool  = existing runs/agent/er2_base.json (7B) and er2_27b_base.json (27B)  [--lsp-tools, defn available]
#   WITHOUT    = these read-only runs [--no-defn: <defn>/<findrefs> genuinely unavailable, stripped from prompt]
# Suite = effic_real2 (obscure, retrieval genuinely required). Same model/seeds/caps as the with-tool runs.
# Tells us: for a model that elects <defn> for free (27B), does the tool actually save tokens / lift success?
set -u
cd /home/ianbarber/Projects/Streams
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/mnt/nas/hf-cache
PY=.venv-streams.system/bin/python
RO="--suite effic_real2 --gpu-only --conds A --no-defn --temp 0.7 --max-reads 4 --max-turns 14 --max-new 3000"
pkill -9 -f "[p]yrefly" 2>/dev/null

# 7B read-only (4 seeds, matches er2_base.json)
if [ ! -f runs/agent/er2_7b_readonly.json ]; then
  echo "[7b-ro-start $(date +%T)]"
  $PY scripts/synth_mf.py runs/agent/er2_7b_readonly.json $RO --model "Qwen/Qwen2.5-Coder-7B-Instruct" --seeds 4 \
    && echo "[7b-ro-done $(date +%T)]" || { echo "[7b-ro-FAIL]"; exit 1; }
else echo "[7b-ro-skip]"; fi

# 27B read-only (2 seeds, matches er2_27b_base.json) — the key arm
if [ ! -f runs/agent/er2_27b_readonly.json ]; then
  echo "[27b-ro-start $(date +%T)]"
  $PY scripts/synth_mf.py runs/agent/er2_27b_readonly.json $RO --model "Qwen/Qwen3.6-27B" --seeds 2 \
    && echo "[27b-ro-done $(date +%T)]" || { echo "[27b-ro-FAIL]"; exit 1; }
else echo "[27b-ro-skip]"; fi

echo "[ALL-TOOLABLATION-DONE $(date +%T)]"
