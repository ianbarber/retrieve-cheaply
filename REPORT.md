# When Do Language Servers Help Coding Agents?

## Abstract

Language servers help coding agents when they provide information the agent does not already have, return
it more cheaply than the available alternative, and change the agent's action. LSP transport itself is not
the intervention: types, semantic resolution, diagnostics, delivery policy, and acceptance rules are
separate mechanisms.

The strongest result in this repository is compact retrieval. When the alternative is reading a whole
library file, a compact definition result preserves success while reducing input tokens by 3.5-4.7x across
a local 27B model and two frontier models. The result is consistent across tasks, but most headline runs use
a static AST resolver rather than a live language server. It supports compact semantic retrieval in this
specific baseline comparison, not a general claim for or against LSPs.

Other experiments locate the boundaries. Semantic navigation adds little when the agent can cheaply infer
the target and make a ranged read. A sound typed/erased pilot confirms that types improve resolver precision,
but the agent still reads the target file and gains no correctness benefit. Checker feedback makes one extra
selected workspace type-clean, but does not improve held-out correctness and costs more tokens. The local
gate experiment is not causally valid.

The resulting recipe is direct: use text for unique local facts; use typed semantic resolution for genuine
ambiguity; keep retrieval tools only when they replace work; deliver diagnostics at coherent patch
boundaries; and deploy gates only after telemetry shows that they prevent accepted defects.

## Practitioner recipe

