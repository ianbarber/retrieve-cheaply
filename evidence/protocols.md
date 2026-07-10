# Frozen protocols and run budget

## Experiment 1: types x semantic navigation

Protocol version `navigation-v1` uses four excluded pilot instances over two development templates, twelve
additional apparatus-audit instances over three templates, and twelve reserved confirmation instances over
three new templates, with deterministic disjoint seeds in `scripts/experiments/navigation_tasks.py`.
The apparatus set is explicitly not confirmation because it was inspected while validator behavior was
still being repaired. Identifiers are neutral;
each task has 8–15 overrides, factory/registry construction, identical implementation/test/gold files
between variants, and a one-line gold fix. The only source difference is the remote factory return type.

The core cells are typed/textual, typed/automatic semantic result, erased/textual, and erased/automatic
semantic result. Typed deployment cells are textual, neutral elective semantic tool, cheap/precise framed
tool, and automatic semantic result. `positive_control` supplies the correct definition and must pass
every selected pilot family before the driver continues to causal cells. Automatic results are composed:
strict Pyrefly LSP definition resolution plus the enclosing method span. There is no AST fallback.

Mechanical exclusions are fixed before model runs: reject a family if base does not fail, gold does not
pass, runtime outputs differ across variants, gold differs, override count is outside 8–15, typed goto
misses the gold override, erased goto is discriminating, the rendered prompt leaks the concrete class or
gold path, or the positive control cannot be edited. Pilot and apparatus-audit families may be revised;
confirmation families may not. Confirmation is one shot after prompts, generator, metrics, exclusions,
and source hashes are frozen.

Primary outcome is task-level held-out pass@1. Other preregistered outcomes are correct-file localization
before first edit, wrong-file edits, input/output tokens, calls, reads, turns, wall time, server latency,
semantic election, semantic-then-read behavior, and expected tokens per successful task. Seeds are nested
within task. Report task distributions, means and medians, and task bootstrap intervals. Equivalence
margins, if a null is discussed, are +/-10 percentage points for pass@1 and a token ratio of 0.90–1.10;
an interval crossing those bounds is inconclusive rather than equivalent.

## Experiment 2: checker opportunity and integration

Protocol version `checker-paired-v1` first generates a natural draft with no checker access, stores every
workspace file and its hash, then forks control, one-shot coherent-patch diagnostics, acceptance gate, and
deliberately noisy after-every-edit trajectories from those exact bytes. Coherence means the target parses
and contains no remaining explicit `raise NotImplementedError`. Failed/incoherent drafts remain in the
unconditional denominator but are separated from semantic checker opportunities.

Diagnostics are target-scoped deltas from the pristine workspace, deduplicated, uncapped in raw JSON, and
presented with path, range, code, concise message, classification, and code frame. Tests execute outside
the checked tree. Opportunity means at least one new semantic diagnostic on the frozen natural draft;
syntax/partial-edit failures are separate. The model regime must put 20–70% of coherent development drafts
in this opportunity set while retaining viable edit behavior. If none does, report that capability gap.

Control and treated revisions share the same token, turn, read, and test budgets. Outcomes include
unconditional and opportunity-conditioned held-out pass, diagnostics eliminated/retained/introduced,
edits overlapping diagnosed locations, type-clean accepted patches, gate rejection/abstention, tokens,
turns, latency, and expected cost per accepted correct patch. A +/-10 percentage-point margin applies to
pass@1 or accepted-defect null claims.

## Run and spend budget

No paid API run is authorized by this protocol. The executed development regimes use locally cached
Qwen2.5-Coder 7B/14B models. The pilot is two navigation families across one positive-control cell,
four core cells, and two incremental deployment cells (typed baseline/automatic are shared), followed by
three checker development tasks. Monetary cap is **$0**. The frozen navigation confirmation is twelve
families x six unique cells x three nested seeds; it remains
unrun until the pilot clears every gate. Any OpenRouter or other paid confirmation requires a separate
model/cell/cost proposal.

## Execution status

The local 7B navigation positive control passes 2/2, but all 12 two-task causal/deployment pilot cells fail
held-out behavior; confirmation is blocked as a uniform floor. Fresh checker calibration also blocks
revisions: 7B yields 0/3 coherent submitted drafts. Across two development batches, 14B yields 2/8 coherent
drafts; both are type-clean, for 0% semantic opportunity. These are exploratory stopping-gate results, not
confirmation evidence. No paid API calls were made.
