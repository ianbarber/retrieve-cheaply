# When Do Language Servers Help Coding Agents?

## Abstract

Language servers can help coding agents by resolving bindings that text cannot distinguish, returning compact code context, and checking patches. The experiments show a narrow but clear retrieval effect: compact definitions cut total tokens by 1.30x at unchanged 11/11 success against a capable grep-plus-ranged-read interface, and by much more against historical whole-file counterfactuals. Definitions were cheaper on 10/11 tasks and were never followed by a defining-file reread. Semantic navigation was near token-neutral when text already exposed the target. In sound typed/erased tasks, type information let Pyrefly distinguish the correct implementation from many same-named alternatives, but the two-task agent pilot reread every target file and gained neither correctness nor lower cost. In a corrected controlled gate pilot, one of three seeded defects self-repairs before submission. Control accepts the other two bad completions; the gate rejects both, elicits repair, retest, and explicit resubmission, then accepts both clean and held-out-correct. Three exact matched clean drafts pass the gate on their first submission with zero false rejections.

For practitioners, start with the cheapest workflow that resolves the task. Add typed semantic resolution when it prevents wrong-target work, compact semantic spans when they replace retrieval, and diagnostics when coherent patches contain actionable static errors. Measure changed actions and outcomes rather than tool calls. Improve election only after demonstrating service value, and require gates to prove model-origin completion, repair, retest, resubmission, accepted yield, and clean-draft precision.

## Evidence limits at a glance

- **Compact retrieval:** supported on constructed tasks against both whole-file reads and an efficient grep-plus-ranged-read interface; real-repository and live-LSP generalization remain open.
- **Typed navigation:** mechanism supported (sound types sharpen resolution); agent-level benefit not shown — only two pilot tasks, every automatic result followed by a target read.
- **Checker feedback:** a valid selected case series shows an intermediate checker-state effect but no joint-outcome gain; the earlier v5 hidden-defect one-shot comparison has observation/action leakage and is excluded.
- **Gates:** accepted recovery is shown on 2/2 reached bad completions, with 0/3 false rejections on matched clean controls. Natural prevalence and population precision remain open.
- **Real-repository generalization:** unresolved — the bounded scan found no fully admissible task.

## Decision checklist

Before adding a language-server integration, check:

1. **Is there a concrete bottleneck the server removes?** Ambiguous binding, broad retrieval, or repairable static error.
2. **Does the integration change what the agent does?** Fewer reads, correct target, or repaired defect.
3. **Is the outcome better or cheaper?** Held-out tests pass, total tokens fall, or wall time drops.
4. **Have you measured the full failure path?** Gates need rejection, repair, and resubmission events; diagnostics need coherent, repairable drafts.

## Practitioner guide

