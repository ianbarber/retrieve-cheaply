# When Do Language Servers Help Coding Agents?

**Start with cheap text search and ranged reads. Add language-server features when a binding is genuinely ambiguous, a compact definition replaces search and reading, or a coherent patch contains a repairable static error. Measure whether the service changes what the agent actually does — not how often it is called.**

Language servers help when repository semantics are the bottleneck and the result changes the agent's work: resolving an ambiguous binding, substituting a compact span for retrieval, or surfacing a defect the model can repair. A correct result that neither prevents wrong-target work nor replaces retrieval is overhead.

This repository turns controlled experiments on those three jobs into practitioner guidance. It contains raw artifacts, reproducible analysis, experiment harnesses, and a technical report covering semantic retrieval, typed resolution, checker feedback, tool election, and gates.

## Evidence strength at a glance

| Claim | Status |
|---|---|
| Compact definitions cut tokens vs. efficient text retrieval | **Supported in a controlled suite** — 1.30x fewer total tokens with equal success across 11 tasks |
| Typed semantic resolution picks the right target | **Mechanism supported** — precision gain shown; agent-level benefit not shown |
| Semantic navigation helps when text already exposes the target | **Not shown** — near token-neutral in the tested regime |
| One-shot checker feedback improves outcomes | **Not shown** — valid selected cases change checker state without improving joint outcome; the earlier hidden-defect comparison is invalid |
| Submission gates recover checker-detectable bad completions | **Supported in a controlled pilot** — 2/2 reached bad completions were rejected, repaired, resubmitted, and accepted; 0/3 matched clean drafts were rejected |

## Operational defaults

1. **Start with text search and ranged reads for unique, local bindings.** They are cheap and transparent when the prompt already exposes the receiver and target.
2. **Add typed semantic resolution only when text cannot identify the exact target.** Good candidates are overloads, inheritance, re-exports, factories, and same-named implementations.
3. **Use compact definitions when they replace search and reading.** Against a grep-plus-ranged-read interface, definitions cut mean total tokens from 1,602 to 1,235 and avoided every defining-file reread in the controlled suite.
4. **Deliver diagnostics at an actionable boundary.** The v5 one-shot comparison is invalid because user-observation action tags crossed the parser boundary. In corrected v6, the two defects that survived to completion were repaired only after the gate rejected them.
5. **Stage gates around accepted yield, not cleanliness alone.** Both reached bad completions were repaired, explicitly resubmitted, and accepted; all three matched clean drafts passed the gate on their first submission. Measure the same outcomes on a larger natural cohort before deployment.

## What the evidence does not yet show

- Typed resolution improved resolver precision, but we did not show an agent-level outcome gain.
- The compact-definition result uses constructed tasks and static AST lookup; real-repository and live-LSP generalization remain unmeasured.
- One-shot checker context has not improved held-out correctness in a valid controlled comparison.
- The gate result uses three selected defects, three matched clean controls, one model, and one seed. Natural opportunity prevalence and population rejection precision remain unmeasured.

Measure effect, not invocation: did the service replace reading, prevent a wrong-target edit, repair an actionable defect, or reject a bad submission? Optimize tool election only after the service demonstrates value when it is available.

## Evidence at a glance

