# runs/ -- committed result data

This directory contains result JSON used by `REPORT.md`. There are four evidence layers: the supported
controlled whole-file-read comparison, historical retrieval/dispatch follow-ups, checker/execution
ceilings, and new protocol/calibration artifacts. The old “types reframe” is no longer a final conclusion.

`python3 scripts/analysis/stats.py` reproduces the 7B efficiency-recipe numbers and prints `[MATCH]`
checks against `REPORT.md`. Other report numbers are produced by the targeted analyzers and by the
dispatch/authoring JSONs listed below.

## Efficiency Recipe: Whole-File-Read Baseline

These files support the controlled result that go-to-definition is cheaper when it replaces a whole-file
read and the agent elects it.

| file(s) | report section | what it shows |
|---|---|---|
| `agent/reallsp_base.json` / `reallsp_sft.json` | §3.1 | defn-sufficient PRE->POST: 2%->100% `<defn>`, 3086->688 tokens, success 0.65->1.00 |
| `agent/effic_retest_base.json` / `relabel2_retest.json` | §3.1 | relabel method in isolation: 2%->100% `<defn>`, 3086->724 tokens |
| `agent/powered_retest_base{,_x}.json` / `powered_retest_sft{,_x}.json` | §3.1 | matched-outcome lead-`<defn>` pilot: 2108->675 tokens, success McNemar p=6.3e-14 |
| `agent/effic_readtrained_retest.json` vs `powered_retest_sft.json` | §3.1 | read-trained vs defn-trained at matched outcome: 3191->684 tokens, p=6.8e-4 |
| `agent/lsp_base.json` / `agent/lsp_sft.json` | §3.2 | live-first Pyrefly plus AST fallback: 0%->100% `<defn>`, 2894->689 tokens |
| `agent/reallsp_base.json` / `agent/reallsp_sft.json` (`group=="readreq"`) | §3.1 | non-degeneracy boundary: trained policy still reads when a read is required |
| `agent/grpo_retest.json`, `agent/grpo_harvest_0..4.json`, `agent/grpo_retest_round1.json` | §3.1 | cost-reward RL corroboration: clean retest 86% `<defn>`, 663 tokens, 100% solved |
| `agent/27b_base.json` / `agent/27b_retest.json` | §3.1 | 27B training-transfer check: 4058->726 tokens, 0.96->1.00 success |

The tool-value ablation at fixed capability uses:

| file(s) | report section | what it shows |
|---|---|---|
| `agent/er2_27b_base.json` / `agent/er2_27b_readonly.json` | §3.1 | 27B with `<defn>` vs read-only on obscure real-code suite: 1302 vs 4563 tokens |
| `agent/fr_sonnet45_withdefn.json` / `agent/fr_sonnet45_readonly.json` | §3.1 | Sonnet tool-calling ablation: 6018 vs 21985 prompt tokens |
| `agent/fr_deepseek_withdefn.json` / `agent/fr_deepseek_readonly.json` | §3.1 | DeepSeek tool-calling ablation: 7705 vs 36192 prompt tokens |

## Historical Retrieval and Dispatch

These files show that the historical dispatch tool was near token-neutral in a prompt that exposed
concrete receiver information. They do not establish equivalence or a typed-versus-erased effect.

Run `python3 scripts/analysis/analyze_dispatch.py` from the repo root to summarize these files.

| file(s) | report section | what it shows |
|---|---|---|
| `realbench/dispatch/local_Qwen3.6-27B.json` | §3.3 | mixed grep/neutral/framed goto rows; annotated 27B cells solve 15/15, 14/15, and 15/15 |
| `realbench/dispatch/local_Qwen3.6-27B_stripped.json` | §3.3 | receiver type moved from call-site annotation to test construction; grep-base cost stays flat |
| `realbench/dispatch/local_Qwen3.6-27B_indirection.json` | §3.3 | receiver type behind return-annotated factory; goto resolves, but remains token-neutral |
| `realbench/dispatch/local_Qwen2.5-Coder-7B-Instruct.json` | §3.3 | weak model remains edit-bound; forcing goto does not produce a reliable benefit |
| `realbench/candidates.json`, `realbench/dispatch_candidates.json` | §4.3 | SWE-bench candidate scans and ambiguity evidence used for reconnaissance |

