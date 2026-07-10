#!/usr/bin/env bash
# Historical workspace-resolver headline: PRE/POST on the mixed suite using the static AST definition
# resolver over live files. Despite this script's legacy filename, it is not a language-server run;
# `run_lsp_headline.sh` is the live-first Pyrefly variant. Four seeds; read-required boundary included.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
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
