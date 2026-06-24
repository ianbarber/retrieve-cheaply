#!/usr/bin/env bash
# Cost-reward GRPO outer loop (7B, the 9 defn-sufficient efficiency train tasks).
# Each round: (a) sample G rollouts/task at temperature with synth_mf.py --save-sft (current adapter if r>1),
#             (b) grpo_cost.py computes reward+group-advantage and does K advantage-weighted PG steps,
#                 producing/continuing the LoRA runs/sft/effic_lora_grpo,
#             (c) the next round resamples WITH that adapter.
# Round 0 = the WILD 7B (no adapter) baseline harvest, so we can see in_tokens DROP across rounds.
# Watch across rounds: mean reward UP, mean in_tokens DOWN, %resolved (stay/up), %use-defn UP.
# Mirrors run_relabel2.sh's harvest->train->resample shell pattern (idempotent: skips finished artifacts).
set -u
cd /home/ianbarber/Projects/Streams
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/mnt/nas/hf-cache
PY=.venv-streams.system/bin/python
M="Qwen/Qwen2.5-Coder-7B-Instruct"
ADAPTER="runs/sft/effic_lora_grpo"

# the 9 definition-sufficient efficiency TRAIN tasks (same set as run_relabel2.sh)
DEFN_TRAIN="effic_account_defn,effic_transfer_defn,effic_span_defn,effic_store_defn,effic_point_defn,effic_config_defn,effic_matrix_defn,effic_lexer_defn,effic_color_defn"

# rollout config: cond A + the LSP tools advertised (the efficiency lever), temperature for a real group.
COMMON="--suite effic --model $M --gpu-only --conds A --lsp-tools --temp 0.7 --max-reads 4 --max-turns 14 --max-new 3000 --save-sft"

# GRPO hyperparameters
N=4          # rounds
G=8          # rollouts per task (the group size -> seeds)
K=4          # PG steps per round
LAMBDA=0.5   # token-cost weight in the reward
LR=1e-5

mkdir -p runs/agent runs/sft

# helper: quick per-harvest summary (mean reward / mean in_tokens / %resolved / %use-defn) via the CPU math path
summarize () {
  local H="$1"
  $PY scripts/grpo_cost.py --dry-run-rewards "$H" --lambda $LAMBDA 2>/dev/null | sed -n '1,40p'
  $PY - "$H" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1])); rows = d["rows"]
rows = rows if isinstance(rows, list) else [r for c in rows for r in rows[c]]
n = len(rows); res = [r for r in rows if r.get("resolved")]
udefn = sum(1 for r in res if (r.get("n_lsp") or 0) > 0)
mit = sum(float(r.get("in_tokens",0) or 0) for r in rows)/max(n,1)
print(f"[summary] {sys.argv[1]}: n={n} resolved={len(res)}/{n} "
      f"mean_in_tokens={mit:.0f} use-defn(of resolved)={udefn}/{len(res)}")
PYEOF
}

# ---------- ROUND 0: wild 7B baseline (no adapter) ----------
H0=runs/agent/grpo_harvest_0.json
if [ ! -f "$H0" ]; then
  echo "[round0-harvest-start] wild 7B (no adapter)"
  $PY scripts/synth_mf.py "$H0" $COMMON --names "$DEFN_TRAIN" --force-lsp --relabel --seeds $G \
    && echo "[round0-harvest-done]" || { echo "[round0-harvest-FAIL]"; exit 1; }
else echo "[round0-harvest-skip]"; fi
echo "[round0-baseline]"; summarize "$H0"

# ---------- ROUNDS 1..N: sample with current adapter, then K PG steps ----------
for r in $(seq 1 $N); do
  H=runs/agent/grpo_harvest_${r}.json
  prev=$((r-1))
  # (a) sample G rollouts/task with the CURRENT adapter (round 1 samples with the wild model;
  #     the adapter only exists once round 1 has trained it, so round 1's harvest is still wild).
  ADAPTER_FLAG=""
  if [ "$r" -gt 1 ] && [ -d "$ADAPTER" ]; then ADAPTER_FLAG="--adapter $ADAPTER"; fi
  if [ ! -f "$H" ]; then
    echo "[round${r}-harvest-start] $ADAPTER_FLAG"
    $PY scripts/synth_mf.py "$H" $COMMON --names "$DEFN_TRAIN" --force-lsp --relabel --seeds $G $ADAPTER_FLAG \
      && echo "[round${r}-harvest-done]" || { echo "[round${r}-harvest-FAIL]"; exit 1; }
  else echo "[round${r}-harvest-skip]"; fi
  echo "[round${r}-pre-train-stats]"; summarize "$H"

  # (b) K advantage-weighted PG steps -> produce (r==1) or continue (r>1) the LoRA.
  INIT_FLAG=""
  if [ "$r" -gt 1 ] && [ -d "$ADAPTER" ]; then INIT_FLAG="--init-adapter $ADAPTER"; fi
  echo "[round${r}-train-start] $INIT_FLAG"
  $PY scripts/grpo_cost.py --harvest "$H" --model "$M" --out "$ADAPTER" $INIT_FLAG \
      --lambda $LAMBDA --steps $K --lr $LR \
    && echo "[round${r}-train-done]" || { echo "[round${r}-train-FAIL]"; exit 1; }
done

# ---------- final re-test with the trained adapter ----------
RETEST=runs/agent/grpo_retest.json
if [ ! -f "$RETEST" ]; then
  echo "[grpo-retest-start]"
  $PY scripts/synth_mf.py "$RETEST" $COMMON --names "$DEFN_TRAIN" --adapter "$ADAPTER" --seeds 4 \
    && echo "[grpo-retest-done]" || { echo "[grpo-retest-FAIL]"; exit 1; }
fi
echo "[grpo-retest-stats]"; summarize "$RETEST"
echo "[ALL-GRPO-DONE]"
