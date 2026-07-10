# When Do Language Servers Help Coding Agents?

## Abstract

Language servers are not uniformly useful or redundant for coding agents. Their realized value is a
chain:

> opportunity prevalence × signal correctness and uniqueness × retrieval/compression advantage ×
> agent election × ability to act − tool, latency, and context costs.

The strongest committed result in this repository is narrow and positive. When an agent otherwise reads
a whole library file, a compact definition result preserves success while reducing input tokens by
3.5–4.7x in pooled comparisons across a local 27B model and two frontier models. Task-level reanalysis
confirms the direction on 11/11, 11/11, and 10/11 tasks. This is evidence for compact semantic retrieval
against a whole-file baseline, not for the general value of the Language Server Protocol (LSP).

The negative regimes are equally important. In a historical dispatch suite, a capable agent often read
the concrete receiver type and opened the correct file directly, so semantic navigation was near
token-neutral. That suite leaked the disambiguating class and never erased the type, so it cannot support
the old conclusion that navigation never beats a readable type. Historical checker experiments compared
independently generated trajectories and delivered either elective or after-every-edit diagnostics. Their
residual counts were polluted by type-checking the generated test runner, although corrected replay now
finds genuine checker-positive opportunities in two coherent historical final workspaces.

We therefore replace the old “types, not language servers” conclusion with a decision framework and two
causal protocols. Experiment 1 pairs typed and erased factories and automatically supplies strict live
Pyrefly results to separate semantic information from election. Its manipulation checks pass, but a local
7B pilot is uniformly floored despite typed automatic results localizing the correct file. Experiment 2
freezes natural drafts before paired revisions; fresh 7B and 14B calibration misses the required
coherence/opportunity band, so paired checker outcomes remain unrun.
The practical conclusion is conditional: use the cheapest integration that supplies unique, actionable
information at an actual opportunity, and measure whether it replaces work rather than merely preceding
it.

## 1. Terms and causal model

These are different objects and must not be treated as competitors:

- **LSP** is a transport protocol between an editor/client and a semantic service.
- A **language server** is the implementation that parses, infers, indexes, resolves, and validates code.
- **Type annotations and inferred types** are semantic information in or derived from code.
- A **type checker** tests consistency and emits diagnostics. It may be a CLI, a server feature, or a
  compiler phase.
- An **integration mode** determines when an agent receives or uses the information: pull retrieval,
  pushed context, coherent-patch feedback, acceptance gate, reranking, constrained decoding, or training
  reward.

Types are semantic substrate. A language server can infer types, follow bindings, index definitions,
validate a patch, and expose the result compactly. A type may also be readable directly in source; a
checker may run without LSP; an LSP server may provide useful syntax or index operations without a rich
type system. The scientific question is which information and integration changes behavior at acceptable
cost.

For task `t`, a useful decomposition is:

`value(t) ≈ opportunity(t) × correctness(t) × uniqueness(t) × compression(t) × election(t) × actionability(t) − cost(t)`.

A zero at any multiplicative stage explains many nulls. A perfect checker has no revision value on a
type-clean draft. A perfect goto has no deployment value when it is not elected. A compact result has no
compression value when the agent still reads the same file. Correct diagnostics have no outcome value if
the model cannot make a valid edit. Tool latency and repeated context can make a correct signal net
negative.

## 2. What a server can provide

| value | useful mechanism | redundant when | necessary conditions |
|---|---|---|---|
| Semantic information | infer receiver/type/binding unavailable in the visible text | the fact is already visible or cheaply derived | the server resolves the relevant language construct correctly and more uniquely than text search |
| Context compression | return a definition, signature, hover, or references instead of a large read | the baseline already uses a small ranged read, or the agent reads the file after the result | result replaces retrieval and includes enough editable context |
| Disambiguation/indexing | resolve re-exports, overloads, inheritance, factories, or same-named methods | names are lexically unique or the receiver is obvious | correct project configuration, index coverage, and static resolvability |
| Validation | detect inconsistent calls, attributes, keys, returns, or imports | natural drafts are type-clean or errors lie outside the checker | new actionable diagnostics, coherent delivery, and successful revision |
| Gate/reranking | keep dirty patches out or prefer clean candidates | false positives dominate or type cleanliness is irrelevant | delta-scoped diagnostics and an explicit acceptance policy |
| Safe structured operations | rename, references, AST-aware edits, syntax validation | a simple text edit is already safe and unique | operation preserves semantics and its preconditions are checked |
| Supervision/reward | teach tool election or penalize compiler/type failures | the deployed policy already elects and acts correctly | training examples match deployment opportunities and costs |

