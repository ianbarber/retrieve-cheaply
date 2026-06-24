#!/usr/bin/env bash
# THE genuine value-add headline: PRE (untrained) + POST (trained effic_lora_powered) on the full mixed suite (12
# defn-sufficient + 6 read-required), using the REAL go-to-definition resolver (no oracle; <defn> AST-resolves the
# symbol from the live workspace). Since the resolver returns content identical to the oracle (validated 12/12), this
# REPRODUCES the headline with a real tool — converting "we trained a preference for a magic cheap action" into
# "we made a real LSP value-add." 4 seeds each; the boundary (read-required) is included.
set -u
cd /home/ianbarber/Projects/Streams
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/mnt/nas/hf-cache
PY=.venv-streams.system/bin/python
M="Qwen/Qwen2.5-Coder-7B-Instruct"
COMMON="--suite effmix --model $M --gpu-only --conds A --lsp-tools --temp 0.7 --max-reads 4 --max-turns 14 --max-new 3000 --seeds 4"
if [ ! -f runs/agent/reallsp_base.json ]; then
  echo "[real-base-start]"; $PY scripts/synth_mf.py runs/agent/reallsp_base.json $COMMON \
    && echo "[real-base-done]" || { echo "[real-base-FAIL]"; exit 1; }
else echo "[real-base-skip]"; fi
if [ ! -f runs/agent/reallsp_sft.json ]; then
  echo "[real-sft-start]"; $PY scripts/synth_mf.py runs/agent/reallsp_sft.json $COMMON --adapter runs/sft/effic_lora_powered \
    && echo "[real-sft-done]" || { echo "[real-sft-FAIL]"; exit 1; }
else echo "[real-sft-skip]"; fi
echo "[ALL-REALLSP-DONE]"
