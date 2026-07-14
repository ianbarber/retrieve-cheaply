# When Do Language Servers Help Coding Agents?

This repository studies where semantic retrieval, types, and checker feedback help coding agents, where
they do not, and how to integrate them without adding redundant context or latency. It contains raw
experiment artifacts, reproducible analysis, controlled experiment harnesses, and a practitioner-oriented
technical report.

Language servers expose semantic retrieval, name resolution, diagnostics, and structured code operations.
This project evaluates how type information affects those services and how agents consume them through
on-demand retrieval, pushed context, patch feedback, gates, reranking, and training.

## Practitioner takeaways

1. **Use text search and ranged reads for unique, local bindings.** They are cheap and transparent.
2. **Use typed semantic resolution for genuinely non-lexical ambiguity.** It is most relevant for overloads,
   inheritance, re-exports, factories, and same-named implementations.
3. **Keep semantic retrieval only when it replaces work.** A definition result followed by the same target
   read is overhead, not compression.
4. **Run target-scoped diagnostic deltas on coherent patches.** Checker cleanliness is useful intermediate
   evidence, not behavioral correctness.
5. **Gate only when telemetry demonstrates prevention.** A useful gate must stop a defect the ungated agent
   would actually submit, or help turn it into an accepted clean and correct patch.

The recurring test is whether a tool supplies unique, actionable information at a real opportunity and
replaces enough work to justify its token, latency, and integration cost.

## Evidence at a glance

| Finding | Status | What it supports |
|---|---|---|
| Compact definition retrieval reduces input tokens 3.5-4.7x at unchanged success when the alternative is a whole-file library read. The treatment is cheaper on 11/11 local-27B tasks, 11/11 Sonnet tasks, and 10/11 DeepSeek tasks. | **Supported, narrow** | Compact retrieval can be valuable when it replaces large reads. The three-model comparison uses a static AST resolver; live-server evidence comes from a separate hybrid suite. |
| Retrieval-tool election changes with prompting, on-policy relabeling, and cost-reward training. | **Supported, model/policy-specific** | Prove that supplied context is useful before investing in tool-election prompting or training. |
| In the sound typed/erased navigation pilot, all cells pass, typed automatic context falls within the token margin on two tasks, erased context costs more, and every automatic result is followed by a target read. Lookup itself takes about six seconds per task in this harness. | **Boundary evidence** | Types improve resolver precision, but this pilot does not show useful navigation compression or a correctness gain. |
| On two selected checker-positive workspaces, one-shot diagnostics produce one additional type-clean final workspace but no held-out or accepted-clean-correct gain, while adding revision tokens. | **Descriptive, selected cases** | Checker state can improve without product outcome improvement. Prevalence and end-to-end value remain unknown. |
| The local gate arm diverges from control before the gate can act and contains no rejection event. | **Invalid for causal comparison** | Gate prevention remains an open question and external design recommendation, not a repository result. |

Semantic tools help when they resolve otherwise missing ambiguity, compress retrieval, or catch actionable
defects, and when the agent integration converts that signal into lower-cost correct work.

## Read the work

- [REPORT.md](REPORT.md) presents the argument, evidence audit, limitations, related work, and confidence-labeled decision table.
- [evidence/claim_ledger.md](evidence/claim_ledger.md) maps every important claim to its artifacts and evidence status.
- [evidence/protocols.md](evidence/protocols.md) records the experiment protocols, stopping gates, and execution status.
- [evidence/manifest.json](evidence/manifest.json) records hashes, model metadata, integration modes, and provenance warnings.

The claim ledger includes excluded and invalidated results for auditability, and marks evidence as missing,
confounded, or unsupported where appropriate.

## Reproduce the analysis

Python 3.10+ is required:

```bash
python3 -m pip install -e '.[dev,analysis]'
python3 scripts/analysis/reproduce_all.py
```

The reproducer verifies the manifest, reruns the retained analyzers, recomputes task-level effects, and
reruns the navigation mechanical checks. It uses committed artifacts and makes no model or API calls.
Pyrefly is discovered through `STREAMS_PYREFLY`, `PYREFLY_BIN`, `PATH`, `.venv/bin`, or
`.venv-streams/bin`.

Model execution is separate from reproduction. See [evidence/protocols.md](evidence/protocols.md) before
using `scripts/run_navigation_pilot.sh`, `scripts/run_navigation_confirmation.sh`,
`scripts/run_checker_paired.sh`, or `scripts/run_checker_case_series.sh`. No paid API run is authorized by
the protocol.

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