| When you see… | Then default to… | Evidence in this report | Verify by measuring… | Do not use when… |
|---|---|---|---|---|
| The binding is local, visible, and unique | Text search plus ranged reads | Navigation is near token-neutral when prompts expose the receiver and target ([C6](evidence/claim_ledger.md#c6), [C9](evidence/claim_ledger.md#c9)) | Wrong-file edits, target reads avoided, total tokens | The prompt already names the target file and line |
| Overloads, inheritance, factories, or re-exports make the target ambiguous | Typed semantic resolution | Sound types improve resolver precision; agent-level benefit remains open ([C15](evidence/claim_ledger.md#c15), [C24](evidence/claim_ledger.md#c24)) | Wrong-target work prevented, retrieval reduced, not just tool calls | Text already identifies the exact target |
| A compact result can replace search and reading | Definition or enclosing-method span | 1.30x fewer total tokens vs. grep plus ranged reads at 11/11 success, with zero defining-file rereads ([C27](evidence/claim_ledger.md#c27)); historical whole-file contrasts are larger ([C1](evidence/claim_ledger.md#c1)) | Retrieval-response bytes, total tokens, and post-definition rereads | The agent still performs the same search and reads after receiving the span |
| A coherent patch contains checker-detectable errors | Deliver new relevant checker errors at completion, with a repair loop | A corrected gate rejects and recovers both checker-detectable defects that survive to completion ([C29](evidence/claim_ledger.md#c29)); valid one-shot evidence has not improved joint outcome ([C26](evidence/claim_ledger.md#c26)) | Diagnosed-location edits, held-out pass, and total diagnostic cost | The draft is incoherent or the error is not repairable |
| A useful service is available but rarely chosen | Improve tool description or policy | Prompting and training change election in model-specific runs ([C2](evidence/claim_ledger.md#c2), [C3](evidence/claim_ledger.md#c3)) | Higher election retains correctness and lowers total cost | The service has not first shown value when available |
| Bad submission prevention | Staged acceptance gate with explicit repair and resubmit | Two reached bad completions are rejected, repaired, retested, resubmitted, and accepted; three matched clean drafts pass first try ([C29](evidence/claim_ledger.md#c29)) | False rejections, resubmission, accepted-correct yield, and total cost | Abstention is unacceptable or rejection precision is unknown |

## 1. How language-server assistance creates value

Language-server assistance addresses three distinct bottlenecks:

- **Resolve:** identify the correct program entity when names or local text are ambiguous. Type information, whether written or inferred, can distinguish overloads, implementations, and factory results.
- **Compress:** return the needed definition, signature, or method span instead of making the agent search and read broader source context.
- **Validate:** expose a checker-detectable defect in a coherent patch while the agent can still repair it, or prevent a bad patch from being accepted.

Agents can request these services, receive results automatically, or use them through patch feedback, acceptance gates, candidate reranking, structured operations, and training rewards. Delivery changes availability and election; it cannot make redundant information useful.

The common value chain is:

`real opportunity -> useful semantic signal -> changed agent action -> lower cost or higher correctness`

Each step must be measured. Correct resolution is not an agent benefit if the same target was already clear. Compact context saves nothing if the agent rereads the file. A diagnostic has no outcome value on a clean draft or when the model cannot repair the reported error.

## 2. Results

The [claim ledger](evidence/claim_ledger.md) maps every material claim to its artifacts and status. The [manifest](evidence/manifest.json) records hashes, configurations, and provenance warnings.

### Recipe 1: Use compact spans when they replace whole-file reads

The `effic` and `effic_real2` tasks ask an agent to implement a small target with an unfamiliar library API. The treatment returns a compact definition; the counterfactual drives whole-file retrieval. Every attempt in both arms succeeds.

| Model | Pooled input-token ratio | Tasks cheaper with definition | Mean task ratio (95% bootstrap CI) | Success |
|---|---:|---:|---:|---:|
| Qwen3.6-27B | 3.50x | 11/11 | 4.02 (2.85–5.30) | 44/44 both arms |
| Claude Sonnet 4.5 | 3.65x | 11/11 | 3.65 (2.72–5.20) | 44/44 both arms |
| DeepSeek v3.1 | 4.70x | 10/11 | 6.03 (2.32–10.82) | 44/44 both arms |

The task-level medians are 3.83, 3.01, and 2.70; DeepSeek's distribution is strongly skewed. Seeds are repeated runs within tasks, and intervals resample task means. The three-model comparison uses the repository's static AST resolver and measures compact retrieval against whole-file reading ([C1](evidence/claim_ledger.md#c1)).

The harder counterfactual keeps grep, ranged reads, and a whole-file fallback available. On the same eleven `effic_real2` tasks, pinned Qwen3.5-27B at temperature zero succeeds 11/11 with both interfaces:

| Interface | Mean total tokens | Mean retrieval characters | Whole-file reads | Success |
|---|---:|---:|---:|---:|
| Grep plus ranged reads | 1,602 | 1,640 | 4 | 11/11 |
| Compact definition plus text fallback | 1,235 | 1,264 | 0 | 11/11 |

The paired ratio is 1.297 text/definition (task-bootstrap 95% CI 1.093–1.527), and definitions are cheaper on 10/11 tasks. The model elects the definition operation on every task and never follows it with a read of the defining file. The one exception is informative: on `reduceby`, text costs 1,670 tokens and the definition arm 1,959. Compact lookup is a favorable default here, not a per-task dominance claim. A three-task whole-file pilot under the same model produces a 5.67 ratio (2.97–8.96), showing why whole-file-only comparisons overstate the advantage relevant to capable shell agents ([C27](evidence/claim_ledger.md#c27)).

Tool election is a policy question. In matched local 7B runs, definition-trained and read-trained policies both solve 40 cells while mean input falls from 3,191 to 684 tokens. Relabeling raises definition use from approximately zero to 100%; cost-reward training reaches 86% use with 36/36 success. Prompting and training can change election, but these runs do not establish a model-size law ([C2](evidence/claim_ledger.md#c2), [C3](evidence/claim_ledger.md#c3)).

A live-first Pyrefly suite reduces mean input from 2,894 to 689 tokens and raises success from 14/24 to 24/24. The tool combines live lookup with AST-selected use sites, span expansion, and fallback, and the rows do not record which backend answered. The estimate therefore applies to the composed integration ([C4](evidence/claim_ledger.md#c4)).

**Takeaway:** compact definitions reduce cost when they substitute for retrieval rather than precede it. In this controlled suite the effect survives the realistic text baseline; the remaining question is how often that substitution occurs in natural repositories and with live language-server spans.

### Recipe 2: Use typed semantic resolution when it prevents wrong-target work

A 15-task dispatch suite compares grep/ranged reads with live Pyrefly goto. On the annotated 27B variant, grep, neutral goto, and framed goto solve 15/15, 14/15, and 15/15; matched-success token ratios are 0.972 and 1.041. Stripped and factory-indirection variants remain near one (0.945–1.065).

The prompts expose the concrete receiver and make the correct file cheap to identify, so this suite measures a redundant-navigation regime. It has no erased or `Any` condition, and some variants still describe an annotation that has been removed. Goto adds little when text already reveals the answer ([C6](evidence/claim_ledger.md#c6), [C9](evidence/claim_ledger.md#c9)).

The typed/erased navigation pilot isolates this mechanism. Typed and erased repositories have byte-identical runtime code, tests, and gold patches. Only `factory.pyi` differs: the typed stub has sound per-key `Literal` overloads; the erased stub returns the base type. Each task contains 8–15 same-named overrides, and neither the prompt nor failure names the target class or path. Strict live Pyrefly resolves the definition at the use site without AST fallback. Mechanical checks confirm that typed lookup reaches the gold override, erased lookup returns a non-discriminating base result, widening the key removes the discrimination, and both variants are type-clean ([C15](evidence/claim_ledger.md#c15)).

The 7B and 14B models fail a supplied-span edit control. Qwen3.6-27B passes it, so the two-task comparison uses that model:

| Outcome | Result |
|---|---:|
| Correctness | All 12 task-condition runs pass |
| Typed automatic / typed textual tokens | 1.037 (task bootstrap 0.988–1.093) |
| Erased automatic / erased textual tokens | 1.190 (1.119–1.251) |
| Typed-by-automatic interaction | -214 tokens (-402 to -26) |
| Automatic-result substitution | Every result is followed by a target-file read |
| Neutral / framed elective use | 0/2 and 1/2 |

The typed ratio lies inside the prespecified 0.90–1.10 margin for these two pilot tasks; two tasks are insufficient for population equivalence. Lookup itself takes about six seconds per task, dominated by a fixed indexing wait. Including that lookup, descriptive end-to-end times are about 109 seconds for automatic context and 64 seconds for textual baselines. Correctness is ceilinged, and the tool does not replace retrieval ([C24](evidence/claim_ledger.md#c24)).

**Takeaway:** sound types improve resolver precision. Agent value requires that precision to change localization, prevent wrong-target work, or reduce retrieval; automatic delivery alone can turn a correct answer into extra context and latency.

### Recipe 3: Use checker feedback only on coherent, repairable errors

The broad checker suites do not isolate feedback value. Frontier inference arms and 27B authoring arms are at ceiling (18/18 and 12/12), while the 7B authoring arms use different first drafts. Exact recovery finds two coherent workspaces with relevant semantic diagnostics, but natural-draft calibration produces no usable opportunity: 0/3 7B drafts are coherent, and the 2/8 coherent 14B drafts are already type-clean ([C11](evidence/claim_ledger.md#c11), [C16](evidence/claim_ledger.md#c16), [C22](evidence/claim_ledger.md#c22)).

A paired case series forks each of the two recovered workspaces into control and one-shot diagnostic revisions:

| Outcome | Control | One-shot diagnostics |
|---|---:|---:|
| Type-clean final workspace | 1/2 | 2/2 |
| Held-out tests pass | 1/2 | 1/2 |
| Accepted, type-clean, and held-out-correct | 1/2 | 1/2 |
| Mean revision tokens | 1,368 | 1,585 |

Diagnostics improve an intermediate checker state on one selected task, at 217 extra revision tokens, but do not improve behavioral or joint success. The sample contains two selected workspaces and one seed; draft-generation cost is unavailable ([C26](evidence/claim_ledger.md#c26)).

The earlier paired gate arm diverges from control before either attempts completion and records no rejection event, so that historical contrast remains invalid.

The first hidden-defect development result exposes an apparatus bug rather than a valid submission effect. After the model emits `<test/>`, the passing-test user observation literally says to emit `<done/>`; v5 leaves action cursors before that observation. Its recorded first `done_attempt` therefore fires at token 4 from user text while the assistant has emitted only `<think>`. V5 still shows that gate feedback can precede repair, but it cannot identify model submission, one-shot acceptance, or resubmission effects and is excluded from those claims ([C28](evidence/claim_ledger.md#c28)).

Protocol v6 advances every action cursor beyond tool observations, marks completion origin, invalidates stale passing-test state after any edit, and requires a fresh test and model-generated `<done/>` after rejection. `checker-gate-v2` pairs each of three seeded hidden defects with its exact validated clean gold counterpart. Control and gate receive identical prompts and have identical model-generated prefixes through the first completion:

| Controlled cohort outcome | Control | Gate |
|---|---:|---:|
| Seeded defect self-repaired before submission | 1/3 | 1/3 |
| Reached bad completion accepted | 2/2 | 0/2 |
| Reached bad completion rejected | 0/2 | 2/2 |
| Rejected, repaired, retested, resubmitted, accepted clean/correct | 0/2 | 2/2 |
| Accepted type-clean and held-out-correct across defect workspaces | 1/3 | 3/3 |
| Matched clean first submission accepted | 3/3 | 3/3 |
| Matched clean false rejection | — | 0/3 |
| Mean revision tokens, defect cohort | 838 | 1,211 |
| Mean revision tokens, clean cohort | 643 | 643 |

The gate pairing audit passes 6/6 and every completion is verified as model-generated. On the two actual bad-completion opportunities, each rejection is followed by one diagnosed-location edit, a passing visible test, a second `<done/>`, a clean gate check, and acceptance. The third seeded defect is repaired identically in control and gate before completion, so it is retained as a spontaneous-repair case rather than post-selected away. Clean controls receive the checker call and latency but no extra model tokens because all three pass on the first check ([C29](evidence/claim_ledger.md#c29)).

**Takeaway:** delivery phase and lifecycle semantics matter. In this controlled pilot, a staged gate converts every reached checker-detectable bad completion into an accepted correct patch without rejecting matched clean submissions. The remaining deployment question is how often those opportunities and false rejections occur in a larger natural workload.

### Execution feedback and external validity

Execution feedback is ceilinged in the committed small-task suite: two frontier models, 14 tasks, three seeds, and three delivery modes all pass, for 252/252 attempts. This does not establish equivalence outside small simulable functions.

The bounded real-repository scan found no fully admissible task. One Django case has a working environment and substantial override ambiguity, but leakage and fix-site resolution were not fully audited. Both recorded arms pass and the semantic tool is not elected. Constructed tasks therefore provide the cleanest causal apparatus here, while population validity remains open. The audit and rejection reasons are in [docs/external_validity_recon.md](docs/external_validity_recon.md).

## 3. Related work

Prior work studies missing context, automatic delivery, coherent drafts, and generation constraints. These conditions map to different points in the resolve-compress-validate chain.

| Work | Relevant lesson |
|---|---|
| [Typed Holes](https://arxiv.org/abs/2409.00921) and [LSPRAG](https://arxiv.org/abs/2510.22210) | Push types, definitions, or references when context is missing; automatic delivery removes election failure. |
| [STALL+](https://arxiv.org/abs/2406.10018) | Static analysis effects vary by language and integration phase; retrieval and semantic analysis can complement each other. |
| [CoCoGen](https://arxiv.org/abs/2403.16792) | Check a coherent draft, then retrieve context to repair project/API mismatches. This is the opportunity-conditioned regime absent from after-every-edit feedback. |
| [CodeStruct](https://arxiv.org/abs/2604.05407) | Structured reads, edits, and syntax validation improve actionability through program structure rather than type information. |
| [CompCoder](https://arxiv.org/abs/2203.05132), [type-constrained generation](https://arxiv.org/abs/2504.09246), and [RLCSF v2](https://arxiv.org/abs/2510.22907) | Compiler and server signals can rank, constrain, or train candidates even when repair-time feedback is not useful. |

Across this report and prior work, static tooling helps when it supplies missing, correct, compact, actionable information at the phase where the model can use it. The common failure modes are duplicate information, no checker opportunity, ignored or noisy delivery, and cost that exceeds the work saved.

## 4. Reproducibility and limits

From a clean clone:

```bash
python3 -m pip install -e '.[dev,analysis]'
python3 scripts/analysis/reproduce_all.py
```

The reproducer verifies the manifest, reruns retained analyzers, recomputes task-level effects, and executes the navigation manipulation checks without making model or API calls. Model runs are separate; see [evidence/protocols.md](evidence/protocols.md) before using the navigation or checker run scripts.

The main limits are:

- Static tooling does not address dynamic behavior, incorrect annotations, `Any`-heavy boundaries, environment failures, or logic outside the checker.
- Compact-retrieval tasks are synthetic. The efficient ranged-retrieval baseline now supports a within-suite effect, but natural-repository frequency and live-LSP latency remain unmeasured.
- The typed navigation outcome comes from two pilot tasks with ceilinged correctness; there is no outcome headroom or retrieval substitution to justify confirmation.
- The checker evidence combines two selected recovered workspaces with three controlled defect/clean pairs. V6 exercises explicit rejection, repair, retest, resubmission, acceptance, and a matched-clean control, but does not estimate natural opportunity prevalence, population false rejection, or draft-plus-revision cost.
- The real-repository scan found no fully admissible case, so external validity is unresolved.
- Some retained artifacts contain provenance gaps, including unavailable seed shards, incomplete server backend/version records, source-hash mismatches, and invalidated runs. Exclusion reasons and discrepancies are reported in the claim ledger and manifest.

Within these limits, the evidence supports compact retrieval against both whole-file and efficient text retrieval in the controlled suite, and the mechanistic claim that sound types sharpen semantic resolution.

## Conclusion

Language-server services can create value by resolving ambiguity, compressing retrieval, or validating a patch. The experiments demonstrate compact retrieval against both broad and efficient text reads, type-driven gains in resolver precision, and accepted recovery after gate rejection on selected checker-detectable defects with matched clean controls. They do not yet demonstrate a general navigation benefit or natural-workload checker value.

The deployment standard is the same for each service: identify a real opportunity, verify that the semantic signal changes the agent's action, and measure whether that change lowers cost or improves correctness. Availability and invocation are not outcomes. The useful integration is the smallest targeted operation that removes work or prevents an error the agent would otherwise carry forward.