## 3. Evidence audit

The machine-readable hashes and configurations are in `evidence/manifest.json`; the full claim mapping is
in `evidence/claim_ledger.md`. This section retains the supported historical evidence while separating
static resolvers, live servers, hybrids, checkers, and execution feedback.

### 3.1 Supported: compact retrieval beats whole-file reads

The `effic` and `effic_real2` tasks require an agent to implement a small target using an unfamiliar
library API. The treatment returns a compact definition; the counterfactual removes that action and
drives whole-file retrieval. Most headline files use the repository’s static AST resolver, not a live
language server. All committed tool-value files used temperature 0.7, despite older report prose saying
0.0.

| model / treatment | tasks × seeds | no-definition tokens | compact-definition tokens | success | task-level effect |
|---|---:|---:|---:|---:|---|
| Qwen3.6-27B, static definition tool | 11 × 4 | 4563 | 1302 | 44/44 both arms | cheaper on 11/11 tasks; mean task ratio 4.02, 95% bootstrap 2.85–5.30; median 3.83 |
| Claude Sonnet 4.5, static definition tool | 11 × 4 | 21,985 | 6018 | 44/44 both arms | cheaper on 11/11; mean 3.65, 2.72–5.20; median 3.01 |
| DeepSeek v3.1, static definition tool | 11 × 4 | 36,192 | 7705 | 44/44 both arms | cheaper on 10/11; mean 6.03, 2.32–10.82; median 2.70 |

The pooled token ratios are 3.50x, 3.65x, and 4.70x. The difference between DeepSeek’s mean and median
shows why tool-loop distributions must not be summarized by a mean alone. The expected token cost per
success equals the per-arm token mean here because every attempt succeeds. Seeds are nested repetitions;
the intervals resample tasks after averaging within task.

The local 7B training experiments provide a complementary policy result. A read-trained and a
definition-trained policy both solve 40 matched `(task, seed)` cells, while input tokens fall from 3191
to 684 (4.7x). A clean relabel retest changes definition election from approximately zero to 100%, and a
cost-reward GRPO retest reaches 86% definition use, 663 input tokens, and 36/36 success. These comparisons
show that election can be changed by prompting or training. They do not establish a monotonic relationship
with parameter count because model family, training, and policy differ.

### 3.2 Tentative: live-server transfer

`lsp_base.json` and `lsp_sft.json` use live-first Pyrefly on 12 tasks × two seeds. The observed token mean
falls from 2894 to 689 while success rises from 14/24 to 24/24. The historical implementation uses AST
logic to find a use site and expand the returned span, and it can fall back after an LSP miss. Rows do not
record which backend answered. This is evidence that the composed live-first tool can reproduce the
controlled behavior, but it is not a pure server ablation.

Files named `reallsp_*` are not live LSP runs: they use the static resolver over a live workspace. The
manifest labels this explicitly. Historical local logs mention Pyrefly 1.0.0; the external x86 dispatch
host used 1.1.1. No historical result JSON records a server version, so neither version is assigned
globally.

### 3.3 Tentative negative: realistic retrieval can erase compression advantage

A three-task mini-swe-agent probe found that a capable shell agent used grep and ranged reads rather than
whole-file reads, and definition calls were often additive. Full raw logs are not committed, so this is a
case study only.

The later 15-task dispatch suite compared grep/ranged-read retrieval with a live Pyrefly goto composed
with an enclosing span. For Qwen3.6-27B on the annotated variant, grep, neutral goto, and framed goto solve
15/15, 14/15, and 15/15, with matched-success token ratios 0.972 and 1.041. Stripped and factory-indirection
variants produce descriptive ratios from 0.945 to 1.065. A 7B model solves only 2–4 of 15 depending on the
arm, with no common matched-success set.

These trajectories show a negative regime: when the prompt exposes a concrete receiver and the correct
file is cheap to read, goto may not save tokens. They do **not** prove equivalence or that navigation never
beats a readable type. The prompt explicitly described the static receiver, showed concrete construction,
and even claimed a call-site annotation in variants where it was removed. No erased/`Any` condition existed,
and no equivalence margin was preregistered. The former broad conclusion is unsupported.

