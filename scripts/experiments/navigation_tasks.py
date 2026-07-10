#!/usr/bin/env python3
"""Generate and validate the paired types x semantic-navigation experiment.

The pilot, apparatus-audit, and confirmation splits are deterministic and disjoint. The typed factory stub
adds sound per-key overloads; runtime construction, the factory implementation, implementation files,
tests, and the gold patch are identical between variants.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import random
import re
import shutil
import string
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scaffold.real_env import RealRepoEnv  # noqa: E402
from scaffold.tooling import find_pyrefly  # noqa: E402


PROTOCOL_VERSION = "navigation-v2"
SPLIT_SEEDS = {
    "pilot": (17011, 17027, 17033, 17041),
    "apparatus": (
        29009, 29017, 29021, 29023, 29027, 29033,
        29059, 29063, 29077, 29083, 29089, 29101,
    ),
    "confirmation": (
        41011, 41017, 41023, 41039, 41047, 41051,
        41057, 41077, 41081, 41083, 41099, 41113,
    ),
}
VARIANTS = ("typed", "erased")
SPLIT_TEMPLATES = {
    "pilot": ("add", "multiply"),
    "apparatus": ("subtract", "affine", "xor"),
    "confirmation": ("modulo", "square_offset", "negate_offset"),
}


class StrictUseSiteEnv(RealRepoEnv):
    """Require the composed semantic tool to identify an explicit use site."""

    def lsp_definition(self, symbol, file=None, line=None, col=None):
        if file is None or line is None or col is None:
            return None, None
        return super().lsp_definition(symbol, file=file, line=line, col=col)

    def apply_line_edit(self, path, start, end, new_text):
        if path not in self.editable:
            return False, f"file is not editable in this treatment: {path}"
        return super().apply_line_edit(path, start, end, new_text)


def _identifier(rng: random.Random, prefix: str, length: int = 7) -> str:
    return prefix + "".join(rng.choice(string.ascii_lowercase) for _ in range(length))


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def _line_of(source: str, pattern: str) -> tuple[int, int]:
    for line_no, line in enumerate(source.splitlines(), 1):
        match = re.search(pattern, line)
        if match:
            return line_no, match.start() + 1
    raise ValueError(f"pattern not found: {pattern}")


def _method_span(source: str, class_name: str, method: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method:
                    end = child.end_lineno or child.lineno
                    return child.lineno, end, "\n".join(lines[child.lineno - 1:end])
    raise ValueError(f"method not found: {class_name}.{method}")


def _spec(seed: int, split: str) -> dict:
    rng = random.Random(seed)
    n_overrides = rng.randint(8, 15)
    base = _identifier(rng, "B")
    method = _identifier(rng, "m")
    classes = [_identifier(rng, "C") for _ in range(n_overrides)]
    tokens = [_identifier(rng, "k", 5) for _ in range(n_overrides)]
    module_count = 4
    modules = [_identifier(rng, "u", 5) for _ in range(module_count)]
    target_idx = rng.randrange(n_overrides)
    template_index = SPLIT_SEEDS[split].index(seed) % len(SPLIT_TEMPLATES[split])
    template = SPLIT_TEMPLATES[split][template_index]
    value_range = range(2, 20) if template == "multiply" else range(11, 90)
    params = rng.sample(value_range, n_overrides)
    input_value = rng.randint(2, 9)
    return {
        "seed": seed,
        "split": split,
        "name": f"nav_{split}_{seed}",
        "base": base,
        "method": method,
        "classes": classes,
        "tokens": tokens,
        "modules": modules,
        "target_idx": target_idx,
        "template": template,
        "params": params,
        "input": input_value,
    }


def _expression(template: str, param: int) -> str:
    return {
        "add": f"value + {param}",
        "multiply": f"value * {param}",
        "subtract": f"value - {param}",
        "affine": f"value * 2 + {param}",
        "xor": f"value ^ {param}",
        "modulo": f"(value + {param}) % 97",
        "square_offset": f"value * value + {param}",
        "negate_offset": f"{param} - value",
    }[template]


def _evaluate(template: str, value: int, param: int) -> int:
    return {
        "add": value + param,
        "multiply": value * param,
        "subtract": value - param,
        "affine": value * 2 + param,
        "xor": value ^ param,
        "modulo": (value + param) % 97,
        "square_offset": value * value + param,
        "negate_offset": param - value,
    }[template]


def _sources(spec: dict, variant: str) -> tuple[dict[str, str], dict]:
    base, method = spec["base"], spec["method"]
    files = {
        "pkg/__init__.py": "",
        "pkg/units/__init__.py": "",
        "pkg/base.py": (
            f"class {base}:\n"
            f"    def {method}(self, value: int) -> int:\n"
            "        raise NotImplementedError\n"
        ),
    }
    class_to_path = {}
    for module_idx, module in enumerate(spec["modules"]):
        blocks = [f"from pkg.base import {base}\n"]
        for idx, class_name in enumerate(spec["classes"]):
            if idx % len(spec["modules"]) != module_idx:
                continue
            param = spec["params"][idx]
            if idx == spec["target_idx"]:
                param += 1
            blocks.append(
                f"\n\nclass {class_name}({base}):\n"
                f"    def {method}(self, value: int) -> int:\n"
                f"        return {_expression(spec['template'], param)}\n"
            )
            class_to_path[class_name] = f"pkg/units/{module}.py"
        files[f"pkg/units/{module}.py"] = "".join(blocks)

    imports = [f"from pkg.base import {base}"]
    for module in spec["modules"]:
        names = [c for i, c in enumerate(spec["classes"])
                 if i % len(spec["modules"]) == spec["modules"].index(module)]
        imports.append(f"from pkg.units.{module} import {', '.join(names)}")
    entries = ",\n".join(
        f'    "{token}": {class_name}'
        for token, class_name in zip(spec["tokens"], spec["classes"])
    )
    target_class = spec["classes"][spec["target_idx"]]
    token = spec["tokens"][spec["target_idx"]]
    stub_imports = [f"from pkg.base import {base}"]
    overloads = ""
    if variant == "typed":
        stub_imports.append("from typing import Literal, overload")
        for module in spec["modules"]:
            names = [c for i, c in enumerate(spec["classes"])
                     if i % len(spec["modules"]) == spec["modules"].index(module)]
            stub_imports.append(f"from pkg.units.{module} import {', '.join(names)}")
        overloads = "".join(
            "@overload\n"
            f'def make(token: Literal["{key}"]) -> {class_name}: ...\n\n'
            for key, class_name in zip(spec["tokens"], spec["classes"])
        )
        overloads += f"@overload\ndef make(token: str) -> {base}: ...\n\n"
    files["pkg/factory.py"] = (
        "\n".join(imports) + "\n\n"
        f"_items: dict[str, type[{base}]] = {{\n{entries}\n}}\n\n"
        f"def make(token: str) -> {base}:\n"
        "    return _items[token]()\n"
    )
    files["pkg/factory.pyi"] = (
        "\n".join(stub_imports) + "\n\n"
        + (overloads if variant == "typed" else f"def make(token: str) -> {base}: ...\n")
    )
    files["pkg/app.py"] = (
        "from typing import Literal\n\n"
        "from pkg.factory import make\n\n\n"
        f'def execute(token: Literal["{token}"], value: int) -> int:\n'
        "    x = make(token)\n"
        f"    return x.{method}(value)\n"
    )
    files["pkg/widened.py"] = (
        "from pkg.factory import make\n\n\n"
        "def execute_widened(token: str, value: int) -> int:\n"
        "    x = make(token)\n"
        f"    return x.{method}(value)\n"
    )
    target_param = spec["params"][spec["target_idx"]]
    expected = _evaluate(spec["template"], spec["input"], target_param)
    held_input = spec["input"] + 7
    held_expected = _evaluate(spec["template"], held_input, target_param)
    files["test_behavior.py"] = (
        "from pkg.app import execute\n\n\n"
        "def main() -> None:\n"
        f'    assert execute("{token}", {spec["input"]}) == {expected}\n\n\n'
        'if __name__ == "__main__":\n'
        "    main()\n"
    )
    files["test_heldout.py"] = (
        "from pkg.app import execute\n\n\n"
        "def main() -> None:\n"
        f'    assert execute("{token}", {held_input}) == {held_expected}\n\n\n'
        'if __name__ == "__main__":\n'
        "    main()\n"
    )

    target_path = class_to_path[target_class]
    start, end, span = _method_span(files[target_path], target_class, method)
    target_lines = files[target_path].splitlines()
    buggy_line = next(
        line_no for line_no in range(start, end + 1)
        if "return " in target_lines[line_no - 1]
    )
    gold = {
        "path": target_path,
        "start": buggy_line,
        "end": buggy_line,
        "new_text": f"        return {_expression(spec['template'], target_param)}",
    }
    meta = {
        "target_class": target_class,
        "target_path": target_path,
        "target_method_span": {"start": start, "end": end, "source": span},
        "gold": gold,
        "token": token,
        "expected": expected,
        "held_input": held_input,
        "held_expected": held_expected,
        "registry_contract": dict(zip(spec["tokens"], spec["classes"])),
    }
    return files, meta


def build_tasks(root: str | Path, split: str = "pilot") -> list[dict]:
    if split not in SPLIT_SEEDS:
        raise ValueError(f"unknown split {split!r}")
    root = Path(root)
    tasks = []
    for seed in SPLIT_SEEDS[split]:
        spec = _spec(seed, split)
        paired = {}
        shared_meta = None
        for variant in VARIANTS:
            files, meta = _sources(spec, variant)
            repo = root / spec["name"] / variant
            if repo.exists():
                shutil.rmtree(repo)
            repo.mkdir(parents=True)
            for rel, source in files.items():
                _write(repo, rel, source)
            _write(repo, "pyrefly.toml", 'project-includes = ["pkg/**/*.py", "pkg/**/*.pyi"]\n')
            _git(repo, "init", "-q")
            _git(repo, "add", "-A")
            _git(repo, "-c", "user.email=streams@local", "-c", "user.name=streams",
                 "commit", "-q", "-m", "base")
            base_commit = _git(repo, "rev-parse", "HEAD").stdout.strip()
            line, col = _line_of(files["pkg/app.py"], rf"\b{re.escape(spec['method'])}\b")
            wide_line, wide_col = _line_of(
                files["pkg/widened.py"], rf"\b{re.escape(spec['method'])}\b"
            )
            paired[variant] = {
                "repo_dir": str(repo),
                "files": files,
                "base_commit": base_commit,
                "gold": meta["gold"],
                "use_site": {"file": "pkg/app.py", "line": line, "col": col},
                "widened_use_site": {
                    "file": "pkg/widened.py", "line": wide_line, "col": wide_col,
                },
            }
            shared_meta = meta
        tasks.append({
            **spec,
            **shared_meta,
            "variants": paired,
            "editable": sorted(
                p for p in paired["typed"]["files"]
                if p.startswith("pkg/units/") and p != "pkg/units/__init__.py"
            ),
            "n_overrides": len(spec["classes"]),
            "protocol": PROTOCOL_VERSION,
        })
    return tasks


def make_env(task: dict, variant: str) -> RealRepoEnv:
    data = task["variants"][variant]
    return StrictUseSiteEnv(
        data["repo_dir"], editable=task["editable"],
        test_spec=f"{sys.executable} test_behavior.py", base_commit=data["base_commit"],
        file_glob="pkg/**/*.*", test_kind="command", test_cwd=".",
        lsp_index_sleep=6.0, lsp_timeout=30.0,
    )


def build_prompt(task: dict, variant: str) -> str:
    app = task["variants"][variant]["files"]["pkg/app.py"]
    numbered = "\n".join(f"{i:>3}| {line}" for i, line in enumerate(app.splitlines(), 1))
    return (
        "Fix a one-line bug in one implementation module. The failing behavior is:\n"
        f"`execute({task['token']!r}, {task['input']})` should return {task['expected']}.\n\n"
        "The initially visible call site is:\n"
        f"```python\n{numbered}\n```\n\n"
        f"The method `{task['method']}` has {task['n_overrides']} implementations. Construction is "
        "indirect through a factory and registry. Trace source as needed, edit one implementation, "
        "then run the test."
    )


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _protocol_hashes() -> dict[str, str]:
    paths = [
        Path(__file__).resolve(),
        ROOT / "scripts" / "experiments" / "run_navigation.py",
        ROOT / "scripts" / "analysis" / "analyze_navigation.py",
        ROOT / "scripts" / "run_navigation_pilot.sh",
        ROOT / "scripts" / "run_navigation_confirmation.sh",
        ROOT / "scaffold" / "stream_agent.py",
        ROOT / "scaffold" / "real_env.py",
        ROOT / "scaffold" / "tooling.py",
        ROOT / "scripts" / "validate_pyrefly_lsp.py",
        ROOT / "evidence" / "protocols.md",
    ]
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def _probe_runtime(task: dict, variant: str) -> dict[str, int]:
    repo = task["variants"][variant]["repo_dir"]
    code = (
        "import json\nfrom pkg.app import execute\n"
        f"print(json.dumps({{k: execute(k, 13) for k in {task['tokens']!r}}}, sort_keys=True))\n"
    )
    run = subprocess.run([sys.executable, "-c", code], cwd=repo, capture_output=True, text=True)
    if run.returncode:
        raise RuntimeError(run.stderr)
    return json.loads(run.stdout)


def _probe_factory_classes(task: dict, variant: str) -> dict[str, str]:
    repo = task["variants"][variant]["repo_dir"]
    code = (
        "import json\nfrom pkg.factory import make\n"
        f"print(json.dumps({{k: type(make(k)).__name__ for k in {task['tokens']!r}}}, sort_keys=True))\n"
    )
    run = subprocess.run([sys.executable, "-c", code], cwd=repo, capture_output=True, text=True)
    if run.returncode:
        raise RuntimeError(run.stderr)
    return json.loads(run.stdout)


def _type_errors(repo: str) -> list[dict]:
    run = subprocess.run(
        [find_pyrefly(), "check", "--output-format", "json", repo],
        cwd=repo, capture_output=True, text=True, timeout=90,
    )
    try:
        return json.loads(run.stdout or "{}").get("errors", [])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid Pyrefly check output: {run.stdout[:300]}") from exc


def run_heldout(task: dict, variant: str) -> bool:
    run = subprocess.run(
        [sys.executable, "test_heldout.py"], cwd=task["variants"][variant]["repo_dir"],
        capture_output=True, text=True,
    )
    return run.returncode == 0


def _validate_task(task: dict) -> dict:
    row = {"task": task["name"], "split": task["split"], "template": task["template"],
           "n_overrides": task["n_overrides"]}
    lsp = {}
    lsp_errors = []
    tests = {}
    failures = []
    for variant in VARIANTS:
        env = make_env(task, variant)
        try:
            base_result = env.run_tests()
            tests[f"{variant}_base_fails"] = not base_result["resolved"]
            failures.append(base_result.get("failure", ""))
            tests[f"{variant}_heldout_base_fails"] = not run_heldout(task, variant)
            use = task["variants"][variant]["use_site"]
            t0 = time.perf_counter()
            span, path = env.lsp_definition(
                task["method"], file=use["file"], line=use["line"], col=use["col"]
            )
            lsp[variant] = {
                "path": path,
                "span_hash": _hash(span or ""),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "health_path": path,
                "resolved_class": None,
            }
            try:
                node = ast.parse(span or "").body[0]
                if isinstance(node, ast.ClassDef):
                    lsp[variant]["resolved_class"] = node.name
                    span_lines = (span or "").splitlines()
                    method_nodes = [
                        child for child in node.body
                        if isinstance(child, ast.FunctionDef) and child.name == task["method"]
                    ]
                    if len(method_nodes) == 1:
                        child = method_nodes[0]
                        method_source = "\n".join(
                            span_lines[child.lineno - 1:(child.end_lineno or child.lineno)]
                        )
                        lsp[variant]["resolved_method_span_hash"] = _hash(method_source)
            except (SyntaxError, IndexError):
                pass
            if path is None:
                health_line, health_col = _line_of(
                    task["variants"][variant]["files"]["pkg/app.py"], r"\bmake\b"
                )
                _health_span, health_path = env.lsp_definition(
                    "make", file="pkg/app.py", line=health_line, col=health_col
                )
                lsp[variant]["health_path"] = health_path
            if variant == "typed":
                wide = task["variants"][variant]["widened_use_site"]
                wide_span, wide_path = env.lsp_definition(
                    task["method"], file=wide["file"], line=wide["line"], col=wide["col"]
                )
                wide_class = None
                try:
                    node = ast.parse(wide_span or "").body[0]
                    if isinstance(node, ast.ClassDef):
                        wide_class = node.name
                except (SyntaxError, IndexError):
                    pass
                lsp["typed_widened"] = {
                    "path": wide_path,
                    "span_hash": _hash(wide_span or ""),
                    "resolved_class": wide_class,
                }
            gold = task["gold"]
            applied, _ = env.apply_line_edit(gold["path"], gold["start"], gold["end"], gold["new_text"])
            tests[f"{variant}_gold_passes"] = bool(applied and env.run_tests()["resolved"])
            tests[f"{variant}_heldout_gold_passes"] = bool(applied and run_heldout(task, variant))
        finally:
            lsp_errors.extend(env.lsp_errors)
            env.close()

    typed_files = task["variants"]["typed"]["files"]
    erased_files = task["variants"]["erased"]["files"]
    runtime_files = sorted(p for p in typed_files if p.endswith(".py"))
    runtime_hashes_equal = all(_hash(typed_files[p]) == _hash(erased_files[p]) for p in runtime_files)
    runtime_outputs_equal = _probe_runtime(task, "typed") == _probe_runtime(task, "erased")
    factory_classes = {
        variant: _probe_factory_classes(task, variant) for variant in VARIANTS
    }
    expected_contract = task["registry_contract"]
    typed_stub = typed_files["pkg/factory.pyi"]
    declared_contract = dict(re.findall(
        r'def make\(token: Literal\["([^"]+)"\]\) -> ([A-Za-z_][A-Za-z0-9_]*):',
        typed_stub,
    ))
    fallback_signature = f"def make(token: str) -> {task['base']}: ..."
    type_errors = {
        variant: _type_errors(task["variants"][variant]["repo_dir"]) for variant in VARIANTS
    }
    initial_surfaces = [
        build_prompt(task, "typed"),
        typed_files["pkg/app.py"],
        typed_files["test_behavior.py"],
        "implementation modules under pkg/units/",
        *failures,
    ]
    forbidden = [task["target_class"], task["target_path"]]
    leakage = [token for token in forbidden if any(token in surface for surface in initial_surfaces)]
    base_path = "pkg/base.py"
    typed_ok = (lsp["typed"]["path"] == task["target_path"]
                and lsp["typed"]["resolved_class"] == task["target_class"])
    erased_ok = (
        lsp["erased"]["path"] is None
        or (lsp["erased"]["path"] == base_path
            and lsp["erased"]["resolved_class"] == task["base"])
    )
    widened = lsp.get("typed_widened", {})
    widened_ok = (
        widened.get("path") is None
        or (widened.get("path") == base_path
            and widened.get("resolved_class") == task["base"])
    )
    implementation_files = [path for path in typed_files if path.startswith("pkg/units/")
                            and path.endswith(".py") and path != "pkg/units/__init__.py"]
    actual_overrides = sum(
        len(re.findall(rf"\bdef\s+{re.escape(task['method'])}\b", typed_files[path]))
        for path in implementation_files
    )
    factory = typed_files["pkg/factory.py"]
    implementation_marker = f"def make(token: str) -> {task['base']}:\n"
    typed_impl = implementation_marker + factory.rsplit(implementation_marker, 1)[1]
    erased_factory = erased_files["pkg/factory.py"]
    erased_impl = implementation_marker + erased_factory.rsplit(implementation_marker, 1)[1]
    registry_unique = (
        len(set(task["tokens"])) == task["n_overrides"]
        and factory.count(f'"{task["token"]}": {task["target_class"]}') == 1
    )
    checks = {
        **tests,
        "runtime_files_identical": runtime_hashes_equal,
        "runtime_outputs_identical": runtime_outputs_equal,
        "factory_implementation_identical": typed_impl == erased_impl,
        "all_declared_returns_match_runtime": (
            declared_contract == expected_contract
            and factory_classes["typed"] == declared_contract
            and factory_classes["erased"] == expected_contract
        ),
        "specific_overloads_precede_fallback": (
            typed_stub.count(fallback_signature) == 1
            and all(typed_stub.index(f'Literal["{key}"]') < typed_stub.index(fallback_signature)
                    for key in task["tokens"])
        ),
        "variants_type_clean": not type_errors["typed"] and not type_errors["erased"],
        "gold_identical": (task["variants"]["typed"]["gold"]
                           == task["variants"]["erased"]["gold"] == task["gold"]),
        "override_count_valid": (8 <= actual_overrides <= 15
                                 and actual_overrides == task["n_overrides"]
                                 and len(implementation_files) >= 3),
        "registry_trace_unique": registry_unique,
        "typed_lsp_discriminates": typed_ok,
        "typed_lsp_span_matches_pristine_target": (
            lsp["typed"].get("resolved_method_span_hash")
            == _hash(task["target_method_span"]["source"])
        ),
        "erased_lsp_nondiscriminating": erased_ok,
        "literal_widening_removes_discrimination": widened_ok,
        "lsp_server_healthy": all(
            data.get("health_path", data.get("path")) is not None for data in lsp.values()
        ),
        "lsp_no_errors": not lsp_errors,
        "prompt_has_no_target_leak": not leakage,
        "positive_control_materialized": bool(task["target_method_span"]["source"] and task["gold"]),
    }
    row.update({"checks": checks, "lsp": lsp, "lsp_errors": lsp_errors,
                "runtime_factory_classes": factory_classes,
                "declared_registry_contract": expected_contract,
                "parsed_typed_stub_contract": declared_contract,
                "type_errors": type_errors,
                "leakage": leakage, "passed": all(checks.values())})
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=sorted(SPLIT_SEEDS), default="pilot")
    parser.add_argument("--tmp-root", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    tmp_root = args.tmp_root or str(Path(tempfile.gettempdir()) / "streams_navigation_v2")
    tasks = build_tasks(Path(tmp_root) / args.split, args.split)
    rows = []
    for task in tasks:
        row = _validate_task(task)
        rows.append(row)
        print(f"{task['name']}: {'PASS' if row['passed'] else 'FAIL'} "
              f"typed={row['lsp']['typed']['path']} erased={row['lsp']['erased']['path']}")
    pyrefly = find_pyrefly()
    version = subprocess.run([pyrefly, "--version"], capture_output=True, text=True).stdout.strip()
    result = {
        "protocol": PROTOCOL_VERSION,
        "split": args.split,
        "generator": str(Path(__file__).relative_to(ROOT)),
        "seeds": list(SPLIT_SEEDS[args.split]),
        "templates": list(SPLIT_TEMPLATES[args.split]),
        "protocol_source_sha256": _protocol_hashes(),
        "pyrefly": {"path": pyrefly, "version": version},
        "rows": rows,
        "passed": all(r["passed"] for r in rows),
    }
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
