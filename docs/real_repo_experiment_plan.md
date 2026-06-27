# Real-repository experiment plan: does cheap `<defn>` retrieval generalize?

## Scope and link to the current work

The headline result in `PAPER.md` is trained and evaluated on synthetic multi-file tasks: a large `biglib.py` contains one needed symbol, and `<defn sym>` returns the same information as `<read path="biglib.py"/>` for roughly 1/70 of the tokens. The open limitation is whether the learned cheap-retrieval preference survives in real repositories, where symbol resolution is ambiguous, methods live inside classes, imports are re-exported, and the "needed symbol" is not pre-labelled.

This plan describes a small, feasible real-repo arm that reuses the existing scaffold (`scaffold/stream_agent.py`, `scaffold/mock_env.py`, `scripts/sft_lora.py`) and the established on-policy relabel recipe (`scripts/run_relabel2.sh`).

---

## 1. Benchmark choice

**Recommendation:** start with **RefactorBench**, a benchmark of multi-file refactoring tasks on 9 popular Python repositories. Tasks are verified by custom AST-based unit tests rather than hidden fail-to-pass tests, which makes the evaluation harness lighter than SWE-bench and the patch semantics clearer.

**Why RefactorBench?**
- Real repository code with real refactoring goals.
- Tasks inherently require reading existing code before editing, so there is a natural retrieval phase to measure.
- AST-based verification avoids the heavy Docker harness of SWE-bench.
- It is smaller and more controlled than SWE-bench, which fits our goal of testing a *specific retrieval preference* rather than beating an issue-resolution leaderboard.

**Why not run all of RefactorBench?** Cost and focus. We will filter down to **15–20 tasks** where the refactor depends on understanding one or a few external symbols defined in large files, giving a clean `<defn>` vs `<read>` cost gap.

**Complement / follow-up:** after the RefactorBench arm, run a smaller **hand-curated typed-library issue** set (10–20 issues from `pydantic`, `fastapi`, `httpx`, `sqlalchemy` 2.0, `mypy`, `black`, `typer`, `structlog`, or `python-attrs/attrs`). These repos have high annotation density, so pyrefly resolves cleanly and the experiment isolates the *retrieval preference* from resolver robustness.

**Fallbacks if RefactorBench proves unsuitable:** SWE-Gym Lite, FEA-Bench, or a curated mini-benchmark from small/medium repos such as `pallets/click` or `encode/starlette`.

---

## 2. Task selection criteria

A task is suitable for measuring `<defn>` vs `<read>` savings when:

1. **The gold patch is small and localized.**
   - ≤3 files edited, ≤30 lines changed.
   - Prefer single-file edits for the first experiment; multi-file blast-radius is a separate variable.

2. **The fix depends on understanding one external symbol.**
   - The buggy file imports or references a class/function from a *large* non-editable module.
   - The issue or failing test names the symbol, or the failing traceback points to it.

3. **There is a material cost gap.**
   - The defining file is at least ~200 lines, preferably 500+.
   - `<defn sym>` returns ≤10% of the file's tokens.

4. **The symbol is resolvable by pyrefly.**
   - Avoid tasks where the needed behavior is hidden behind dynamic dispatch, `getattr`, star imports, or C extensions.
   - Run a resolver-coverage audit: for each candidate task, ask pyrefly for `textDocument/definition` on the symbol the patch touches. Keep only tasks where pyrefly returns the correct span (validated against the gold patch or `inspect.getsource`). Report the resolver hit rate as a metadata column.

5. **Baseline solvability.**
   - The untrained 7B agent should solve at least some seeds with `<read>` available, so we can compare tokens at matched outcome.

6. **No environment/build hacks.**
   - Skip tasks that require compiling C extensions, patching `setup.py`, or non-Python changes.

**Selection pipeline:** load the SWE-bench Verified JSON → filter by patch size → compute the largest file referenced by the failing test → keep tasks where the referenced file is large and the patch touches a call/attribute of an imported symbol → manual review the final 20.

---

