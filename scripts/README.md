# scripts/

The fast artifact command is:

```bash
python3 scripts/analysis/reproduce_all.py
```

It makes no model/API calls. It verifies the evidence manifest, reruns the historical analyzers and
task-level reanalysis, audits the checker artifacts, and revalidates the navigation manipulation splits.

## New causal protocols

- `experiments/navigation_tasks.py` generates deterministic typed/erased stub pairs over byte-identical
  runtime code and enforces all-key contract, type-cleanliness, widening, gold, leakage, override-count,
  and strict live-Pyrefly manipulation gates.
- `experiments/run_navigation.py` runs the core automatic-result cells, the metadata-supplied buggy-span
  actionability control, and typed deployment/election cells, recording localization, substitution, tokens,
  calls, turns, and latency.
- `experiments/diagnostics.py` provides uncapped structured, target-scoped Pyrefly diagnostic deltas.
- `experiments/checker_paired.py` generates or imports frozen natural drafts, then forks identical control,
  coherent-patch diagnostic, gate, and noisy checker revisions.
- `run_navigation_pilot.sh`, `run_navigation_confirmation.sh`, and `run_checker_paired.sh` are separate
  local-model drivers. The confirmation script is intentionally not part of fast reproduction.

## Historical suites and analyzers

- `synth_tasks_effic*.py`, `synth_mf.py`, `sft_lora.py`, and `grpo_cost.py` implement the controlled
  whole-file versus compact-definition retrieval and policy-training studies.
- `realbench/dispatch_tasks.py` and `realbench/local_dispatch.py` implement the historical leaky dispatch
  suite. It is preserved but no longer treated as a valid typed/erased causal experiment.
- `synth_tasks_authoring.py` implements the historical unpaired authoring suite; its after-every-edit arm
  is retained only as a noisy integration baseline.
- `synth_tasks_gapd2.py` and `synth_tasks_runtime.py` provide the checker-inference and execution ceilings.
- `analysis/stats.py` reproduces the 7B retrieval/training tables.
- `analysis/effic_real_stats.py` handles local and API schemas, drops sign-test ties, and reports task
  direction; `analysis/task_level_effects.py` averages seeds within task and bootstraps tasks.
- `analysis/analyze_dispatch.py`, `analyze_authoring.py`, `analyze_inference.py`, and
  `../analyze_runtime.py` reproduce scoped historical observations.
- `analysis/analyze_navigation.py` implements paired task effects and the preregistered 0.90–1.10
  task-weighted token-ratio equivalence test. `analyze_checker_paired.py` includes task-weighted total
  draft-plus-revision cost per accepted correct patch.

## Drivers and tools

Every `run_*.sh` sources `common.sh`, derives the repository root from its own path, and honors
`PYTHON`. Cache/offline variables are caller-controlled. Pyrefly discovery is implemented in
`scaffold/tooling.py`; `realbench/pyrefly_nav.py` remains self-contained because it is copied alone into
SWE-bench containers.

`build_manifest.py` records hashes, raw configs, actual seeds, integration modes, source-run provenance,
and known metadata warnings. Historical result JSON is never silently rewritten.
