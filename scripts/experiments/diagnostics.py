"""Structured, delta-scoped Pyrefly diagnostics for paired checker experiments."""

from __future__ import annotations

import ast
from collections import Counter
import json
import subprocess
import time
from pathlib import Path

from scaffold.mock_env import MultiFileEnv
from scaffold.tooling import find_pyrefly


SYNTAX_CODES = {"parse-error", "syntax-error", "invalid-syntax", "unexpected-token"}


def _frame(path: Path, line: int, radius: int = 1) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    start, end = max(1, line - radius), min(len(lines), line + radius)
    return "\n".join(f"{i:>4}| {lines[i - 1]}" for i in range(start, end + 1))


def collect_diagnostics(workspace: str | Path, scope: set[str] | None = None) -> tuple[list[dict], float]:
    workspace = Path(workspace).resolve()
    started = time.perf_counter()
    run = subprocess.run(
        [find_pyrefly(), "check", "--output-format", "json", str(workspace)],
        cwd=workspace, capture_output=True, text=True, timeout=90,
    )
    latency = time.perf_counter() - started
    try:
        payload = json.loads(run.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid Pyrefly JSON: {exc}: {run.stdout[:300]}") from exc
    normalized = []
    syntax_paths = set()
    for raw in payload.get("errors", []):
        raw_path = Path(raw.get("path") or "")
        absolute = (raw_path if raw_path.is_absolute() else workspace / raw_path).resolve()
        try:
            path = str(absolute.relative_to(workspace))
        except ValueError:
            path = str(absolute)
        code = raw.get("name") or str(raw.get("code", "diagnostic"))
        normalized.append((raw, path, code))
        if code in SYNTAX_CODES or "parse" in code:
            syntax_paths.add(path)

    rows = []
    seen = set()
    for raw, path, code in normalized:
        if scope is not None and path not in scope:
            continue
        message = raw.get("concise_description") or raw.get("description") or ""
        line = int(raw.get("line") or 1)
        column = int(raw.get("column") or 1)
        stop_line = int(raw.get("stop_line") or line)
        stop_column = int(raw.get("stop_column") or column)
        key = (path, line, column, stop_line, stop_column, code, message)
        if key in seen:
            continue
        seen.add(key)
        # Semantic-looking errors in a file that does not parse are often cascades from the
        # partial edit. Do not count them as checker-positive semantic opportunities.
        classification = "syntax_or_partial" if path in syntax_paths else "semantic"
        rows.append({
            "path": path, "line": line, "column": column,
            "stop_line": stop_line, "stop_column": stop_column,
            "code": code, "message": message, "severity": raw.get("severity", "error"),
            "classification": classification,
            "frame": _frame(workspace / path, line),
        })
    rows.sort(key=lambda d: (d["path"], d["line"], d["column"], d["code"], d["message"]))
    return rows, latency


def fingerprint(diag: dict, include_location: bool = False) -> tuple:
    base = (diag["path"], diag["code"], diag["message"])
    return base + ((diag["line"], diag["column"]) if include_location else ())


def delta(current: list[dict], baseline: list[dict]) -> list[dict]:
    baseline_counts = Counter(fingerprint(item) for item in baseline)
    result = []
    for item in current:
        key = fingerprint(item)
        if baseline_counts[key]:
            baseline_counts[key] -= 1
        else:
            result.append(item)
    return result


def format_diagnostics(rows: list[dict], cap: int = 8) -> str:
    if not rows:
        return ""
    blocks = []
    for item in rows[:cap]:
        blocks.append(
            f"[{item['classification']}] {item['path']}:{item['line']}:{item['column']} "
            f"{item['code']}: {item['message']}\n{item['frame']}"
        )
    if len(rows) > cap:
        blocks.append(f"... {len(rows) - cap} additional diagnostics retained in raw results")
    return "\n\n".join(blocks)


def is_coherent(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                return False
    return True


class DeltaDiagnosticEnv(MultiFileEnv):
    """MultiFileEnv whose checker surface is only new, target-scoped diagnostics."""

    def __init__(self, *args, baseline_diagnostics: list[dict], diagnostic_scope: set[str], **kwargs):
        super().__init__(*args, **kwargs)
        self.baseline_diagnostics = list(baseline_diagnostics)
        self.diagnostic_scope = set(diagnostic_scope)
        self.last_checker_latency = 0.0
        self.last_raw_diagnostics: list[dict] = []

    def apply_edit(self, path: str, search: str, replace: str):
        """Apply one exact, unique SEARCH/REPLACE block to a workspace file."""
        path = path or self.target
        source = self.read_file(path)
        occurrences = source.count(search)
        if occurrences != 1:
            return False, f"search occurrence count is {occurrences}, expected 1"
        updated = source.replace(search, replace, 1)
        self.chars_written += len(replace)
        if self.first_write_done:
            self.chars_deleted_after_first += len(search)
        self.first_write_done = True
        self.n_edits += 1
        Path(self._abspath(path)).write_text(updated, encoding="utf-8")
        return True, "ok"

    def raw_diagnostic_delta(self) -> list[dict]:
        current, latency = collect_diagnostics(self.ws, self.diagnostic_scope)
        self.last_checker_latency += latency
        self.last_raw_diagnostics = delta(current, self.baseline_diagnostics)
        return self.last_raw_diagnostics

    def pyrefly_diagnostics(self, path=None):
        return format_diagnostics(self.raw_diagnostic_delta())
