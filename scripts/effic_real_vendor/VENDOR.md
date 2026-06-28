# Vendored real library source — `effic_real` suite

Committed snapshots of real, idiomatic, pure-Python packages used by
`scripts/synth_tasks_effic_real.py`. The tasks read these files at import time
(`_pkg_files(pkg)`) so the suite exercises genuine library code: imports resolve and the
behavioural tests run the real implementation through the pyrefly-backed `MultiFileEnv`.

## Packages and exact versions

| package         | version | source                                  |
|-----------------|---------|-----------------------------------------|
| `toolz`         | 1.1.0   | PyPI sdist/wheel, `pip install toolz`   |
| `more-itertools`| 11.1.0  | PyPI, `pip install more-itertools`      |

Both are pure Python and (apart from the trims noted below) are vendored verbatim from a
throwaway venv:

```
python3 -m venv vendor_venv
vendor_venv/bin/pip install toolz==1.1.0 more-itertools==11.1.0
# then copy the package source trees here, excluding tests / __pycache__ / compiled artifacts
```

(`h11` 0.16.0 and `markupsafe` 3.0.3 were also installed while scouting candidates but are
NOT vendored — the suite only uses `toolz` and `more_itertools`.)

## Trims applied to the snapshot

- **`toolz`**: the `tests/` directory and `__pycache__/` are excluded (test files add ~160
  pyrefly errors and are irrelevant). The optional **`curried/` and `sandbox/`
  alternate-namespace subpackages are NOT vendored**, and the single line
  `from . import curried, sandbox` in `toolz/__init__.py` is commented out (a note marks the
  spot). Reason: `toolz/curried/__init__.py` re-binds every core symbol as a module-level
  alias (e.g. `get = curry(toolz.get)`). Since that file sorts before `itertoolz.py`, the
  env's AST `goto_definition` would resolve `<defn get/>` to the one-line alias instead of the
  real definition — defeating the defn-vs-read comparison. With those subpackages removed,
  go-to-definition resolves to the genuine `itertoolz`/`dicttoolz` source. The CORE modules
  (`itertoolz.py`, `dicttoolz.py`, `functoolz.py`, `_signatures.py`, `recipes.py`, `utils.py`,
  `compatibility.py`) are otherwise pristine.
- **`more_itertools`**: vendored verbatim, including the `.pyi` type stubs and `py.typed`
  (these let pyrefly catch the arg-order misuse in the `take`/`tail` tasks). Only
  `__pycache__/` is excluded.

## Pre-existing pyrefly noise (expected, not the model's concern)

These vendored libraries type-check with their own internal errors workspace-wide
(`toolz` ~40, `more_itertools` ~17), and `pyrefly_diagnostics()` only surfaces the first 10.
The suite's verifier therefore counts pyrefly errors **scoped to `target.py`** (uncapped,
basename-filtered) for R2/R4 — see the module docstring of `synth_tasks_effic_real.py`.
