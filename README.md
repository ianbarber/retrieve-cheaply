# When Do Language Servers Help Coding Agents?

This repository studies a conditional engineering question rather than defending a universal LSP claim:

> When do semantic retrieval, readable/inferred types, checker feedback, and server-backed operations
> improve a coding agent after election, actionability, latency, and context costs are counted?

The working model is:

`opportunity × correctness/uniqueness × compression × election × actionability − cost`.

LSP is the transport; a language server is the semantic implementation; types are semantic substrate; a
type checker produces consistency diagnostics; and pull tools, pushed context, patch-boundary feedback,
gates, rerankers, constrained decoding, and training rewards are distinct integrations.

## Current findings

**Supported, narrow positive.** A compact definition result cuts pooled input tokens 3.5–4.7x at unchanged
success when the counterfactual is a whole-file library read. After averaging rollout seeds within task,
the treatment is cheaper on 11/11 local-27B tasks, 11/11 Sonnet tasks, and 10/11 DeepSeek tasks. Mean
per-task ratios are 4.02, 3.65, and 6.03; medians are 3.83, 3.01, and 2.70. Most of these runs use a static
AST resolver, so this supports compact retrieval, not LSP transport in general.

**Supported policy result.** Tool election is model- and policy-dependent. Prompting works in some
capable-model runs; on-policy relabeling and cost-reward training change a 7B model’s retrieval choice.
This is not evidence for a monotonic parameter-count law.

**Tentative negative regimes.** A historical dispatch suite shows near-one token ratios when a capable
agent can read the concrete receiver and open the target directly. The suite leaks that information and
has no erased-type arm, so it does not prove semantic navigation is redundant. Historical checker arms
compare unrelated first drafts, and their residual counts were contaminated by an in-workspace test file.
Corrected replay nevertheless finds checker-positive diagnostics in both coherent recoverable historical
workspaces. Execution/checker inference suites are at behavioral ceiling, but checker opportunity was not
measured there; neither fact establishes equivalence.

**New apparatus evidence.** The repaired `navigation-v2` typed/erased apparatus uses sound per-key `Literal`
overloads in `.pyi` files over byte-identical runtime code. It passes base/gold, held-out, all-key runtime
contract, type-cleanliness, leakage, widened-call, and strict live-Pyrefly checks on all four pilot instances and twelve additional
apparatus-audit instances. Those 12 are not confirmation because validator changes followed their first
inspection; a new disjoint 12-instance confirmation split passes mechanical checks and is reserved behind
source hashes without model exposure. The earlier 7B `navigation-v1` pilot used an unsound gold-derived
factory return and is retained only as invalid apparatus history. In v2, the gold-copy control passes 2/2,
but the identically framed pristine buggy-span actionability control fails 0/2. The gated driver therefore
does not run the causal matrix; no navigation treatment effect is claimed. Fresh checker calibration stops correctly: 7B produces 0/3 coherent
drafts, while 14B produces 2/8 and both are type-clean. Neither reaches the 20–70% opportunity band;
paired revisions and navigation confirmation remain unrun.

See [REPORT.md](REPORT.md) for the evidence, limitations, related work, and practitioner decision table;
[evidence/claim_ledger.md](evidence/claim_ledger.md) for claim-by-claim status; and
[evidence/protocols.md](evidence/protocols.md) for the frozen protocols and zero-paid-spend run budget.

## Fast reproduction

Python 3.10+ is required. Install the analysis/LSP development dependencies, then run the no-model
reproducer:

```bash
python3 -m pip install -e '.[dev,analysis]'
python3 scripts/analysis/reproduce_all.py
```

The command verifies `evidence/manifest.json`, reruns every analyzer retained in the report, recomputes
task-level effects, and reruns all navigation mechanical gates. It makes no model or API calls.
Pyrefly is discovered from `STREAMS_PYREFLY`, `PYREFLY_BIN`, PATH, `.venv/bin`, or
`.venv-streams/bin`.

Targeted commands:

```bash
python3 scripts/analysis/stats.py
python3 scripts/analysis/effic_real_stats.py \
  --base runs/agent/er2_27b_readonly.json \
  --trained runs/agent/er2_27b_base.json --label 27B
python3 scripts/analysis/task_level_effects.py \
  --base runs/agent/er2_27b_readonly.json \
  --treatment runs/agent/er2_27b_base.json --label 27B
python3 scripts/experiments/navigation_tasks.py --split pilot
```

## Expensive runs

No paid API run is authorized. The local pilots use cached 7B/14B models with a monetary cap of `$0`.
The navigation command writes new v2 artifacts and preserves invalidated v1 evidence; the checker command
exactly regenerates the three reported 1,400-token calibration batches:

```bash
PYTHON=python3 scripts/run_navigation_pilot.sh
PYTHON=python3 scripts/run_checker_paired.sh
```

The confirmation command is intentionally separate and runs only after the v2 gold-copy and buggy-span
controls and pilot clear the preregistered gates. It currently exits before model loading because the
buggy-span control failed and no causal matrix exists:

```bash
PYTHON=python3 scripts/run_navigation_confirmation.sh
```

Historical OpenRouter drivers still require `OPENROUTER_API_KEY` or `.orkey` and enforce their own
`--budget-usd` limits. Do not run them merely to reproduce the report; committed JSON is sufficient.

## Decision recipe

| condition | use | evidence confidence |
|---|---|---|
| Fact is visible, lexically unique, and cheap to read | grep plus ranged textual retrieval | tentative repository guidance (C6, C9) |
| Binding is ambiguous or remote; re-exports, overloads, factories, or inheritance defeat text | semantic pull navigation | mechanism supported; v2 agent benefit open (C15, C23) |
| Compact result can replace a large read | automatic or elected definition/method span | high but narrow against whole-file reads (C1) |
| Valuable automatic context is not elected | cheap/precise framing, then policy training if needed | tentative framing; model-specific training result (C2, C3) |
| Natural coherent drafts have checker-detectable errors and the model can revise | patch-boundary diagnostic deltas | literature-motivated; repository effect open (C16, C22) |
| Self-repair is unreliable and accepted regressions matter | checker gate or offline reranking | external/design guidance only (C14) |
| Invalid candidates should never enter the search | constrained decoding or training reward | external evidence only |

Always measure whether semantic retrieval substitutes for a read, the checker opportunity rate, whether
the model edits diagnosed locations, and accepted-defect rate. Static tooling will not solve dynamic
behavior, logical errors outside the type system, incorrect annotations, `Any` boundaries, or failures the
model cannot act on.

## Repository layout

| path | purpose |
|---|---|
| `REPORT.md` | final conditional argument and practitioner framework |
| `evidence/` | claim ledger, preregistered protocols, hashes, provenance warnings |
| `runs/agent/` | committed historical raw model results |
| `runs/protocol/` | mechanical checks and draft-recovery audit artifacts |
| `scripts/experiments/` | typed/erased navigation and paired-checker harnesses |
| `scripts/analysis/` | historical and task-level analyzers plus the fast reproducer |
| `scripts/realbench/` | SWE-bench scanning and historical dispatch tooling |
| `scaffold/` | agent and workspace environments |
| `docs/real_repo_progress.md` | preserved chronological research log; not the final claim source |

Historical evidence is preserved. Where raw data or exact provenance is missing, the claim ledger marks
the result tentative or unsupported instead of reconstructing certainty from `log.md` summaries.
