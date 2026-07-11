import math
from pathlib import Path
import subprocess
import sys

from scaffold.mock_env import MultiFileEnv
from scripts.analysis.effic_real_stats import binom_two_sided
from scripts.analysis.analyze_checker_paired import (
    end_to_end_summary,
    expected_cost_per_accepted_correct,
    paired_contrast,
)
from scripts.analysis.analyze_navigation import interaction, paired_ratio
from scripts.experiments.diagnostics import collect_diagnostics, delta, format_diagnostics, is_coherent
from scripts.experiments.navigation_tasks import build_prompt, build_tasks
from scripts.experiments.run_navigation import (
    _control_floor_failure,
    _method_from_metadata,
    _positive_result,
)


def test_navigation_generator_pairs_runtime_and_hides_target(tmp_path):
    task = build_tasks(tmp_path, "pilot")[0]
    typed = task["variants"]["typed"]["files"]
    erased = task["variants"]["erased"]["files"]
    assert typed["pkg/factory.py"] == erased["pkg/factory.py"]
    assert typed["pkg/factory.pyi"] != erased["pkg/factory.pyi"]
    assert all(typed[path] == erased[path] for path in typed if path.endswith(".py"))
    assert "cast(" not in typed["pkg/factory.py"]
    for token, class_name in task["registry_contract"].items():
        assert f'Literal["{token}"]' in typed["pkg/factory.pyi"]
        assert f"-> {class_name}" in typed["pkg/factory.pyi"]
    assert 8 <= task["n_overrides"] <= 15
    prompt = build_prompt(task, "typed")
    assert task["target_class"] not in prompt
    assert task["target_path"] not in prompt
    positive = _positive_result(task)
    assert task["gold"]["new_text"] in positive
    assert task["target_method_span"]["source"] not in positive
    current_span, current_path = _method_from_metadata(task)
    assert current_path == task["target_path"]
    assert task["target_method_span"]["source"].splitlines()[-1] in current_span
    assert task["gold"]["new_text"] not in current_span
    repo = task["variants"]["typed"]["repo_dir"]
    probe = subprocess.run(
        [sys.executable, "-c", (
            "from pkg.factory import make\n"
            + "actual = {k: type(make(k)).__name__ for k in " + repr(task["tokens"]) + "}\n"
            + "assert actual == " + repr(task["registry_contract"]) + "\n"
        )],
        cwd=repo, capture_output=True, text=True,
    )
    assert probe.returncode == 0, probe.stderr


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


def test_navigation_token_equivalence_uses_ratio_of_task_weighted_means():
    rows = []
    for task, base, treatment in (("small", 10, 20), ("large", 100, 100)):
        rows.extend([
            {"task": task, "variant": "typed", "arm": "baseline",
             "held_out_pass": True, "in_tokens": base, "out_tokens": 0},
            {"task": task, "variant": "typed", "arm": "semantic_auto",
             "held_out_pass": True, "in_tokens": treatment, "out_tokens": 0},
        ])
    result = paired_ratio(
        rows, ("typed", "baseline"), ("typed", "semantic_auto"),
        "total_tokens", bootstrap=100, seed=1,
    )
    assert result["ratio_of_task_weighted_means"] == 120 / 110
    assert result["mean_task_ratio_descriptive"] == 1.5
    assert not result["equivalent"]


def test_checker_expected_cost_includes_draft_and_failed_attempts():
    drafts = [
        {"draft_id": "d1", "task": "t1", "draft_submitted": True, "coherent": True,
         "draft_diagnostics": [], "in_tokens": 100, "out_tokens": 20},
        {"draft_id": "d2", "task": "t2", "draft_submitted": True, "coherent": True,
         "draft_diagnostics": [], "in_tokens": 200, "out_tokens": 20},
    ]
    rows = [
        {"draft_id": "d1", "task": "t1", "arm": "gate", "accepted": True,
         "held_pass": True, "type_clean": True, "in_tokens": 50, "out_tokens": 10},
        {"draft_id": "d2", "task": "t2", "arm": "gate", "accepted": False,
         "held_pass": False, "type_clean": True, "in_tokens": 30, "out_tokens": 10},
    ]
    result = expected_cost_per_accepted_correct(
        drafts, rows, "gate", False, bootstrap=100, seed=1,
    )
    assert result["accepted_correct_rate"] == 0.5
    assert result["mean_draft_plus_revision_tokens"] == 220
    assert result["expected_tokens_per_accepted_correct_patch"] == 440
    assert math.isinf(result["ci95"][1])


def test_checker_end_to_end_counts_incoherent_draft_as_failure():
    drafts = [
        {"draft_id": "d1", "task": "t1", "draft_submitted": True, "coherent": True,
         "draft_diagnostics": [], "in_tokens": 100, "out_tokens": 20},
        {"draft_id": "d2", "task": "t2", "draft_submitted": True, "coherent": False,
         "draft_diagnostics": [], "in_tokens": 200, "out_tokens": 20},
    ]
    rows = [{
        "draft_id": "d1", "task": "t1", "arm": "control", "accepted": True,
        "held_pass": True, "type_clean": True, "semantic_clean": True,
        "in_tokens": 50, "out_tokens": 10,
    }]
    result = end_to_end_summary(drafts, rows, "control")
    assert result["final_held_pass_yield"] == 0.5
    assert result["accepted_correct_yield"] == 0.5
    assert result["pre_revision_failure_rate"] == 0.5


def test_navigation_span_control_enforces_floor():
    passed = [{"arm": "semantic_span_control", "held_out_pass": True}]
    failed = [{"arm": "semantic_span_control", "held_out_pass": False}]
    assert _control_floor_failure("span-control", passed) is None
    assert _control_floor_failure("span-control", failed)


def test_paired_analyzers_reject_incomplete_nested_grids():
    nav_rows = [
        {"task": "t", "seed": 0, "variant": variant, "arm": arm,
         "held_out_pass": True, "in_tokens": 1, "out_tokens": 0}
        for variant, arm in (
            ("typed", "baseline"), ("typed", "semantic_auto"),
            ("erased", "baseline"), ("erased", "semantic_auto"),
        )
    ]
    nav_rows[-1]["seed"] = 1
    assert not interaction(nav_rows, "pass", 10, 1)["estimable"]

    checker_rows = [
        {"task": "t", "draft_id": "d", "seed": 0, "arm": "control", "held_pass": True},
        {"task": "t", "draft_id": "d", "seed": 1, "arm": "gate", "held_pass": True},
    ]
    assert not paired_contrast(checker_rows, "gate", "held_pass", False, 10, 1)["estimable"]
