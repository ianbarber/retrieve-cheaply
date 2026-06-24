#!/usr/bin/env bash
# ITEM 3 PROPER RUN — the cheap <defn> action driven by a LIVE pyrefly LSP daemon (validated 12/12 ==
# the AST resolver). Scoped (12 defn-sufficient effic tasks, 2 seeds) because each <defn> spawns+kills a
# pyrefly daemon (~1-2s) and the daemon must stay STRICTLY SEQUENTIAL (deadlock gotcha). Confirms the
# headline reproduces when the cheap retrieval is a real language-server call (not the static resolver).
set -u
cd /home/ianbarber/Projects/Streams
pkill -9 -f pyrefly 2>/dev/null || true
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/mnt/nas/hf-cache
PY=.venv-streams.system/bin/python
M="Qwen/Qwen2.5-Coder-7B-Instruct"
COMMON="--suite effic --model $M --gpu-only --conds A --lsp-tools --lsp-defn --temp 0.7 --max-reads 4 --max-turns 14 --max-new 3000 --seeds 2"

if [ ! -f runs/agent/lsp_base.json ]; then
  echo "[lsp-base-start]"; $PY scripts/synth_mf.py runs/agent/lsp_base.json $COMMON \
    && echo "[lsp-base-done]" || { echo "[lsp-base-FAIL]"; exit 1; }
else echo "[lsp-base-skip]"; fi
pkill -9 -f pyrefly 2>/dev/null || true

if [ ! -f runs/agent/lsp_sft.json ]; then
  echo "[lsp-sft-start]"; $PY scripts/synth_mf.py runs/agent/lsp_sft.json $COMMON --adapter runs/sft/effic_lora_powered \
    && echo "[lsp-sft-done]" || { echo "[lsp-sft-FAIL]"; exit 1; }
else echo "[lsp-sft-skip]"; fi
pkill -9 -f pyrefly 2>/dev/null || true
echo "[ALL-LSP-DONE]"
