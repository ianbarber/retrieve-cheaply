#!/usr/bin/env bash
# effic-real ZERO-SHOT TRANSFER eval.
# Question: does the synthetic-trained cheap-<defn> preference (effic_lora_powered) generalize to
# REAL library code? We run base 7B vs the trained adapter on the 13 effic_real tasks (vendored
# toolz + more_itertools), condition A, lsp-tools available. SAME caps as the synthetic headline
# (run_relabel2.sh) so the token comparison is apples-to-apples. Trained first (fast: ~<100 out
# tokens/solve), then base (slow: reads the big file, long generations). Resumable: existing
# output jsons are skipped. Sequential only (pyrefly-init shares a daemon socket).
set -u
cd /home/ianbarber/Projects/Streams
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/mnt/nas/hf-cache
PY=.venv-streams.system/bin/python
M="${MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct}"
ADAPTER="${ADAPTER:-runs/sft/effic_lora_powered}"
SEEDS="${SEEDS:-4}"
SUITE="${SUITE:-effic_real}"          # effic_real (famous, base-guessable) | effic_real2 (obscure, un-memorized)
PREFIX="${PREFIX:-er}"                # output basename: ${PREFIX}_trained.json / ${PREFIX}_base.json
COMMON="--suite $SUITE --model $M --gpu-only --conds A --lsp-tools --temp 0.7 \
        --max-reads 4 --max-turns 14 --max-new 3000 --seeds $SEEDS"
pkill -9 -f "[p]yrefly" 2>/dev/null

if [ ! -f runs/agent/${PREFIX}_trained.json ]; then
  echo "[${PREFIX}-trained-start $(date +%T)]"
  $PY scripts/synth_mf.py runs/agent/${PREFIX}_trained.json $COMMON --adapter "$ADAPTER" \
    && echo "[${PREFIX}-trained-done $(date +%T)]" || { echo "[${PREFIX}-trained-FAIL]"; exit 1; }
else echo "[${PREFIX}-trained-skip]"; fi

if [ ! -f runs/agent/${PREFIX}_base.json ]; then
  echo "[${PREFIX}-base-start $(date +%T)]"
  $PY scripts/synth_mf.py runs/agent/${PREFIX}_base.json $COMMON \
    && echo "[${PREFIX}-base-done $(date +%T)]" || { echo "[${PREFIX}-base-FAIL]"; exit 1; }
else echo "[${PREFIX}-base-skip]"; fi

echo "[ALL-${PREFIX}-DONE $(date +%T)]"
