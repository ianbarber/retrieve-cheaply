# scripts/

The recipe + everything that produces a number in `PAPER.md`. (Superseded
era-1 scripts — the multi-file suites, isolation probes, old SFT pipeline,
real-repo pilot — were removed in the 2026-06-24 cleanup; see `log.md` / git
history if you need them.)

## Task suites
- `synth_tasks_effic.py` — the definition-sufficient efficiency suite (prefer a
  cheap `<defn>` over reading a big lib). The headline suite.
- `synth_tasks_efficread.py` — the read-required boundary tasks (`<defn>`
  insufficient → must `<read>`); `effmix` = effic + efficread.
- `synth_tasks_effic_nodel.py` — the no-delegation coverage probe (honest-open;
  floors the 7B, see `log.md` 2026-06-24).
- `synth_tasks.py` — the original single-file 14-task suite; still imported by
  `analysis/stats.py` for the §6.2 SFT held-out numbers.

## Core recipe
- `synth_mf.py` — the condition runner (rollouts / harvest / retest).
  `--suite {effic,efficread,effmix,effic_nodel}`.
- `sft_lora.py` — the on-policy LoRA-SFT trainer (the relabel — the headline step).
- `grpo_cost.py` — the cost-reward GRPO trainer (the independent corroboration).
- `validate_pyrefly_lsp.py` — validates `<defn>` against a live `pyrefly lsp` daemon.
- `analysis/stats.py` — **reproduce every recipe headline number**: `python scripts/analysis/stats.py`.
  Recomputes the full table (headline 3086→688, relabel-only, matched-outcome controls,
  real-LSP, boundary, GRPO, 27B) from the committed `runs/agent/*.json` and checks each
  against `PAPER.md`.
- `make_figures.py` — figures from the result JSONs.

## Headline runs (shell drivers)
- `run_relabel2.sh` — the on-policy relabel headline (harvest → SFT → retest, `--suite effic`).
- `run_real_lsp_headline.sh` — headline with the real go-to-definition resolver (`--suite effmix`).
- `run_lsp_headline.sh` — validation against the live pyrefly LSP daemon.
- `run_relabel2_27b.sh` — the Qwen3.6-27B scale-transfer run.
- `run_grpo.sh` — the multi-round cost-RL GRPO corroboration.
