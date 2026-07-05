# runs/ -- committed result data

This directory contains the JSON result files that back `REPORT.md`. There are three layers of evidence:
the controlled whole-file-read efficiency recipe, the realistic retrieval/dispatch follow-ups that drive
the types reframe, and boundary tests for static information and execution feedback.

`python3 scripts/analysis/stats.py` reproduces the 7B efficiency-recipe numbers and prints `[MATCH]`
checks against `REPORT.md`. Other report numbers are produced by the targeted analyzers and by the
dispatch/authoring JSONs listed below.

## Efficiency Recipe: Whole-File-Read Baseline

These files support the controlled result that go-to-definition is cheaper when it replaces a whole-file
read and the agent elects it.

| file(s) | report section | what it shows |
|---|---|---|
| `agent/reallsp_base.json` / `reallsp_sft.json` | §4 | defn-sufficient PRE->POST: 2%->100% `<defn>`, 3086->688 tokens, success 0.65->1.00 |
| `agent/effic_retest_base.json` / `relabel2_retest.json` | §4 | relabel method in isolation: 2%->100% `<defn>`, 3086->724 tokens |
| `agent/powered_retest_base{,_x}.json` / `powered_retest_sft{,_x}.json` | §4 | matched-outcome lead-`<defn>` pilot: 2108->675 tokens, success McNemar p=6.3e-14 |
| `agent/effic_readtrained_retest.json` vs `powered_retest_sft.json` | §3 | read-trained vs defn-trained at matched outcome: 3191->684 tokens, p=6.8e-4 |
| `agent/lsp_base.json` / `agent/lsp_sft.json` | §2 | live `pyrefly lsp` daemon validation: 0%->100% `<defn>`, 2894->689 tokens |
| `agent/reallsp_base.json` / `agent/reallsp_sft.json` (`group=="readreq"`) | §4 | non-degeneracy boundary: trained policy still reads when a read is required |
| `agent/grpo_retest.json`, `agent/grpo_harvest_0..4.json`, `agent/grpo_retest_round1.json` | Appendix A | cost-reward RL corroboration: clean retest 86% `<defn>`, 663 tokens, 100% solved |
| `agent/27b_base.json` / `agent/27b_retest.json` | Appendix B | 27B training-transfer check: 4058->726 tokens, 0.96->1.00 success |

The tool-value ablation at fixed capability uses:

| file(s) | report section | what it shows |
|---|---|---|
| `agent/er2_27b_base.json` / `agent/er2_27b_readonly.json` | §3 | 27B with `<defn>` vs read-only on obscure real-code suite: 1302 vs 4563 tokens |
| `agent/fr_sonnet45_withdefn.json` / `agent/fr_sonnet45_readonly.json` | §3 | sonnet tool-calling ablation: 6018 vs 21985 prompt tokens |
| `agent/fr_deepseek_withdefn.json` / `agent/fr_deepseek_readonly.json` | §3 | deepseek tool-calling ablation: 7705 vs 36192 prompt tokens |

## Types Reframe: Realistic Retrieval and Dispatch

These files support the later finding that the efficiency result is scoped to whole-file reads, and that
semantic goto is redundant when the relevant type is readable.

Run `python3 scripts/analysis/analyze_dispatch.py` from the repo root to summarize these files.

| file(s) | report section | what it shows |
|---|---|---|
| `realbench/dispatch/local_Qwen3.6-27B.json` | §3.5 | 15-task dispatch suite, annotated receiver type: 27B solves 15/15, grep-vs-goto token ratio near 1 |
| `realbench/dispatch/local_Qwen3.6-27B_stripped.json` | §3.5 | receiver type moved from call-site annotation to test construction; grep-base cost stays flat |
| `realbench/dispatch/local_Qwen3.6-27B_indirection.json` | §3.5 | receiver type behind return-annotated factory; goto resolves, but remains token-neutral |
| `realbench/dispatch/local_Qwen2.5-Coder-7B-Instruct.json` | §3.5 | weak model remains edit-bound; forcing goto does not produce a reliable benefit |
| `realbench/candidates.json`, `realbench/dispatch_candidates.json` | §3.4-§3.5 | SWE-bench candidate scans and ambiguity evidence used to build the real-repo probes |

The mini-swe-agent in-the-wild probe is summarized in `docs/real_repo_progress.md`; its larger logs are
not all committed here.

## Static Information and Authoring

| file(s) | report section | what it shows |
|---|---|---|
| `agent/gd2_*_{realistic,nocheck,withcheck}.json` | §5 | held-out type-inference tasks: both frontier models solve 18/18 with and without `check_types()` |
| `agent/exp2_27b_{none,check,feedback}.json` | §5 | authoring suite: 27B solves 12/12 and is essentially type-clean without checker help |
| `agent/exp2_7b_{none,check,feedback}.json` | §5 | authoring suite: 7B is worse with checker access/feedback; residual type errors stay flat |

Run `python3 scripts/analysis/analyze_authoring.py` from the repo root to summarize the authoring files.

## Runtime Boundary

`scripts/analyze_runtime.py` aggregates both the base runtime files and the semantic-trap extension:

| file pattern | report section | what it shows |
|---|---|---|
| `agent/rt_{deepseek,sonnet45}_r0_notest.json` and `*_r0_trap.json` | §5 | no execution-feedback arm |
| `agent/rt_{deepseek,sonnet45}_r1_run.json` and `*_r1_trap.json` | §5 | elective execution arm |
| `agent/rt_{deepseek,sonnet45}_r2_auto.json` and `*_r2_trap.json` | §5 | volunteered execution-feedback arm |

`runs/sft/` holds trained LoRA adapters and is git-ignored.