## 3. Action space adaptation

The current `<defn sym="NAME"/>` only resolves top-level module names via a static AST resolver. Real repos need richer symbol syntax and a real language server.

### Symbol specification

`<defn>` should accept qualified symbols:

- `ClassName`
- `module.ClassName`
- `ClassName.method_name`
- `module.ClassName.method_name`
- top-level `function_name`

If a method name is given without a class, return `(no definition found)` to force disambiguation by the model.

### Use-site resolution

For ambiguous cases, optionally support:

```xml
<defn sym="method_name" file="src/pkg/foo.py" line="42" col="8"/>
```

The `file/line/col` attributes point to a use-site; the backend calls `textDocument/definition` at that position. This is especially useful for overloaded methods and imports that shadow names.

### Backend resolver

Pyrefly is a type checker, but it performs aggressive inference even on unannotated code
(unlike mypy, which often defaults to `Any`). That means it may resolve more symbols on
SWE-bench-style code than a strict annotation-only checker would. We should still measure
resolver coverage explicitly rather than assuming it works.

- **Primary:** drive a live `pyrefly lsp` daemon per task, reusing `scripts/validate_pyrefly_lsp.py::LspClient`.
- **Fallback:** static AST/CST resolver over the checked-out repo.
- **Coverage audit:** before running the full experiment, run `pyrefly coverage report` (or
  the LSP definition call) on a sample of candidate symbols and record the hit rate. Only
  include tasks where the needed symbol resolves correctly.
- **Return format:** the full source span of the resolved definition (same shape as `goto_definition` today).
- **Sequential execution:** because pyrefly daemons deadlock under concurrency, one daemon per rollout, killed before the next task.

### `<read>`

Return a numbered, editable view of the requested file, truncated to ~16k tokens / 250 lines to avoid context overflow. The file view must be line-numbered so the existing `<edit path="..." lines="START-END">` action continues to work.

### `<findrefs>`

Keep the current `textDocument/references` wrapper, returning a list of `path:line` sites.

### Edit action

Start with line-range edits (`edit_mode="line"`). If real-repo patches turn out to need whole-function replacements, also allow `SEARCH/REPLACE/END`.

---

## 4. Coverage and boundary: how to decide "definition-sufficient"

We no longer have task labels. Use a **two-phase empirical boundary**:

1. **Harvest phase:** run every candidate task with `--force-lsp` (reads of non-editable files denied). Tasks that the untrained agent solves mostly via `<defn>` are strong candidates for definition-sufficient training demos.

2. **Post-SFT evaluation phase:** the trained model's own read decisions become the boundary signal.
   - If the trained model uses `<defn>` first and solves → task is definition-sufficient for that seed.
   - If it reads first and solves → task is a boundary success.
   - If it reads and fails, or defns and fails → unresolved.

For reporting, split results into:
- **Def-sufficient subset:** tasks where the trained policy used `<defn>` and solved.
- **Boundary subset:** tasks where the trained policy read and solved.
- **Unresolved:** everything else.

This is the same "model judges coverage per-instance" idea tested in §5.6 of `PAPER.md`, but now applied to real repos.

**Optional helper:** train a lightweight coverage classifier from the harvest trajectories. Features: issue text, failing-test names, first `<defn>` result length, whether the defn span references further unresolved names. Use it only to stratify analysis, not to gate training.

---

## 5. Metrics and controls

### Conditions

1. **Default 7B** – no adapter, no extra prompt.
2. **Explicit-prompt 7B** – append the `preferlsp` steer hint used in `scripts/synth_mf.py`.
3. **Trained LoRA 7B** – on-policy relabel SFT.
4. *(Optional)* **Read-only trained 7B** – SFT on read-first trajectories to isolate the cost preference from retrieval itself.

### Metrics per rollout

- `pass@1` from the repo's test command.
- `<defn>` use rate (% of rollouts with ≥1 real `<defn>` that found a definition).
- `<read>` count and rate.
- Input tokens, output tokens, total tokens.
- Turns and edit count.
- Rework ratio and n_edits from the env.