The mini-swe-agent in-the-wild probe is summarized in `docs/real_repo_progress.md`; its larger logs are
not all committed here.

## Static Information and Authoring

| file(s) | report section | what it shows |
|---|---|---|
| `agent/gd2_*_nocheck.json` | §3.4 | hinted no-checker inference arm; both frontier models solve 18/18 |
| `agent/gd2_*_withcheck.json` | §3.4 | hinted elective-checker inference arm; both solve 18/18 |
| `agent/gd2_*_realistic.json` | §3.4 | unhinted no-checker arm, despite the filename; both solve 18/18 |
| `agent/exp2_27b_{none,check,feedback}.json` | §3.4 | historical unavailable/elective/after-every-edit arms: 27B solves 12/12 each |
| `agent/exp2_7b_{none,check,feedback}.json` | §3.4 | historical unpaired arms: 6/12, 3/12, 4/12 held-out; original residual counts are contaminated |

Run `python3 scripts/analysis/analyze_authoring.py` from the repo root to summarize the authoring files.

## New protocol artifacts

| file | meaning |
|---|---|
| `protocol/navigation_pilot_validation.json` | historical v1 mechanical artifact; superseded because its typed contract was unsound |
| `protocol/navigation_apparatus_validation_v0.json` | preserved pre-freeze validation of the 12 instances later designated apparatus-audit only |
| `protocol/navigation_apparatus_validation.json` | historical v1 apparatus artifact; superseded |
| `protocol/navigation_confirmation_validation.json` | historical v1 reserved-split artifact; never used for a model run |
| `protocol/navigation_v2_pilot_validation.json` | four sound-stub pilot instances pass all-key runtime, type, widening, leakage, and live-LSP gates |
| `protocol/navigation_v2_apparatus_validation.json` | twelve repaired apparatus-audit instances; not confirmation |
| `protocol/navigation_v2_confirmation_validation.json` | twelve reserved v2 instances and frozen source hashes; no model outcome |
| `protocol/checker_natural_drafts_legacy_7b.json` | five exact historical final workspaces; two coherent and both checker-positive |
| `pilot/checker_drafts_7b_smoke.json` | pre-protocol partial-edit smoke; incoherent with 14 syntax/partial diagnostics |
| `pilot/navigation_positive_invalid_v0.json` | rejected one-row control run: the apparatus accidentally supplied the buggy rather than gold method body |
| `pilot/navigation_positive_floor_failed_v1.json` | excluded two-row pilot: corrected control passed 1/2 because one trajectory ignored supplied context |
| `pilot/navigation_positive.json` | v1 edit-only 7B control: 2/2, retained with the invalidated v1 apparatus |
| `pilot/navigation_all.json` | invalidated v1 7B matrix: unsound gold-derived typed contract; outcome/token claims excluded |
| `pilot/checker_drafts_7b.json` | current-protocol calibration: 3/3 submitted, 0/3 coherent; revisions blocked |
| `pilot/checker_drafts_14b.json` | current-protocol calibration: 1/3 coherent and type-clean; revisions blocked |
| `pilot/checker_drafts_14b_ext.json` | five-task extension: 1/5 coherent and type-clean; combined 14B opportunity remains 0/2 |

Model confirmation outcome files do not exist. Their absence is intentional and is reported as open work,
not filled from pilot or log summaries.

## Runtime Boundary

`scripts/analyze_runtime.py` aggregates both the base runtime files and the semantic-trap extension:

| file pattern | report section | what it shows |
|---|---|---|
| `agent/rt_{deepseek,sonnet45}_r0_notest.json` and `*_r0_trap.json` | §3.5 | no execution-feedback arm |
| `agent/rt_{deepseek,sonnet45}_r1_run.json` and `*_r1_trap.json` | §3.5 | elective execution arm |
| `agent/rt_{deepseek,sonnet45}_r2_auto.json` and `*_r2_trap.json` | §3.5 | volunteered execution-feedback arm |

`runs/sft/` holds trained LoRA adapters and is git-ignored.