| Situation | What to do | What the experiments show | Verify by measuring | Do not use when |
|---|---|---|---|---|
| **Binding is local, visible, and unique** | Text search plus ranged reads | Navigation is near token-neutral when text already exposes the target. The agent can find the file without semantic help ([C6](evidence/claim_ledger.md#c6), [C9](evidence/claim_ledger.md#c9)). | Wrong-file edits, target reads avoided, total tokens | The needed code is already in context |
| **Overloads, inheritance, factories, or re-exports make the target ambiguous** | Typed semantic resolution | Sound types let Pyrefly distinguish the correct implementation from same-named alternatives. The two-task pilot still reread every target and gained no correctness or cost improvement ([C15](evidence/claim_ledger.md#c15), [C24](evidence/claim_ledger.md#c24)). | Wrong-target work prevented, retrieval reduced, not just tool calls | Text already identifies the exact target |
| **A compact span can replace search and reading** | Definition or enclosing-method span | Definitions retained 11/11 success while cutting mean total tokens from 1,602 to 1,235 versus grep plus ranged reads; they were cheaper on 10/11 tasks and triggered no defining-file rereads ([C27](evidence/claim_ledger.md#c27)). Historical whole-file contrasts are larger ([C1](evidence/claim_ledger.md#c1)). | Retrieval-response bytes, total tokens, and post-definition rereads | The result is followed by the same file reads |
| **Coherent patch has checker-detectable errors** | Show new relevant checker errors at completion, with a repair loop | Earlier one-shot context does not improve joint outcome. In v6, the gate rejects both checker-detectable defects that survive to completion and elicits accepted repair ([C26](evidence/claim_ledger.md#c26), [C29](evidence/claim_ledger.md#c29)). | Diagnosed-location edits, held-out pass, and total diagnostic cost | The draft is incoherent or the diagnostic is not repairable |
| **Bad submission prevention** | Use a staged acceptance gate with an explicit repair-and-resubmit loop | Of three seeded defects, one self-repairs before submission; the other two are rejected, repaired, retested, resubmitted, and accepted clean. Three matched clean drafts pass on the first submission ([C29](evidence/claim_ledger.md#c29)). | False rejections, resubmission rate, accepted-correct yield, total cost | You cannot tolerate abstention or have not measured rejection precision |
| **Useful service is available but rarely chosen** | Improve tool description or policy | Prompting and cost-reward training raise election in model-specific runs ([C2](evidence/claim_ledger.md#c2), [C3](evidence/claim_ledger.md#c3)). | Higher election retains correctness and lowers total cost | The service has not first shown value when available |

**Open integrations:** the gate now demonstrates controlled accepted-correct recovery and a matched-clean negative control, but not natural-workload prevalence or population value ([C29](evidence/claim_ledger.md#c29)). Candidate reranking, constrained generation, and structured edits are discussed in related work but have no direct repository experiment.

## Read the work

- [REPORT.md](REPORT.md) presents the practitioner guide, evidence, limitations, and related work.
- [evidence/claim_ledger.md](evidence/claim_ledger.md) maps every important claim to its artifacts and evidence status.
- [evidence/protocols.md](evidence/protocols.md) records the experiment protocols, stopping gates, and execution status.
- [evidence/manifest.json](evidence/manifest.json) records hashes, model metadata, integration modes, and provenance warnings.

The claim ledger includes excluded and invalidated results for auditability, and marks evidence as missing, confounded, or unsupported where appropriate.

## Reproduce the analysis

Python 3.10+ is required:

```bash
python3 -m pip install -e '.[dev,analysis]'
python3 scripts/analysis/reproduce_all.py
```

The reproducer verifies the manifest, reruns the retained analyzers, recomputes task-level effects, and reruns the navigation mechanical checks. It uses committed artifacts and makes no model or API calls. Pyrefly is discovered through `STREAMS_PYREFLY`, `PYREFLY_BIN`, `PATH`, `.venv/bin`, or `.venv-streams/bin`.

Model execution is separate from reproduction. See [evidence/protocols.md](evidence/protocols.md) before using `scripts/run_navigation_pilot.sh`, `scripts/run_navigation_confirmation.sh`, `scripts/run_checker_paired.sh`, `scripts/run_checker_case_series.sh`, `scripts/run_checker_hidden.sh`, or `scripts/run_checker_gate_v2.sh`. No paid API run is authorized by the protocol.

## Repository map

| Path | Purpose |
|---|---|
| `REPORT.md` | Practitioner guidance and technical report |
| `evidence/` | Claim ledger, protocols, manifest, hashes, and provenance |
| `runs/agent/` | Archived raw model results |
| `runs/pilot/` | Pilot and case-series results |
| `runs/protocol/` | Mechanical validation and frozen selection artifacts |
| `scripts/analysis/` | Reproducers and statistical analysis |
| `scripts/experiments/` | Retrieval, navigation, and paired-checker harnesses |
| `scripts/realbench/` | Real-repository candidate scanning and dispatch experiments |
| `scaffold/` | Agent loop, tools, and workspace environments |
| `docs/real_repo_progress.md` | Preserved chronological research log, not the final claim source |