### Aggregated comparisons

- **Matched-outcome token comparison:** restrict to tasks both the base and trained policy solve; compare mean input tokens.
- **McNemar exact test** on pass@1.
- **Paired sign test** on input tokens.
- Report by subgroup (definition-sufficient vs boundary).

---

## 6. Data collection and training

### Harvesting on real-repo tasks without labels

Use the same on-policy relabel recipe as `scripts/run_relabel2.sh`, but split the harvest into two modes:

**Mode A – force_lsp (cheap-action demos):**
- Run with `--force-lsp --relabel --save-sft`.
- Reads of non-editable files are denied; the model is redirected to emit `<defn>` itself.
- Keep only resolved trajectories where a real `<defn>` returned a found definition.
- This produces the "definition-sufficient" half of the training mix.

**Mode B – reads allowed (boundary demos):**
- Run the same tasks without `--force-lsp`, with `--save-sft`.
- Keep resolved trajectories where the model used `<read>` first (or at all) on a large file.
- This produces the "read-when-needed" half of the training mix.

The combined set is fed to `scripts/sft_lora.py`. The existing `is_clean_teacher()` filter already does the right thing: it keeps resolved trajectories with a real `<defn>`/`<findrefs>` hit or a lead action.

### Identifying the "needed symbol"

We do **not** need a gold needed-symbol oracle. The relabel mechanism lets the model pick the symbol it was looking for. For analysis only, extract the first `<defn>` call from the resolved trajectory; that symbol is the model's guess at the needed API.

### Training hyperparameters

Reuse the headline recipe:
- Model: `Qwen/Qwen2.5-Coder-7B-Instruct`.
- LoRA rank 16, alpha 32, dropout 0.05.
- LR `1e-4`, 3 epochs, micro-batch 1, grad accumulation 8.
- `max_len=4096`.

---

## 7. Expected sample size and cost

| Stage | Tasks | Seeds/condition | Rollouts | Notes |
|-------|-------|-----------------|----------|-------|
| Task selection / dry-run | 50–100 filtered | 1 | 50–100 | No model load; just resolver smoke tests |
| Mode A harvest | 15–20 | 4–8 | 60–160 | `--force-lsp --relabel --save-sft` |
| Mode B harvest | 15–20 | 4–8 | 60–160 | reads allowed |
| LoRA SFT | — | — | — | ~30–60 min on DGX Spark |
| Retest base / prompt / trained | 20 | 4 | 240 total | 3 conditions |
| Scale check (optional) | subset 8–10 | 2 | ~60 | 27B |

**GPU time:** roughly **1–2 GPU-days** on the reported DGX Spark (GB10, 128 GB unified memory) for the full 7B arm. The optional 27B check adds another ~1 GPU-day.

**Token cost:** If running locally, the cost is electricity/GPU time. If using an API, estimate ~$100–$300 for ~20–30M tokens total, depending on rollout length.

---

## 8. Risks and fallback

| Risk | Why it matters | Fallback / interpretation |
|------|----------------|---------------------------|
| **Ambiguous imports / re-exports** | `<defn>` may land on the wrong file or return a re-export stub. | Use use-site `file/line/col`; if LSP still misses, agent falls back to `<read>`. |
| **Methods and dynamic dispatch** | A bare method name is ambiguous; real behavior may be in subclasses. | Require qualified `Class.method`; report resolution rate separately. |
| **Needing multiple symbols** | One `<read>` may be cheaper than several `<defn>` calls. | Track token spend; the boundary analysis will show when reading is rational. |
| **LSP / pyrefly failures on real repos** | Real repos may not pyrefly-parse cleanly. | Use AST fallback; skip tasks where both fail consistently. |
| **Multi-file / non-local patches** | The agent's line-edit action may be too weak. | Allow `SEARCH/REPLACE/END` and multi-file `SYS_LINE_MULTI`. |
| **Small cost gap** | Many real files are not large enough. | Report per-task savings; do not pool tasks with no gap. |
| **Trained policy under-reads and fails** | The cheap preference could hurt success. | Compare pass@1; if it drops, the boundary is not being learned. |

