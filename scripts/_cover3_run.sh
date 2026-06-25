#!/usr/bin/env bash
# Form-keying control: the cost-trained 27B on cover3 (adds the _sufx adversarial variant).
# Discriminator = read(sufx): ~read(suf) => content-judging; ~read(insuff) => form-keying.
set -u
cd /home/ianbarber/Projects/Streams
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/mnt/nas/hf-cache
PY=.venv-streams.system/bin/python
M="Qwen/Qwen3.6-27B"
pkill -9 -x pyrefly 2>/dev/null || true
echo "[verify-start]"; $PY scripts/synth_tasks_cover3.py 2>&1 | tail -2; echo "[verify-done]"
pkill -9 -x pyrefly 2>/dev/null || true
echo "[cover3-sft-start]"
$PY scripts/synth_mf.py runs/agent/cover3_sft.json --suite cover3 --model "$M" --gpu-only \
  --conds A --lsp-tools --adapter runs/sft/effic_lora_relabel2_27b --temp 0.7 --max-reads 4 --max-turns 12 --seeds 3 \
  && echo "[cover3-sft-done]" || { echo "[cover3-sft-FAIL]"; exit 1; }
echo "[COVER3-DONE]"
$PY scripts/analysis/coverage_j.py trained=runs/agent/cover3_sft.json