1. **Use text search and ranged reads for unique, local bindings.** They are cheap, transparent, and hard to
   beat when the relevant fact is nearby ([C6](evidence/claim_ledger.md#c6),
   [C9](evidence/claim_ledger.md#c9)).
2. **Use typed semantic resolution for non-lexical ambiguity.** It is most promising for overloads,
   inheritance, re-exports, factories, and same-named implementations
   ([C15](evidence/claim_ledger.md#c15), [C24](evidence/claim_ledger.md#c24)).
3. **Keep semantic retrieval only when it replaces work.** A definition result followed by the same target
   read is overhead, not compression ([C1](evidence/claim_ledger.md#c1),
   [C4](evidence/claim_ledger.md#c4)).
4. **Run target-scoped diagnostic deltas on coherent patches.** Type cleanliness is useful intermediate
   evidence, not proof of behavioral correctness ([C11](evidence/claim_ledger.md#c11),
   [C26](evidence/claim_ledger.md#c26)).
5. **Gate only when telemetry demonstrates prevention.** A gate should stop a defect the ungated agent would
   submit, or help produce an accepted clean and correct patch ([C14](evidence/claim_ledger.md#c14),
   [C26](evidence/claim_ledger.md#c26)).

Measure substitution, not invocation: did the tool prevent a wrong-file edit, replace a larger read, repair
an actionable defect, or reject a bad submission?

## 1. Frame the question correctly

"LSP" is too broad to serve as a single experimental treatment:

- **LSP** is the transport between a client and a semantic service.
- A **language server** parses, indexes, infers, resolves, and validates code.
- **Types** are semantic information written in or inferred from the program.
- A **type checker** tests consistency and emits diagnostics; it need not use LSP.
- An **integration** decides when the agent sees or acts on the signal: pull retrieval, pushed context,
  patch feedback, a gate, reranking, constrained generation, or training reward.

Types and language servers are therefore not competitors. Types can make a server's answer precise; the
same type may also be readable directly from source. The useful question is which signal and integration
change behavior at acceptable cost.

For task `t`:

`value(t) ~= opportunity x correctness x uniqueness x compression x election x actionability - cost`

This decomposition explains most null results. A correct goto has no deployment value if the agent ignores
it. A compact definition has no compression value if the agent then reads the same file. A checker has no
revision value on a clean draft, and a correct diagnostic has no outcome value if the agent cannot repair it.

| Mechanism | Useful when | Redundant or harmful when |
|---|---|---|
| Semantic resolution | Text does not uniquely identify the binding | The binding is visible or cheaply traced |
| Compact retrieval | A definition or method span replaces a large read | The baseline already uses a small range, or the agent rereads the file |
| Diagnostics | A coherent patch contains a checker-detectable, repairable defect | The draft is clean, the signal is noisy, or the model cannot revise |
| Gate or reranking | Cleanliness predicts acceptance and bad candidates occur | False positives dominate or no bad completion reaches the gate |
| Structured operations | Text edits are ambiguous or unsafe | A simple local edit is already unique and reliable |
| Training or reward | A valuable tool is available but rarely elected | The policy already chooses and uses it effectively |

## 2. What the evidence says

The [claim ledger](evidence/claim_ledger.md) maps every material claim to its artifacts and status. The
[manifest](evidence/manifest.json) records hashes, configurations, and provenance warnings.

### 2.1 Compact retrieval works when it replaces a whole-file read

The `effic` and `effic_real2` tasks ask an agent to implement a small target with an unfamiliar library API.
The treatment returns a compact definition; the counterfactual drives whole-file retrieval. Every attempt
in both arms succeeds.

| Model | Pooled input-token ratio | Tasks cheaper with definition | Mean task ratio (95% bootstrap CI) | Success |
|---|---:|---:|---:|---:|
| Qwen3.6-27B | 3.50x | 11/11 | 4.02 (2.85-5.30) | 44/44 both arms |
| Claude Sonnet 4.5 | 3.65x | 11/11 | 3.65 (2.72-5.20) | 44/44 both arms |
| DeepSeek v3.1 | 4.70x | 10/11 | 6.03 (2.32-10.82) | 44/44 both arms |

The task-level medians are 3.83, 3.01, and 2.70. The gap between DeepSeek's mean and median is a reminder to
report task distributions rather than only pooled totals. Seeds are repeated runs within tasks; intervals
resample task means. Most of these files use the repository's static AST resolver, so the supported claim is
compact retrieval against whole-file reading ([C1](evidence/claim_ledger.md#c1)).

Tool election is a policy question. In matched local 7B runs, definition-trained and read-trained policies
both solve 40 cells while mean input falls from 3,191 to 684 tokens. Relabeling raises definition use from
approximately zero to 100%; cost-reward training reaches 86% use with 36/36 success. Prompting and training
can change election, but these runs do not establish a model-size law
([C2](evidence/claim_ledger.md#c2), [C3](evidence/claim_ledger.md#c3)).

A live-first Pyrefly suite reduces mean input from 2,894 to 689 tokens and raises success from 14/24 to
24/24. The tool combines live lookup with AST-selected use sites, span expansion, and fallback, and the rows
do not record which backend answered. This supports the composed integration, not a pure live-server
ablation ([C4](evidence/claim_ledger.md#c4)).

**Takeaway:** compact definitions are valuable when they replace coarse retrieval. Their advantage over an
efficient grep-and-ranged-read baseline remains untested.

### 2.2 Semantic navigation needs real ambiguity and real substitution

A 15-task dispatch suite compares grep/ranged reads with live Pyrefly goto. On the annotated 27B variant,
grep, neutral goto, and framed goto solve 15/15, 14/15, and 15/15; matched-success token ratios are 0.972 and
1.041. Stripped and factory-indirection variants remain near one (0.945-1.065).

This is a useful negative regime, not evidence that navigation is generally redundant. Prompts expose the
concrete receiver and make the correct file cheap to identify. There is no erased or `Any` condition, and
some variants still describe an annotation that has been removed. The suite shows that goto adds little
when text already reveals the answer ([C6](evidence/claim_ledger.md#c6),
[C9](evidence/claim_ledger.md#c9)).

The typed/erased navigation pilot isolates this mechanism. Typed and erased repositories have byte-identical
runtime code, tests, and gold patches. Only `factory.pyi` differs: the typed stub has sound per-key `Literal`
overloads; the erased stub returns the base type. Each task contains 8-15 same-named overrides, and neither
the prompt nor failure names the target class or path. Strict live Pyrefly resolves the definition at the
use site without AST fallback. Mechanical checks confirm that typed lookup reaches the gold override,
erased lookup returns a non-discriminating base result, widening the key removes the discrimination, and
both variants are type-clean ([C15](evidence/claim_ledger.md#c15)).

Only Qwen3.6-27B meets the preregistered actionability criterion; the 7B and 14B models do not. The factorial
estimate therefore covers Qwen3.6-27B on two tasks:

| Outcome | Result |
|---|---:|
| Correctness | All 12 causal/deployment cells pass |
| Typed automatic / typed textual tokens | 1.037 (task bootstrap 0.988-1.093) |
| Erased automatic / erased textual tokens | 1.190 (1.119-1.251) |
| Typed-by-automatic interaction | -214 tokens (-402 to -26) |
| Automatic-result substitution | Every result is followed by a target-file read |
| Neutral / framed elective use | 0/2 and 1/2 |

The typed ratio lies inside the prespecified 0.90-1.10 margin for these two pilot tasks only; this is not a
population equivalence claim. Lookup itself takes about six seconds per task, dominated by a fixed indexing
wait. Including that lookup, descriptive end-to-end times are about 109 seconds for automatic context and
64 seconds for textual baselines. Correctness is ceilinged, and the tool does not replace retrieval
([C24](evidence/claim_ledger.md#c24)).

**Takeaway:** sound types can make semantic resolution precise. That precision becomes useful only when it
changes localization or replaces retrieval; automatic delivery alone can turn a correct answer into extra
context and latency.

### 2.3 Checker feedback needs opportunity, actionability, and an outcome

The checker studies mostly test regimes with no measurable headroom:

| Study | Result | What it establishes |
|---|---|---|
| Inference suite | 18/18 in every checker and no-checker cell for both frontier models | Ceiling; natural checker opportunity was not measured |
| Authoring, 27B | 12/12 in no-checker, elective, and after-every-edit arms | No outcome headroom |
| Authoring, 7B | 6/12 no checker, 3/12 elective, 4/12 noisy; noisy input costs 2.35x | These independently generated live integrations do not help |
| Exact workspace replay | 2 coherent recovered workspaces are checker-positive; 3 are incoherent and 7 unrecoverable | Checker opportunity exists in a selected subset, not at an estimated prevalence |

Residual-error counts from the authoring study are invalid because they include diagnostics from the
generated test runner. Independently generated treatment arms also do not isolate the value of diagnostics
on the same draft. The appropriate unit is a coherent patch frozen before paired revisions
([C11](evidence/claim_ledger.md#c11)).

Natural-draft calibration yields 0/3 coherent drafts from the 7B model and 2/8 from the 14B model; both
coherent 14B drafts are type-clean. The sample therefore lacks the required coherence-and-opportunity band.
This is a calibration result, not a checker null ([C16](evidence/claim_ledger.md#c16),
[C22](evidence/claim_ledger.md#c22)).

A selected case series uses two exact checker-positive recovered workspaces and forks each draft into
control and one-shot diagnostic revisions using unambiguous indentation-anchored edit serialization. Results
are:

| Outcome | Control | One-shot diagnostics |
|---|---:|---:|
| Type-clean final workspace | 1/2 | 2/2 |
| Held-out tests pass | 1/2 | 1/2 |
| Accepted, type-clean, and held-out-correct | 1/2 | 1/2 |
| Mean revision input tokens | 1,368 | 1,585 |

Diagnostics improve an intermediate checker state on one selected task, at 217 extra revision tokens, but
do not improve behavioral or joint success. The sample is two selected workspaces, one seed, and a different
model from the model that generated the drafts; draft-generation cost is unavailable
([C26](evidence/claim_ledger.md#c26)).

The paired gate arm diverges from control before either attempts completion, so no valid prevention contrast
exists. It records no rejection event.

**Takeaway:** report checker opportunity, diagnostic deltas, repair behavior, held-out correctness, and total
cost separately. A cleaner patch is evidence that the checker changed the work, not that the work is right.

### 2.4 Other feedback and external validity

Execution feedback is ceilinged in the committed small-task suite: two frontier models, 14 tasks, three
seeds, and three delivery modes all pass, for 252/252 attempts. This does not establish equivalence outside
small simulable functions.

Claims about correction, prevention, repository scaling, and a 35B model that appear only in the research
log lack the raw artifacts needed for verification. They are excluded from the empirical conclusions and
classified in the claim ledger.

The bounded real-repository scan found no fully admissible task. One Django case has a working environment
and substantial override ambiguity, but leakage and fix-site resolution were not fully audited. Both
recorded arms pass and the semantic tool is not elected. Constructed tasks therefore provide the cleanest
causal apparatus here, while population validity remains open. The audit and rejection reasons are in
[docs/external_validity_recon.md](docs/external_validity_recon.md).

## 3. Practitioner decision table

| Situation | Recommended integration | Evidence status | Measure before keeping it |
|---|---|---|---|
| Fact is local, visible, and unique | Grep plus ranged reads | Tentative guidance from negative retrieval regimes ([C6](evidence/claim_ledger.md#c6), [C9](evidence/claim_ledger.md#c9)) | Localization success, bytes read, total cost |
| Binding is ambiguous across overloads, inheritance, factories, or re-exports | Typed semantic result; use automatic delivery first to test the upper bound | Resolver mechanism supported; useful agent benefit open ([C15](evidence/claim_ledger.md#c15), [C24](evidence/claim_ledger.md#c24)) | Exact resolution, wrong-file edits, substitution, latency |
| A compact result can replace a large read | Definition or enclosing-method span | Supported against whole-file reads; live transfer tentative ([C1](evidence/claim_ledger.md#c1), [C4](evidence/claim_ledger.md#c4)) | Semantic-then-read rate, expected cost per success |
| Automatic context helps but elective use is low | Cheap, explicit framing; then policy training if the upper bound justifies it | Model- and policy-specific ([C2](evidence/claim_ledger.md#c2), [C3](evidence/claim_ledger.md#c3)) | Election, retained correctness, added context |
| A coherent patch has checker-detectable errors and the model can revise | Target-scoped diagnostics at the patch boundary | Intermediate-state effect on two selected cases; correctness benefit open ([C26](evidence/claim_ledger.md#c26)) | Opportunity, new/eliminated errors, held-out success, revision cost |
| Bad submissions occur and cleanliness predicts failure | Acceptance gate | External/design guidance; local causal arm invalid ([C14](evidence/claim_ledger.md#c14), [C26](evidence/claim_ledger.md#c26)) | Identical pre-gate trajectory, rejections, prevented accepted defects, false-positive cost |
| Several candidates already exist | Checker reranking | External evidence only | Clean-correct ranking precision and candidate cost |
| Text edits are structurally risky or non-unique | Server/AST rename, references, or structured edit | External evidence only | Semantic preservation, rollback rate, latency |

Static tooling will not solve dynamic behavior, incorrect annotations, `Any`-heavy boundaries, environment
failures, or logic outside the checker. These are scope boundaries, not all tested null results.

## 4. Related work

Positive prior results generally target missing context, automatic delivery, coherent drafts, or generation
constraints. Those regimes are compatible with this report's negative results for redundant retrieval and
noisy feedback.

| Work | Relevant lesson |
|---|---|
| [Typed Holes](https://arxiv.org/abs/2409.00921) and [LSPRAG](https://arxiv.org/abs/2510.22210) | Push types, definitions, or references when context is missing; automatic delivery removes election failure. |
| [STALL+](https://arxiv.org/abs/2406.10018) | Static analysis effects vary by language and integration phase; retrieval and semantic analysis can complement each other. |
| [CoCoGen](https://arxiv.org/abs/2403.16792) | Check a coherent draft, then retrieve context to repair project/API mismatches. This is the opportunity-conditioned regime absent from after-every-edit feedback. |
| [CodeStruct](https://arxiv.org/abs/2604.05407) | Structured reads, edits, and syntax validation can improve actionability without making a claim specific to LSP transport or types. |
| [CompCoder](https://arxiv.org/abs/2203.05132), [type-constrained generation](https://arxiv.org/abs/2504.09246), and [RLCSF v2](https://arxiv.org/abs/2510.22907) | Compiler and server signals can rank, constrain, or train candidates even when repair-time feedback is not useful. |

The reconciliation is simple: static tooling helps when it supplies missing, correct, compact, actionable
information at the phase where the model can use it. It does not help when the same fact is already cheap,
the draft offers no checker opportunity, delivery is ignored or noisy, or the cost exceeds the work saved.

## 5. Reproducibility and limits

From a clean clone:

```bash
python3 -m pip install -e '.[dev,analysis]'
python3 scripts/analysis/reproduce_all.py
```

The reproducer verifies the manifest, reruns retained analyzers, recomputes task-level effects, and executes
the navigation manipulation checks without making model or API calls. Model runs are separate; see
[evidence/protocols.md](evidence/protocols.md) before using the navigation or checker run scripts.

The main limits are:

- Compact-retrieval tasks are synthetic and compare against whole-file reads; efficient ranged retrieval is
  the harder baseline.
- The typed navigation outcome comes from two pilot tasks with ceilinged correctness; there is no outcome
  headroom or retrieval substitution to justify confirmation.
- The checker result comes from two selected recovered workspaces. It does not estimate natural opportunity
  prevalence or full end-to-end cost, and the gate comparison is invalid.
- The real-repository scan found no fully admissible case, so external validity is unresolved.
- Some retained artifacts contain provenance gaps, including unavailable seed shards, incomplete server
  backend/version records, source-hash mismatches, and invalidated runs. Exclusion reasons and discrepancies
  are reported in the claim ledger and manifest.

Within these limits, the evidence supports compact retrieval against whole-file reads and the mechanistic
claim that sound types sharpen semantic resolution.

## Conclusion

The evidence supports a conditional recipe, not a verdict on LSPs. Compact semantic retrieval clearly helps
when it replaces whole-file reading. Sound types make ambiguous resolution more precise. Neither fact means
that a semantic result will save work: in the realistic retrieval and typed navigation pilots, agents often
obtain the right answer through text or reread the target after receiving it.

Checker feedback should be judged the same way. It is useful only where checker-positive coherent drafts
occur, the model can repair them, and cleaner state predicts a better accepted outcome. This repository
shows a small intermediate-state improvement, not a correctness or prevention gain. The practical standard
for every integration is therefore the same: demonstrate a real opportunity, a unique signal, a changed
action, and lower expected cost per correct result.