**How to interpret a null:** If `<defn>` use does not rise, or token savings disappear, the result is still valuable: it shows that a clean synthetic cost gap does not automatically transfer to messy real repositories. We would conclude that the preference must be trained *in* a real-repo distribution, not just on synthetic analogues, and that real-world indirection is the limiting factor identified in `PAPER.md` §7.

---

## 9. Implementation steps

1. **`scaffold/real_env.py`** – create `RealRepoEnv`.
   - Clone/checkout a task's git base commit.
   - Implement `read_file`, `apply_line_edit`, `apply_edit`, `list_files`, `run_tests`, `pyrefly_diagnostics`, `goto_definition`, `lsp_definition`, `find_references`, `metrics`, `current_patch`.
   - `run_tests` runs the repo-specific test command (pytest/unittest) and parses PASS/FAIL.
   - Reuse `LspClient` from `scripts/validate_pyrefly_lsp.py`.

2. **`scaffold/real_env.py::SymbolResolver`** – support qualified symbols and use-site resolution.
   - Parse `module.Class.method`.
   - Fall back to `textDocument/definition` when `file/line/col` are supplied.
   - Expand the LSP location to the enclosing top-level node's full span (as `lsp_definition` already does in `mock_env.py`).

3. **`scripts/real_repo_loader.py`** – task loader and filter.
   - **Primary input:** RefactorBench JSON. Parse its task format into the internal schema.
   - **Secondary input:** hand-curated typed-library issue JSON (same schema).
   - Filter by patch size, file count, referenced-file size, and pyrefly resolver coverage.
   - Build task dicts matching the schema expected by `synth_mf.py` (name, files dict, target, test command, gold patch).

4. **`scripts/resolver_coverage_audit.py`** – coverage sanity check.
   - For each candidate task, extract the symbol touched by the gold patch.
   - Query pyrefly `textDocument/definition` (and the AST fallback) for that symbol.
   - Compare the returned span to the gold source span or `inspect.getsource`.
   - Emit a CSV of `task, symbol, resolver_hit, correct_file, correct_line_range`.
   - Only tasks with `resolver_hit=True` enter the main experiment.

5. **`scripts/real_mf.py`** – runner mirroring `scripts/synth_mf.py`.
   - Use `RealRepoEnv` instead of `MultiFileEnv`.
   - Keep `--force-lsp`, `--relabel`, `--save-sft`, `--steer`, `--adapter`, `--lsp-tools`, `--lsp-defn`.
   - Build prompts with the real issue description and editable-file list.

6. **`scaffold/stream_agent.py`** – extend `<defn>` parsing.
   - Update `DEFN_RE` to capture optional `file`, `line`, `col`.
   - Pass use-site to `_resolve_defn`.
   - Update system prompts to advertise qualified symbols and line-numbered views.

7. **`scripts/run_real_repo.sh`** – shell driver.
   - Stage 1: dry-run / resolver validation.
   - Stage 2: Mode A harvest.
   - Stage 3: Mode B harvest.
   - Stage 4: LoRA SFT.
   - Stage 5: retest base / prompt / trained.
   - Stage 6: run analysis.

8. **`scripts/analysis/real_repo_stats.py`** – metrics and tests.
   - Compute pass@1, `<defn>` use, input tokens, matched-outcome token reduction.
   - Run McNemar and paired sign tests.
   - Subgroup breakdown by post-hoc definition-sufficiency.

9. **(Optional) `scripts/real_coverage_classifier.py`** – lightweight boundary predictor.
   - Train on harvest trajectories to predict whether a task will need a full read.
   - Use only for stratification and diagnosis.

9. **Validation**
   - Run the resolver on 5 sample tasks and check agreement between LSP and AST.
   - End-to-end smoke test on 2 tasks with the default 7B model.
   - Confirm `sft_lora.py` filters and trains without errors on a small harvested JSON.
