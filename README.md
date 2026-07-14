# When Do Language Servers Help Coding Agents?

**Start with cheap text search and ranged reads. Add language-server features only when a binding is genuinely ambiguous, a compact definition replaces reading a whole file, or a coherent patch contains a repairable static error. Measure whether the service changes what the agent actually does — not how often it is called.**

Language servers help when repository semantics are the bottleneck and the result changes the agent's work: resolving an ambiguous binding, replacing broad reading with a compact span, or surfacing a defect the model can repair. A correct result that neither prevents a wrong-target edit nor replaces reading is overhead.

This repository turns controlled experiments on those three jobs into practitioner guidance. It contains raw artifacts, reproducible analysis, experiment harnesses, and a technical report covering semantic retrieval, typed resolution, checker feedback, tool election, and gates.

## Evidence strength at a glance

| Claim | Status |
|---|---|
| Compact definitions cut input tokens vs. whole-file reads | **Supported, narrow** — shown on constructed tasks against whole-file retrieval |
| Typed semantic resolution picks the right target | **Mechanism supported** — precision gain shown; agent-level benefit not shown |
| Semantic navigation helps when text already exposes the target | **Not shown** — near token-neutral in the tested regime |
| Checker feedback improves outcomes | **Not shown** — improves type-clean state in two selected cases; no held-out gain |
| Submission gates prevent bad patches | **Unevaluated** — no rejection event was observed |

## Operational defaults

1. **Start with text search and ranged reads for unique, local bindings.** They are cheap and transparent when the prompt already exposes the receiver and target.
2. **Add typed semantic resolution only when text cannot identify the exact target.** Good candidates are overloads, inheritance, re-exports, factories, and same-named implementations.
3. **Use compact definitions only when they replace whole-file reads.** A correct result that does not prevent wrong-target work or replace reading is overhead.
4. **Treat checker cleanliness as a signal, not a pass/fail gate.** A type-clean patch is not the same as a correct patch.
5. **Do not deploy submission gates until they have demonstrably blocked a bad submission.** The experiments did not exercise a real rejection, so prevention is unmeasured.

## What the evidence does not yet show

- Typed resolution improved resolver precision, but we did not show an agent-level outcome gain.
- Compact definitions beat whole-file reads; their advantage over efficient grep plus ranged reads is unmeasured.
- Checker diagnostics improved an intermediate state, not behavioral correctness.
- The gate comparison logged zero rejections, so gate prevention is unevaluated.

Measure effect, not invocation: did the service replace reading, prevent a wrong-target edit, repair an actionable defect, or reject a bad submission? Optimize tool election only after the service demonstrates value when it is available.

## Evidence at a glance

| Situation | What to do | What the experiments show | Verify by measuring |
|---|---|---|---|
| **Binding is local, visible, and unique** | Text search plus ranged reads | Navigation is near token-neutral when text already exposes the target. The agent can find the file without semantic help ([C6](evidence/claim_ledger.md#c6), [C9](evidence/claim_ledger.md#c9)). | Wrong-file edits, target reads avoided, total tokens |
| **Overloads, inheritance, factories, or re-exports make the target ambiguous** | Typed semantic resolution | Sound types let Pyrefly distinguish the correct implementation from same-named alternatives. The two-task pilot still reread every target and gained no correctness or cost improvement ([C15](evidence/claim_ledger.md#c15), [C24](evidence/claim_ledger.md#c24)). | Wrong-target work prevented, retrieval reduced, not just tool calls |
| **A compact span can replace a whole-file read** | Definition or enclosing-method span | Input tokens fell 3.5–4.7x at unchanged success when compact retrieval replaced whole-file reads. The live-first hybrid shows the same direction ([C1](evidence/claim_ledger.md#c1), [C4](evidence/claim_ledger.md#c4)). | Confirm the agent does not reread the full file |
| **Coherent patch has checker-detectable errors** | Show new relevant checker errors after the patch | One additional type-clean result in two selected workspaces; no held-out correctness gain ([C26](evidence/claim_ledger.md#c26)). | Held-out tests pass and total cost including diagnostics | The draft is incoherent or the error is not repairable |
| **Bad submission prevention** | **Unevaluated** — do not deploy until a gate blocks a real bad submission | No valid gate contrast; zero rejections observed ([C14](evidence/claim_ledger.md#c14), [C26](evidence/claim_ledger.md#c26)) | Controlled experiment in which the gate rejects bad submissions that would otherwise be accepted | You have not observed the gate block a real bad submission |
| **Useful service is available but rarely chosen** | Improve tool description or policy | Prompting and cost-reward training raise election in model-specific runs ([C2](evidence/claim_ledger.md#c2), [C3](evidence/claim_ledger.md#c3)). | Higher election retains correctness and lowers total cost | The service has not first shown value when available |

**Open integrations:** gate prevention is unmeasured because the gate arm never reached a submission decision and logged zero rejections ([C14](evidence/claim_ledger.md#c14), [C26](evidence/claim_ledger.md#c26)). Candidate reranking, constrained generation, and structured edits are discussed in related work but have no direct repository experiment.

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

Model execution is separate from reproduction. See [evidence/protocols.md](evidence/protocols.md) before using `scripts/run_navigation_pilot.sh`, `scripts/run_navigation_confirmation.sh`, `scripts/run_checker_paired.sh`, or `scripts/run_checker_case_series.sh`. No paid API run is authorized by the protocol.

## Repository map

| Path | Purpose |
|---|---|
| `REPORT.md` | Practitioner guidance and technical report |
| `evidence/` | Claim ledger, protocols, manifest, hashes, and provenance |
| `runs/agent/` | Archived raw model results |
| `runs/pilot/` | Pilot and case-series results |
| `runs/protocol/` | Mechanical validation and frozen selection artifacts |
| `scripts/analysis/` | Reproducers and statistical analysis |
| `scripts/experiments/` | Navigation and paired-checker harnesses |
| `scripts/realbench/` | Real-repository candidate scanning and dispatch experiments |
| `scaffold/` | Agent loop, tools, and workspace environments |
| `docs/real_repo_progress.md` | Preserved chronological research log, not the final claim source |
