# Real-repo generalization experiment: plan, validity invariant, harness spec

> **Historical note.** This was the draft plan for the real-repo generalization pass as of 2026-06-30.
> It is preserved as design provenance, not as the current project state. The follow-up work moved through
> `docs/real_repo_progress.md` into the report's current conclusion: the whole-file-read efficiency result
> is scoped to that baseline, realistic grep/ranged-read retrieval removes most of the advantage, and the
> stable reframe is that readable, correct types are the useful artifact.

## Why

The report's efficiency result (a go-to-definition action cuts input tokens 3.5 to 4.7x at equal
success) is measured on **real source but constructed tasks**: small `target.py` stubs calling into
vendored library code, with symbols hand-picked for non-obvious signatures. The main reviewer attack is
that this is not yet evidence about **messy production codebases** (cross-file edits, methods, classes,
imports/re-exports, aliases, project-specific types, project-wide symbol reasoning). This experiment
tests whether the **efficiency win generalizes to real bug-fix tasks with real tests**, and, as a
secondary target, whether the **information null** holds there too.

Primary target: **efficiency generalization** (does `<defn>` still cut tokens at matched success on
real cross-file tasks?). It is the headline result, the one the reviewer most wants generalized, and the
one that is statistically easiest to show. Secondary target: the information null (does `check_types`
raise success?), which on real tasks needs real statistical power (SWE-bench single-run pass@1 SD is
~1.5 to 3pp; a null needs enough seeds), so we treat it as a stretch.

## Design: the same three-condition matrix, on real tasks

Hold the model and task fixed; toggle the tool. Score **success and input tokens**.

| condition | tools exposed | isolates |
|---|---|---|
| **R** read-only | read_file, edit, run_tests | baseline retrieval cost |
| **D** go-to-definition | + defn, find_references | efficiency: tokens vs R at matched success |
| **I** info | + check_types (pyrefly diagnostics) | does LSP information raise success over D/R |

Two frontier models (`claude-sonnet-4.5`, `deepseek-chat-v3.1`), reusing the `api_agent.py` tool-calling
harness. Election is observed, not forced: the model chooses whether to use `<defn>`/`check_types`, so
we also read off the election rate on real code (the report shows ~100% election on the synthetic
obscure suite; this checks it survives real repos).

Success = the task's `FAIL_TO_PASS` tests pass and `PASS_TO_PASS` still pass (SWE-bench oracle). Cost =
input tokens to solve. Efficiency is `tokens(R) - tokens(D)` at matched success; the information effect
is `success(I) - success(D)`.

## Source

**SWE-bench Verified** (`princeton-nlp/SWE-bench_Verified`, 500 human-filtered tasks) as the reliable
base: real repos, real issues, gold patch, and a curated FAIL_TO_PASS / PASS_TO_PASS oracle, with
`environment_setup_commit` and official per-task Docker images for reproducible test execution.

Contamination caveat, stated honestly and NOT relied on: these repos and issues predate the models'
training and may be memorized. We do **not** claim a contamination benefit. If we want to make a
contamination-controlled claim we must validate it **per model** in our matrix explicitly (e.g. probe
each model for verbatim recall of the gold patch / issue), which we have not done. SWE-rebench
(post-cutoff-oriented) is a future option only under that same per-model validation.

## Validity / selection invariant

SWE-bench tasks are not built around the read-vs-defn cost gap, so most are unsuitable. A task is
**admissible** only if it can actually exercise the efficiency question. Criteria (computable from the
gold patch + a source-only checkout, no dependency install):

- **S1 cross-file dependency.** The gold fix, in file A, references a symbol S (function, method,
  class, or type) whose definition resolves to a *different* file B in the repo (via the AST
  `SymbolResolver`). If the fix only touches symbols local to A, `<defn>` has nothing to fetch.
- **S2 non-trivial symbol.** S is not a one-line, obvious, or guessable top-level helper: it is a
  method, a class, a project-specific type, or a re-exported/aliased name. (Kind tagged from the AST.)
- **S3 expensive counterfactual.** File A (or B, whichever the agent must read to obtain S) is large
  (>= ~300 lines), so a whole-file read is genuinely more expensive than a definition span.
- **S4 test discriminates.** FAIL_TO_PASS is non-empty and, on a clean checkout, fails before the fix
  and passes after the gold patch (SWE-bench guarantees the intent; we re-verify per task).
- **S5 tractable environment.** The task's tests can be run (official Docker image pulls, or a
  source-only repo whose FAIL_TO_PASS does not need heavy native deps). Tasks whose env we cannot stand
  up are dropped and **logged** (no silent truncation).

S1-S3 are a metadata/AST scan (cheap, no env). S4-S5 need the env and are checked only for tasks that
pass S1-S3. The scan reports, per task, which criteria pass, so selection is auditable rather than
hand-waved. Target output: a ranked candidate pool of ~20-30, from which we hand-audit ~15.

This invariant is the analogue of the synthetic suites' V1-V4 (gapd2) and W1-W4 (runtime): it is what
keeps the real-repo suite from being rigged-by-selection, and it is authored here rather than delegated.

## Harness

- `scaffold/real_env.py::RealRepoEnv` (recovered from git history; it already exposes `read_file`,
  `goto_definition`, `find_references`, `pyrefly_diagnostics` = check_types, `run_tests`, `apply_edit`
  over a checked-out repo, with a live `pyrefly lsp` daemon and the AST `SymbolResolver` fallback).
- `scripts/realbench/swe_loader.py` — load a SWE-bench task, shallow-checkout the repo at
  `base_commit`, apply the `test_patch` (which adds the oracle tests), expose the F2P/P2P test
  selection to `run_tests`.
- `scripts/realbench/select.py` — the S1-S3 selection scanner over the dataset, emitting the ranked
  candidate pool with per-criterion evidence.
- Test execution for S4/S5 and the matrix uses the official SWE-bench Docker images
  (`docker` is available) so we do not re-fight per-task Python/dep setup by hand.

## What is NOT decided / open risks

- **Env heaviness.** Standing up test execution for arbitrary tasks is the known cost (per-task Docker
  images are multi-GB; the log records prior pain here). The selection scan (S1-S3) is cheap and runs
  first, so we only pay env cost for already-admissible candidates.
- **Statistical power.** The information null on real tasks needs enough seeds (SD ~1.5-3pp). Efficiency
  (a token ratio at matched success) is far cheaper to show, which is why it is primary.
- **Election vs forced.** We observe election. If frontier models do not spontaneously use `<defn>` on
  real repos, that is itself a finding (the election result, on real code).

## Delegation note

Codex was attempted for the build (Ian's suggestion) and was unreliable in this environment (it
web-searched to answer a local file-count in read-only mode, and hung past two minutes on a trivial
workspace-write task). Kimi has no CLI installed. Per the agreed fallback, the build proceeds solo.
