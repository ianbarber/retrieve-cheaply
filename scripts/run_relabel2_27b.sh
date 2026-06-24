#!/usr/bin/env bash
# ITEM 2 — SCALE CHECK: does the genuine on-policy relabel instill the cheap-retrieval preference at 27B?
# Qwen3.6-27B (qwen3_5, hybrid-reasoning <think>; default config). Lighter seeds than the 7B headline since
# this is a robustness/scale check and the 27B is ~3-4x slower. PRE baseline (no adapter) + relabel harvest
# + LoRA SFT + POST retest, all on the 12 definition-sufficient effic tasks.
set -u
cd /home/ianbarber/Projects/Streams
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/mnt/nas/hf-cache
PY=.venv-streams.system/bin/python
M="Qwen/Qwen3.6-27B"
DEFN_TRAIN="effic_account_defn,effic_transfer_defn,effic_span_defn,effic_store_defn,effic_point_defn,effic_config_defn,effic_matrix_defn,effic_lexer_defn,effic_color_defn"
COMMON="--suite effic --model $M --gpu-only --conds A --lsp-tools --temp 0.7 --max-reads 4 --max-turns 14 --max-new 3000"

# PRE baseline: wild 27B (no adapter), 12 defn tasks, 2 seeds — expect %defn~0 (reads by default).
if [ ! -f runs/agent/27b_base.json ]; then
  echo "[27b-base-start]"; $PY scripts/synth_mf.py runs/agent/27b_base.json $COMMON --seeds 2 \
    && echo "[27b-base-done]" || { echo "[27b-base-FAIL]"; exit 1; }
else echo "[27b-base-skip]"; fi

# Relabel harvest: force-lsp + relabel (model's own <defn>, drop prefix), 9 defn tasks, 4 seeds.
if [ ! -f runs/agent/27b_harvest.json ]; then
  echo "[27b-harvest-start]"; $PY scripts/synth_mf.py runs/agent/27b_harvest.json $COMMON --names "$DEFN_TRAIN" \
      --force-lsp --relabel --save-sft --seeds 4 \
    && echo "[27b-harvest-done]" || { echo "[27b-harvest-FAIL]"; exit 1; }
else echo "[27b-harvest-skip]"; fi

# LoRA SFT on the harvested clean teacher trajectories.
if [ ! -d runs/sft/effic_lora_relabel2_27b ]; then
  echo "[27b-sft-start]"; $PY scripts/sft_lora.py --harvest runs/agent/27b_harvest.json --model "$M" \
      --out runs/sft/effic_lora_relabel2_27b --epochs 3 --lr 1e-4 \
    && echo "[27b-sft-done]" || { echo "[27b-sft-FAIL]"; exit 1; }
else echo "[27b-sft-skip]"; fi

# POST retest: trained 27B, 12 defn tasks, 2 seeds.
if [ ! -f runs/agent/27b_retest.json ]; then
  echo "[27b-retest-start]"; $PY scripts/synth_mf.py runs/agent/27b_retest.json $COMMON \
      --adapter runs/sft/effic_lora_relabel2_27b --seeds 2 \
    && echo "[27b-retest-done]" || { echo "[27b-retest-FAIL]"; exit 1; }
else echo "[27b-retest-skip]"; fi
echo "[ALL-27B-DONE]"
