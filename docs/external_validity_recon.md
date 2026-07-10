# External-validity reconnaissance

**Budget:** one hour over the already committed scans and stored case-study notes, zero new model/API
calls, and no new repository setup. The stopping rule was three clean tasks or the time limit. This pass
found no fully admissible task; it therefore stops and makes no population-level claim.

| candidate | actual-fix ambiguity | prompt leakage | environment | decision |
|---|---:|---|---|---|
| `django__django-11211` | 21 `get_prep_value` overrides | not established | base/gold and tests previously ran | partial historical case only: prompt leakage and a discriminating fix-site goto remain unaudited |
| `scikit-learn__scikit-learn-10908` | 24 `inverse_transform` overrides | not audited | not validated | reject for this pass: environment and leakage checks incomplete |
| `sympy__sympy-12419` | 28 `_eval_derivative` overrides | not audited | not validated | reject: dynamic receiver/dispatch risk; no discriminating live-goto check |
| `sympy__sympy-14531` | 11 `_print_MatrixElement` definitions | not audited | earlier generic environment only | reject: printer dispatch is dynamic and the scan does not prove call-site disambiguation |
| `pydata__xarray-4966` | 9 `decode` overrides | not audited | not validated | reject for this pass: no base/gold or live-goto manipulation check |
| `astropy__astropy-14182` | scanner reports generic `__init__` collisions | issue names target area | historical task environment ran | reject: ambiguity is not demonstrated at the actual fix site |
| `pydata__xarray-4356` | none in dispatch scan | not audited | not validated | reject: no same-named actual-fix ambiguity |

The source tables are `runs/realbench/dispatch_candidates.json` and the chronology in
`docs/real_repo_progress.md`. The committed scans are useful candidate generators, not an
external-validity result. Experiment 1
therefore uses constructed tasks over ordinary Python package structure. If future reconnaissance finds
three clean real tasks, they should be reported as case studies only. CrossCodeEval is the preferred
instrumentable fallback for a broader static-context study.