### 3.4 Checker evidence: opportunity and integration were confounded

The held-out `gapd2` inference suite is a ceiling observation. For each of two frontier models, all six
rich tasks × three seeds pass in the hinted no-checker, hinted elective-checker, and unhinted no-checker
conditions: 18/18 in each cell. This shows no behavioral headroom. The artifacts do not preserve a common
natural first draft or diagnostic deltas, so checker-opportunity prevalence is unmeasured rather than zero.

The 12-task authoring experiment compares no checker, elective checker, and automatic feedback after
each edit. Qwen3.6-27B passes 12/12 held-out in every independently generated arm. Qwen2.5-Coder-7B passes
6/12 without a checker, 3/12 with an elective checker, and 4/12 with after-every-edit feedback; the noisy
arm uses 2.35x the input tokens. Because first drafts differ across arms, this is evidence only that these
particular live integrations did not help, not that coherent diagnostics or a gate are unusable.

The old residual-diagnostic metric is invalid. Tests wrote `_run_tests.py` into the checked workspace,
and Pyrefly diagnosed that generated test. Replaying five exact uncapped no-checker final trajectories
recovers two coherent workspaces; both are checker-positive, with three and one new target-scoped semantic
diagnostics. Three other recovered workspaces are incoherent, and seven trajectories cannot be recovered
because historical edit bodies were truncated. This proves opportunity existed in a narrow historical
subset, but these are final trajectories without a first-draft submission boundary or paired revisions.

### 3.5 Other boundaries and unsupported history

Execution feedback is also ceilinged on the committed small-task suite. Two frontier models × 14 tasks ×
three seeds pass in all three arms (no execution, elective execution, automatic execution), 252/252 total
attempts. Elective execution is always used and automatic feedback saves turns, but absence of failures is
not equivalence beyond small, simulable functions.

Older claims about correction, completeness, prevention, navigation, 21–86-file scaling, and a 35B model
are backed only by `log.md`, not committed raw JSON and analyzers. The 35B log actually records a positive
direction under a ceiling and calls it inconclusive. Those claims are excluded from the empirical
conclusion rather than deleted from repository history.

## 4. New experiments

### 4.1 Experiment 1: readable types × semantic navigation

`navigation-v1` generates paired repositories with identical runtime implementation trees, tests, and
gold patches. Each begins at `x.<neutral_method>(...)`, has 8–15 same-named overrides across files, and
constructs the receiver through a remote factory/registry. Neutral names are deterministically randomized.
The prompt and visible failure contain neither the concrete receiver class nor gold path.

In the typed variant, the remote factory return contract names the concrete receiver. In erased, it
returns only the base type. The textual baseline can still trace the registry. The automatic treatment
strictly asks live Pyrefly for definition-at-use-site and expands only the enclosing method; it never falls
back to the AST resolver. Thus the four causal cells are typed/textual, typed/automatic result,
erased/textual, and erased/automatic result. Typed deployment cells separately measure neutral election,
cheap/precise framing, and the automatic upper bound.

All four pilot instances across two development templates and twelve additional apparatus-audit instances
across three disjoint templates pass every mechanical check: visible and held-out
base tests fail, both gold tests pass, runtime outputs match, gold is identical, override counts are valid,
typed goto reaches the gold override, erased goto returns a non-discriminating base/null result with an
independent server-health query, and prompts
contain no concrete class/path leakage. This is a **mechanical supported result**, not a model outcome. The
apparatus-audit instances are not called confirmation because they were observed while the validator was
still changing. A new disjoint 12-instance, three-template confirmation split is reserved behind protocol
source hashes and passes the same mechanical checks; no model has seen it.

The exploratory local 7B pilot clears the explicit edit-only positive control on 2/2 tasks, then fails all
12 model cells: 0/2 held-out pass in each of the four causal and two deployment cells. Typed automatic
results localize the correct file on 2/2 tasks versus 1/2 for typed textual retrieval and reduce mean input
tokens from 1,988 to 997; the mean task-level total-token delta is −1,022 with a two-task bootstrap 95%
interval of [−2,040, −3]. They do not cross the actionability bottleneck. Neutral tool availability is
elected on 0/2 tasks; cheap/precise framing induces election on 1/2 (two calls) without a successful edit.
These are two deterministic development tasks, so task-bootstrap pass intervals degenerate at a uniform
floor and do not support equivalence or a causal type/navigation effect. The pilot is rejected and the
one-shot confirmation remains blocked.

