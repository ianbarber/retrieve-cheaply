#!/usr/bin/env bash
# PROPER DAgger test (fixed relabel): the model rolls out, chooses to <read>, the rule oracle redirects it to the
# cost-dominant <defn> which the MODEL picks itself; we DROP the read-attempt+redirect prefix so its own <defn> is the
# first trained action from the CLEAN prompt (the fix for the masked-prefix variant that left read+redirect in context).
# harvest (9 defn-sufficient train tasks) -> SFT effic_lora_relabel2 -> retest 12 defn-sufficient.
# Compare %use-defn: broken-relabel ~0% (masked) vs THIS (dropped) vs lead-defn ~100% (teacher-forced).
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
M="Qwen/Qwen2.5-Coder-7B-Instruct"
DEFN_TRAIN="effic_account_defn,effic_transfer_defn,effic_span_defn,effic_store_defn,effic_point_defn,effic_config_defn,effic_matrix_defn,effic_lexer_defn,effic_color_defn"
COMMON="--suite effic --model $M --gpu-only --conds A --lsp-tools --temp 0.7 --max-reads 4 --max-turns 14 --max-new 3000"
if [ ! -f runs/agent/relabel2_harvest.json ]; then
  echo "[r2-harvest-start]"
  $PY scripts/synth_mf.py runs/agent/relabel2_harvest.json $COMMON --names "$DEFN_TRAIN" --force-lsp --relabel --save-sft --seeds 8 \
    && echo "[r2-harvest-done]" || { echo "[r2-harvest-FAIL]"; exit 1; }
else echo "[r2-harvest-skip]"; fi
if [ ! -d runs/sft/effic_lora_relabel2 ]; then
  echo "[r2-sft-start]"
  $PY scripts/sft_lora.py --harvest runs/agent/relabel2_harvest.json --model "$M" --out runs/sft/effic_lora_relabel2 --epochs 3 --lr 1e-4 \
    && echo "[r2-sft-done]" || { echo "[r2-sft-FAIL]"; exit 1; }
else echo "[r2-sft-skip]"; fi
if [ ! -f runs/agent/relabel2_retest.json ]; then
  echo "[r2-retest-start]"
  $PY scripts/synth_mf.py runs/agent/relabel2_retest.json $COMMON --adapter runs/sft/effic_lora_relabel2 --seeds 4 \
    && echo "[r2-retest-done]" || { echo "[r2-retest-FAIL]"; exit 1; }
else echo "[r2-retest-skip]"; fi
echo "[ALL-RELABEL2-DONE]"
