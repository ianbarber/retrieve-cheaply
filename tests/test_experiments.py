from pathlib import Path

from scaffold.mock_env import MultiFileEnv
from scripts.analysis.effic_real_stats import binom_two_sided
from scripts.experiments.diagnostics import collect_diagnostics, delta, format_diagnostics, is_coherent
from scripts.experiments.navigation_tasks import build_prompt, build_tasks
from scripts.experiments.run_navigation import _positive_result


def test_navigation_generator_pairs_runtime_and_hides_target(tmp_path):
    task = build_tasks(tmp_path, "pilot")[0]
    typed = task["variants"]["typed"]["files"]
    erased = task["variants"]["erased"]["files"]
    assert typed["pkg/factory.py"] != erased["pkg/factory.py"]
    assert all(typed[path] == erased[path] for path in typed if path != "pkg/factory.py")
    assert 8 <= task["n_overrides"] <= 15
    prompt = build_prompt(task, "typed")
    assert task["target_class"] not in prompt
    assert task["target_path"] not in prompt
    positive = _positive_result(task)
    assert task["gold"]["new_text"] in positive
    assert task["target_method_span"]["source"] not in positive


def test_diagnostic_delta_and_presentation():
    base = [{
        "path": "target.py", "line": 2, "column": 1, "stop_line": 2, "stop_column": 2,
        "code": "bad-return", "message": "wrong", "classification": "semantic", "frame": "2| x",
    }]
    moved_same_error = [{**base[0], "line": 4, "frame": "4| x"}]
    novel = [{**base[0], "code": "missing-attribute", "message": "no member"}]
    assert delta(moved_same_error, base) == []
    assert delta(novel, base) == novel
    assert "missing-attribute" in format_diagnostics(novel)


def test_coherence_requires_parseable_implemented_source():
    assert is_coherent("def f() -> int:\n    return 1\n")
    assert not is_coherent("def f():\n    raise NotImplementedError()\n")
    assert not is_coherent("def f(:\n    pass\n")


def test_behavioral_test_runner_does_not_pollute_workspace():
    env = MultiFileEnv({"target.py": "x = 1\n"}, "target.py", "from target import x\nassert x == 1",
                       skip_pyrefly=True)
    try:
        assert env.run_tests()["resolved"]
        assert not (Path(env.ws) / "_run_tests.py").exists()
    finally:
        env.close()


def test_collect_diagnostics_resolves_pyrefly_relative_paths():
    env = MultiFileEnv({"target.py": 'def f() -> int:\n    return "wrong"\n'}, "target.py", "",
                       skip_pyrefly=False)
    try:
        diagnostics, _ = collect_diagnostics(env.ws, {"target.py"})
        assert diagnostics
        assert diagnostics[0]["path"] == "target.py"
        assert diagnostics[0]["code"] == "bad-return"
    finally:
        env.close()


def test_exact_sign_test_handles_all_ties_as_no_evidence():
    assert binom_two_sided(0, 0) == 1.0
