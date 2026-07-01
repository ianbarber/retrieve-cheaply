# Real-repo experiment: overnight progress (2026-06-30 → 07-01)

Morning summary of what got built and what it found. Design + validity invariant are in
`docs/real_repo_plan.md`. No matrix runs yet (that needs the env-setup step below); this pass built and
validated the pipeline and produced the auditable candidate pool.

## What's built and working

1. **Harness** — recovered `scaffold/real_env.py` (`RealRepoEnv` + AST `SymbolResolver`) from git
   history. It already exposes `read_file`, `goto_definition`, `find_references`,
   `pyrefly_diagnostics` (= check_types), and `run_tests` over a checked-out repo, with a live
   `pyrefly lsp` daemon and AST fallback. Imports cleanly and passes its self-check in the current tree.
2. **Loader** — `scripts/realbench/swe_loader.py`: loads SWE-bench Verified, keeps a per-repo blobless
   clone cache, checks a task out at `base_commit`, applies the task's `test_patch`, builds the oracle
   pytest command over FAIL_TO_PASS/PASS_TO_PASS. Validated end-to-end on a requests task in ~9s.
3. **Selection scanner** — `scripts/realbench/select.py`: implements the S1–S3 validity invariant
   (cross-file dependency / non-trivial symbol / expensive counterfactual) purely from the gold patch +
   an AST resolve over the checked-out source (no dependency install). Test files are excluded from
   resolution so a symbol never resolves to a test.
4. **Ranker** — `scripts/realbench/rank.py`: merges the per-repo scans into one ranked candidate pool
   (`runs/realbench/candidates.json`).

## What the scan found

Scanning ~22 tasks per repo across the SWE-bench Verified repos, **42 of 183 scanned tasks are
admissible** (pass S1&S2&S3), across 7 repos (sympy 10, xarray 10, matplotlib 6, astropy 5, sphinx 5,
django 4, pytest 2) — plenty to hand-audit ~15 from. The admissible tasks have exactly the cost-gap
structure the experiment needs: the fix, in file A, depends on a symbol defined in a **large** other
file B, so a read-only agent pays to read B whole while `<defn>` fetches just the span. Top examples:

| task | cross-file symbol | defined in | edits |
|---|---|---|---|
| astropy-13398 | `CartesianRepresentation` (type) | representation.py (3474L) | builtin_frames/__init__.py |
| sympy-13878 | `Zero` (type) | core/numbers.py (3843L) | stats/crv_types.py |
| matplotlib-20859 | `Axes` (type) | axes/_axes.py (8151L) | legend.py |
| xarray-7229 | `Dataset` (import) | core/dataset.py (9214L) | core/computation.py |
| django-11149 | `ManyToManyField` (type) | fields/related.py (1647L) | admin/options.py |
| sphinx-11510 | `Sphinx` (type) | application.py (1362L) | directives/other.py |

The full ranked pool with per-criterion evidence (which symbols, which files, sizes, F2P count) is in
`runs/realbench/candidates.json` (per-repo scans in `runs/realbench/scan/`). `requests` and the early
`pytest` tasks correctly scored zero: those fixes are single-file with only stdlib/local symbols, so
there is genuinely no cost gap to measure — the scanner is discriminating, not just permissive.

## Honest next steps (for discussion / next session)

1. **Hand-audit the top ~15** from `candidates.json`. The scanner is a ranked shortlist, not the final
   word; a human confirms the fix truly needs the cross-file symbol and that the task is clean.
2. **S4/S5 environment setup.** To actually run the matrix we need to execute each task's tests, which
   needs the repo's dependencies. The plan is the official SWE-bench Docker images (docker is
   available). This is the known-heavy step; the selection scan runs first precisely so we only pay env
   cost for already-admissible tasks. Not started.
3. **Matrix runner.** Adapt the `api_agent.py` rollout loop to drive `RealRepoEnv` under the three tool
   conditions (R read-only / D +defn / I +check_types), recording success (F2P pass) and input tokens.
   The env interface matches `MultiFileEnv` closely, so this is a moderate adaptation, not a rewrite.
   Not started (deferred until the env step and the audited task set exist).
4. **Contamination.** Per the agreed constraint, we do not claim a "post-training-cutoff" benefit for
   SWE-bench Verified. If we want a contamination-controlled claim, validate it **per model** in our
   matrix explicitly first.

## Notes

- Codex (Ian's suggestion) was tried for the build and was unreliable in this environment: in read-only
  mode it web-searched to answer a local file count, and in workspace-write mode it hung past two
  minutes on a trivial task. Kimi has no CLI installed. Per the agreed fallback, the build was done solo.
- Cloned repos live under `runs/realbench/repos/` (gitignored, large). The scan JSONs and
  `candidates.json` are small and committed.
