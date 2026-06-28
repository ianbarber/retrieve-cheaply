# scripts/

The recipe and everything that produces a number in `PAPER.md`. Journey-only scripts
(coverage-judging probes, no-delegation suite, old single-file suite, superseded drivers)
were removed in the cleanup; see `log.md` / git history if you need them.

## Task suites
- `synth_tasks_effic.py` — synthetic definition-sufficient efficiency suite (prefer a cheap
  `<defn>` over reading a big lib). The training suite.
- `synth_tasks_efficread.py` — read-required boundary tasks (`<defn>` insufficient → must
  `<read>`); `effmix` = effic + efficread.
- `synth_tasks_effic_real{,2}.py` — real vendored-library suites (`effic_real_vendor/`):
  `effic_real` (familiar symbols), `effic_real2` (obscure, un-memorized symbols).
- `synth_tasks_gapd.py` — type-inference tasks for the information channel (overload,
  generic, union, Protocol, TypedDict); pyrefly names the inferred type the test does not.

## Core recipe
- `synth_mf.py` — local condition runner (rollouts / harvest / retest).
  `--suite {effic,effic_real,effic_real2,gapd,efficread,effmix}`, `--no-defn` (tool ablation),
  `--adapter` (trained policy).
- `api_agent.py` — OpenRouter tool-calling harness: test any frontier model in the deployment
  modality (`--no-defn`, `--with-check`, hard `--budget-usd` cap).
- `real_mf.py` + `real_repo_loader.py` + `resolver_coverage_audit.py` — RealRepoEnv runner and
  the RefactorBench loader/audit (PAPER §6).
- `sft_lora.py` — the on-policy LoRA-SFT trainer (the relabel — the headline training step).
- `grpo_cost.py` — cost-reward GRPO trainer (independent corroboration, Appendix A).
- `validate_pyrefly_lsp.py` — validates `<defn>` against a live `pyrefly lsp` daemon.
- `analysis/stats.py` — **reproduce the 7B training numbers**: recomputes the table from the
  committed `runs/agent/*.json` and checks each against `PAPER.md`.
- `analysis/effic_real_stats.py` — paired stats for the real-code and tool-ablation runs.
- `make_figures.py` — figures from the result JSONs.

## Shell drivers
- `run_relabel2.sh` — on-policy relabel training headline (harvest → SFT → retest), PAPER §5.
- `run_toolablation.sh` — tool-value ablation (with-`defn` vs read-only), PAPER §4.
- `run_effic_real.sh` — real-code transfer / un-memorized suites, PAPER §6.
- `run_frontier.sh` — frontier election + efficiency via OpenRouter, PAPER §4–5.
- `run_gapd_frontier.sh` — type-inference information channel, PAPER §3.
- `run_relabel2_27b.sh` — Qwen3.6-27B scale-transfer, Appendix B.
- `run_real_lsp_headline.sh` / `run_lsp_headline.sh` — live `pyrefly lsp` daemon validation, §2.
- `run_grpo.sh` — multi-round cost-RL GRPO corroboration, Appendix A.