### 4.2 Experiment 2: paired checker opportunity and integration

`checker-paired-v1` first produces one natural draft with no checker, stores the exact workspace and hash,
then forks control, coherent-patch diagnostics, acceptance gate, and the historical noisy after-every-edit
integration from identical bytes. Diagnostics are target-scoped deltas from the pristine project,
deduplicated, uncapped in raw results, classified as syntax/partial versus semantic, and presented with a
file, range, code, concise message, and code frame. Tests run outside the checked tree.

Opportunity is a new semantic diagnostic on the natural draft. Calibration requires 20–70% opportunity
among coherent submitted drafts while preserving viable edits. Results will be reported unconditionally
and on the pre-treatment opportunity subset. The gate rejects `done` while new errors remain; its product
metric is accepted type-clean correctness and abstention, not only pass@1. One older local 7B smoke artifact
predates the explicit `<submit_draft/>` boundary and contains repeated partial edits; corrected collection
classifies all 14 diagnostics as syntax/partial cascades and rejects the workspace as incoherent. It is an
apparatus smoke, not a compliant calibration.

Fresh current-protocol calibration also stops before revisions. The 7B model submits 3/3 workspaces but
produces 0/3 coherent drafts. Across initial and extended 14B development batches, the model submits 7/8
and produces 2/8 coherent drafts; both pass held-out behavior and have no semantic diagnostic opportunity.
Thus neither regime reaches the
preregistered minimum of two coherent drafts or the 20–70% opportunity band. This is a capability/calibration
gap for the tested local models, not a checker null. Historical replay proves that checker-positive final
workspaces can occur, but it cannot supply the missing paired first-draft counterfactual.

### 4.3 External validity

The bounded reconnaissance audited the committed SWE-bench scans under a one-hour cap with no new spend.
`django__django-11211` is a partial historical case with a working environment and 21 same-named
overrides, but prompt leakage and a discriminating fix-site goto were not audited; both historical arms
passed and the semantic tool was not elected. Other candidates fail or lack actual-fix
ambiguity, leakage, static-resolution, or environment checks. This is a partial historical case, not an
admissible external-validity result or a population estimate.
The table and rejection reasons are in `docs/external_validity_recon.md`. Constructed tasks remain the
instrumented apparatus; broader external validity is open, with CrossCodeEval as the preferred fallback.

## 5. Related work and reconciliation

Positive prior work generally targets missing context, automatic delivery, coherent drafts, or constrained
generation. Those regimes differ from a self-retrieving repair agent that can cheaply read the same fact.

