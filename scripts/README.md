# scripts/

The recipe and everything that produces a number in `REPORT.md`. Journey-only scripts
(coverage-judging probes, no-delegation suite, old single-file suite, superseded drivers,
and the RefactorBench / real-repo runner that the report did not use) were removed in the
cleanup; see `log.md` / git history if you need them.

## Task suites
- `synth_tasks_effic.py` — synthetic definition-sufficient efficiency suite (prefer a cheap
  `<defn>` over reading a big lib). The training suite.
- `synth_tasks_efficread.py` — read-required boundary tasks (`<defn>` insufficient → must
  `<read>`); `effmix` = effic + efficread.
- `synth_tasks_effic_real{,2}.py` — real vendored-library suites (`effic_real_vendor/`):
  `effic_real` (familiar symbols), `effic_real2` (obscure, un-memorized symbols).
- `synth_tasks_gapd.py`, `synth_tasks_gapd2.py` — type-inference tasks for the information
  channel; `gapd2` adds held-out scoring so a `check_types()` tool can be the unique detector.
- `synth_tasks_runtime.py` — the execution-feedback boundary suite (structural, easy, and
  Python-semantic-trap tiers; held-out scored, well-typed so the only detector is execution).
- `realbench/dispatch_tasks.py` — dispatch-ambiguity suite used to test whether semantic goto beats
  grep/ranged reads when many classes define the same method.
- `synth_tasks_authoring.py` — typed authoring suite used to test whether live checker diagnostics help
  while writing new code.

## Core recipe
- `synth_mf.py` — local condition runner (rollouts / harvest / retest).
  `--suite {effic,effic_real,effic_real2,gapd,efficread,effmix,authoring}`, `--no-defn` (tool ablation),
  `--adapter` (trained policy), and `--arm {none,check,feedback}` for authoring.
- `api_agent.py` — OpenRouter tool-calling harness: test any frontier model in the deployment
  modality (`--no-defn`, `--with-check`, `--no-test` / `--auto-feedback`, hard `--budget-usd` cap).
- `realbench/local_dispatch.py` — local dispatch runner with `grep_base`, `defn_avail`, and
  `defn_prompt` conditions plus the `annotated` / `stripped` / `indirection` typing ladder.
- `sft_lora.py` — the on-policy LoRA-SFT trainer (the relabel, the headline training step).
- `grpo_cost.py` — cost-reward GRPO trainer (independent corroboration, Appendix A).
- `validate_pyrefly_lsp.py` — validates `<defn>` against a live `pyrefly lsp` daemon.
- `analysis/stats.py` — **reproduce the 7B training numbers**: recomputes the table from the
  committed `runs/agent/*.json` and checks each against `REPORT.md`.
- `analysis/effic_real_stats.py` — paired stats for the real-code and tool-ablation runs.
- `analysis/analyze_dispatch.py` — summarizes the dispatch/goto runs and paired grep-vs-goto token
  ratios that support the types reframe.
- `analysis/analyze_authoring.py` — summarizes the authoring/checker arms and residual diagnostics.
- `analyze_runtime.py` — the execution-feedback matrix analysis, including the semantic-trap extension
  files (`*_trap.json`).
- `make_figures.py` — all six figures from the result JSONs.

## Shell drivers
- `run_relabel2.sh` — on-policy relabel training headline (harvest → SFT → retest), report §4.
- `run_relabel2_27b.sh` — Qwen3.6-27B scale-transfer, Appendix B.
- `run_toolablation.sh` — tool-value ablation (with-`defn` vs read-only), report §3.
- `run_effic_real.sh` — real-code transfer / un-memorized suites, report §3.
- `run_frontier.sh` — frontier election + efficiency via OpenRouter, report §3–4.
- `run_seeds_ext.sh` — seed extension for the 27B + frontier efficiency runs.
- `run_gapd_frontier.sh`, `run_gapd2_frontier.sh` — type-inference channel (gapd2 = fair held-out test), §5.
- `run_runtime_frontier.sh` — the execution-feedback boundary test (no-run / run / handed-over), §5.
- `run_real_lsp_headline.sh` / `run_lsp_headline.sh` — live `pyrefly lsp` daemon validation, §2.
- `run_grpo.sh` — multi-round cost-RL GRPO corroboration, Appendix A.