- **Statically Contextualizing Large Language Models with Typed Holes** (OOPSLA 2024,
  <https://arxiv.org/abs/2409.00921>) pushes hole types, typing context, and remote definitions, then
  iterates with a language server. It supports semantic context injection when information is missing or
  nonlocal; it does not conflict with redundancy when the same fact is already readable in budget.
- **STALL+** (<https://arxiv.org/abs/2406.10018>) compares static analysis in prompting, decoding, and
  post-processing on CrossCodeEval. Effects vary by language and phase, and retrieval plus static analysis
  can be complementary. This motivates separating integration modes rather than asking whether “LSP” wins.
- **CoCoGen** (Findings ACL 2024, <https://arxiv.org/abs/2403.16792>) checks a coherent draft and retrieves
  repository context to repair project/API mismatches. That is precisely the opportunity-conditioned,
  patch-boundary regime omitted by the old after-every-edit study.
- **LSPRAG** (ICSE 2026, <https://arxiv.org/abs/2510.22210>) automatically supplies definitions and
  references for unit-test generation across Java, Go, and Python. Automatic delivery removes election
  failure and directly tests compact semantic retrieval, like Experiment 1’s upper-bound arm.
- **CodeStruct** (ACL 2026, <https://arxiv.org/abs/2604.05407>) studies AST-structured reads/edits and syntax
  validation. It supports safe structured operations and actionability, not a claim specific to types or
  LSP transport.
- **CompCoder** (<https://arxiv.org/abs/2203.05132>) uses compiler feedback for training and candidate
  discrimination; type-constrained generation (<https://arxiv.org/abs/2504.09246>) enforces constraints
  during decoding. These can help when repair-time feedback is not actionable.
- **RLCSF v2** (<https://arxiv.org/abs/2510.22907>) treats compiler/language-server feedback as process
  reward and replay data. It is a training methodology, not direct evidence that live diagnostics raise
  pass@1 in this repository’s task regime.

The reconciliation is conditional. Static tooling helps when it supplies missing, correct, compact,
actionable information at the phase where the model can use it. It is redundant or harmful when the fact
is already cheap to retrieve, the draft has no detectable error, delivery is noisy, the model does not
elect or cannot repair, or latency/context exceeds saved work.

## 6. Practitioner decision table

| situation | preferred integration | verify in telemetry |
|---|---|---|
| Fact is visible, lexically unique, and cheap to read | textual grep/ranged retrieval | localization success and bytes/tokens read |
| Binding is ambiguous; type/definition is remote; re-exports, overloads, or inheritance defeat text | semantic pull navigation | correct unique resolution and wrong-file edit rate |
| Compact definition can replace a large read | automatic or elected semantic span | whether it replaces, rather than precedes, the read; expected cost/success |
| Tool is valuable when forced but rarely elected | cheaper/precise prompt framing, then policy training | election rate and downstream substitution, not calls alone |
| Natural coherent drafts contain checker-detectable errors and the model can revise | patch-boundary diagnostic delta | opportunity rate, diagnosed-location edits, eliminated/new errors, held-out correctness |
| Model cannot reliably self-repair, but latent regressions must not ship | acceptance gate or offline reranking | accepted-defect rate, rejection/abstention, false-positive cost |
| Syntax/type constraints can be enforced before invalid candidates consume budget | constrained decoding or training reward | validity, search cost, and behavioral correctness |
| Operation is structural and risky by text | server/AST structured rename, references, or edit | semantic preservation and rollback rate |

Do not expect static tooling to solve dynamic behavior, logical errors outside the type system, incorrect
annotations, `Any`-heavy boundaries, environment/runtime failures, or errors the model cannot act on.

## 7. Reproducibility and limitations

Run `python3 scripts/analysis/reproduce_all.py` from a clean clone to verify hashes, recompute every
reported historical table, run the navigation manipulation gates, and print task-level effects. Model runs
are separate: `scripts/run_navigation_pilot.sh`, `scripts/run_navigation_confirmation.sh`, and
`scripts/run_checker_paired.sh`. Drivers are repository-relative and honor `PYTHON`; Pyrefly is discovered
from `STREAMS_PYREFLY`, `PYREFLY_BIN`, PATH, or a local virtual environment.

Six merged four-seed result files still declare two seeds. The combined rows contain seeds 0–3, but the
source seed-2/3 shards are unavailable. The manifest preserves this warning instead of silently rewriting
historical raw data. Closed-model versions and providers date quickly. Historical server backend/fallback
and version data are incomplete. Synthetic task families provide causal control but limited external
validity. Twelve reserved confirmation instances will still be too few for tight equivalence claims; null language
requires the preregistered margin and an interval within it.

The manifest flags two source-hash differences on the exploratory navigation model rows: after those rows
ran, `navigation_tasks.py` added the shell drivers to its provenance hash list and
`analyze_navigation.py` added an explicit uniform-floor warning. The generator, prompt, tool behavior, and
stored model rows were not changed. All mechanical and reserved-confirmation artifacts match the final
source hashes; the exploratory rows retain their exact at-run hashes.

## 8. Conclusion

Language servers help coding agents when they expose correct and unique semantics, compress retrieval,
arrive at a real opportunity, are elected or supplied, and lead to a successful action at lower total
cost. They do not help merely because a server exists or a type system is present.

The supported positive result is compact retrieval against whole-file reads. The historical realistic
retrieval, checker, and execution results identify plausible negative regimes but are ceilings, leaky
tasks, noisy integrations, or small case studies rather than universal nulls. The new experiments make
the missing causal distinctions explicit; their exploratory model regimes are rejected at actionability or
draft-coherence/opportunity gates, and confirmation remains open.

The actionable recipe is: start with textual retrieval; add semantic pull for genuinely ambiguous or
remote bindings; supply compact results automatically to measure the information upper bound; train
election only if that upper bound is valuable; deliver checker deltas after coherent patches; use gates or
reranking when prevention matters more than self-repair; and always measure opportunity, substitution,
actionability, and accepted defects alongside pass@1.
