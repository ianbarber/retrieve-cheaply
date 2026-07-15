#!/usr/bin/env python3
"""Paired whole-file, textual, and compact-definition retrieval experiment.

The historical efficiency result compared compact definitions with whole-file reads. This
protocol keeps the tasks, model, editing interface, tests, and budgets fixed while introducing
the missing practitioner baseline: grep plus ranged reads. The definition arm retains those
textual tools as a fallback, so it estimates the value of adding compact semantic retrieval to
an already capable text interface.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scaffold.mock_env import MultiFileEnv  # noqa: E402
from scaffold.stream_agent import StreamAgent  # noqa: E402
from scripts.synth_tasks_effic_real2 import TASKS_EFFIC_REAL2  # noqa: E402


PROTOCOL_VERSION = "retrieval-paired-v1"
ARMS = ("whole", "text", "definition")

COMMON = """You are implementing a small Python target against an unfamiliar repository API.
The editable file is `target.py`; its numbered contents and the behavioral test are in the user
message. Use the smallest useful retrieval action, edit only `target.py`, run the test, and finish.

Tools (emit one tag, inspect the result, then continue):
  <edit path="target.py" lines="A-B">...code...</edit>  replace a numbered range
  <test/>                                                  run the behavioral test
  <done/>                                                  finish after the test passes
"""
WHOLE_SYS = COMMON + """  <read path="F"/>                                         read a repository file

Repository context is available through whole-file reads.
"""
TEXT_SYS = COMMON + """  <grep pat="REGEX"/>                                     search source as file:line hits
  <read path="F" lines="A-B"/>                           read a numbered source range
  <read path="F"/>                                       read a whole file when truly necessary

Prefer grep followed by the narrowest useful range over reading a large file in full.
"""
DEFINITION_SYS = TEXT_SYS + """  <defn sym="NAME"/>                                     return a compact definition span

Use a compact definition when it can replace textual localization and broader reading; retain
grep and ranged reads as fallbacks when the definition is insufficient.
"""
SYSTEMS = {"whole": WHOLE_SYS, "text": TEXT_SYS, "definition": DEFINITION_SYS}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _protocol_hashes() -> dict[str, str]:
    paths = [
        Path(__file__).resolve(),
        ROOT / "scripts" / "analysis" / "analyze_retrieval_paired.py",
        ROOT / "scripts" / "synth_tasks_effic_real2.py",
        ROOT / "scaffold" / "stream_agent.py",
        ROOT / "scaffold" / "mock_env.py",
    ]
    return {str(path.relative_to(ROOT)): _sha(path) for path in paths}


def _numbered(source: str) -> str:
    return "\n".join(f"{index:>3}| {line}" for index, line in enumerate(source.splitlines(), 1))


def build_prompt(task: dict) -> str:
    other_files = ", ".join(path for path in sorted(task["files"]) if path != task["target"])
    return (
        f"Implement `{task['target']}` so the test passes. The imported API `{task['symbol']}` is "
        "unfamiliar; retrieve its repository definition or implementation rather than guessing.\n\n"
        f"`{task['target']}`:\n{_numbered(task['files'][task['target']])}\n\n"
        f"Other repository files: {other_files}\n\n"
        f"Behavioral test:\n```python\n{task['test']}```"
    )


def _definition_lines(source: str, symbol: str) -> tuple[int, int]:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol:
            return node.lineno, node.end_lineno or node.lineno
    raise ValueError(f"definition not found: {symbol}")


def validate_tasks(tasks: list[dict]) -> list[dict]:
    rows = []
    for task in tasks:
        env = MultiFileEnv(task["files"], task["target"], task["test"], skip_pyrefly=True)
        try:
            base_fails = not env.run_tests()["resolved"]
            span, path = env.goto_definition(task["symbol"])
            start, end = _definition_lines(task["files"][task["defn_file"]], task["symbol"])
            grep_hits = []
            pattern = re.compile(rf"^\s*(?:def|class)\s+{re.escape(task['symbol'])}\b")
            for rel, source in task["files"].items():
                grep_hits.extend(
                    (rel, line_no) for line_no, line in enumerate(source.splitlines(), 1)
                    if pattern.search(line)
                )
            gold_env = MultiFileEnv(
                {**task["files"], task["target"]: task["gold_target"]},
                task["target"], task["test"], skip_pyrefly=True,
            )
            try:
                gold_passes = bool(gold_env.run_tests()["resolved"])
            finally:
                gold_env.close()
            file_lines = len(task["files"][task["defn_file"]].splitlines())
            span_lines = len((span or "").splitlines())
            checks = {
                "base_fails": base_fails,
                "gold_passes": gold_passes,
                "definition_resolves": path == task["defn_file"] and bool(span),
                "definition_span_matches": span == task["symbol_defns"]["defn"][task["symbol"]],
                "text_search_localizes": (task["defn_file"], start) in grep_hits,
                "compact_vs_file": span_lines * 5 < file_lines,
                "range_valid": 1 <= start <= end <= file_lines,
            }
            rows.append({
                "task": task["name"], "symbol": task["symbol"],
                "definition_path": path, "definition_start": start, "definition_end": end,
                "definition_lines": span_lines, "file_lines": file_lines,
                "grep_hits": grep_hits, "checks": checks, "passed": all(checks.values()),
            })
        finally:
            env.close()
    return rows


def _event_metrics(events: list[dict], definition_path: str) -> dict:
    first_defn = next((index for index, event in enumerate(events) if event.get("type") == "defn"), None)
    return {
        "n_grep": sum(event.get("type") == "grep" for event in events),
        "n_ranged_read": sum(
            event.get("type") == "read" and event.get("ranged") for event in events
        ),
        "n_whole_read": sum(
            event.get("type") == "read" and not event.get("ranged") for event in events
        ),
        "n_definition": sum(event.get("type") == "defn" for event in events),
        "retrieval_response_chars": sum(
            int(event.get("response_chars") or 0)
            for event in events if event.get("type") in {"grep", "read", "defn"}
        ),
        "definition_then_defining_file_read": bool(first_defn is not None and any(
            event.get("type") == "read" and event.get("path") == definition_path
            for event in events[first_defn + 1:]
        )),
    }


def _write_payload(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--validation-out", default=None)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--model", default="Qwen/Qwen3.5-27B")
    parser.add_argument("--revision", default=None)
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--names", default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--max-new", type=int, default=1800)
    parser.add_argument("--max-turns", type=int, default=10)
    parser.add_argument("--max-reads", type=int, default=6)
    parser.add_argument("--live-lsp", action="store_true")
    parser.add_argument("--gpu-only", action="store_true")
    args = parser.parse_args()

    out = Path(args.out)
    if out.exists():
        raise FileExistsError(f"refusing to overwrite retrieval result: {out}")
    arms = args.arms.split(",")
    unknown = set(arms) - set(ARMS)
    if unknown:
        raise ValueError(f"unknown arms: {sorted(unknown)}")
    wanted = set(args.names.split(",")) if args.names else None
    tasks = [task for task in TASKS_EFFIC_REAL2 if wanted is None or task["name"] in wanted]
    if not tasks:
        raise ValueError("no retrieval tasks selected")

    validation_rows = validate_tasks(tasks)
    validation = {
        "protocol": PROTOCOL_VERSION, "kind": "retrieval_mechanical_validation",
        "protocol_source_sha256": _protocol_hashes(), "rows": validation_rows,
        "passed": all(row["passed"] for row in validation_rows),
    }
    if args.validation_out:
        validation_path = Path(args.validation_out)
        if validation_path.exists():
            raise FileExistsError(f"refusing to overwrite validation result: {validation_path}")
        _write_payload(validation_path, validation)
    for row in validation_rows:
        print(f"{row['task']}: {'PASS' if row['passed'] else 'FAIL'} "
              f"span={row['definition_lines']} file={row['file_lines']} hits={len(row['grep_hits'])}")
    if not validation["passed"]:
        return 2
    if args.validate_only:
        return 0

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, revision=args.revision, dtype=torch.bfloat16,
        device_map={"": 0} if args.gpu_only else "auto",
    ).eval()
    model_meta = {
        "revision": getattr(model.config, "_commit_hash", None),
        "transformers": __import__("transformers").__version__,
        "torch": torch.__version__, "dtype": str(model.dtype),
    }
    rows = []
    n_seeds = 1 if args.temperature == 0 else args.seeds
    for task in tasks:
        for seed in range(args.seed_start, args.seed_start + n_seeds):
            for arm in arms:
                env = MultiFileEnv(task["files"], task["target"], task["test"], skip_pyrefly=True)
                try:
                    agent = StreamAgent(
                        model, tokenizer, env, edit_mode="line", sys_override=SYSTEMS[arm],
                        max_new_tokens=args.max_new, max_turns=args.max_turns,
                        max_reads=args.max_reads, temperature=args.temperature, seed=seed,
                        use_lsp_defn=bool(args.live_lsp and arm == "definition"),
                        lsp_disabled=arm != "definition", lsp_fallback=not args.live_lsp,
                    )
                    started = time.perf_counter()
                    result = agent.run(build_prompt(task), task["target"], editable=[task["target"]])
                    wall = time.perf_counter() - started
                    row = {
                        "task": task["name"], "group": task["group"], "symbol": task["symbol"],
                        "definition_path": task["defn_file"], "arm": arm, "seed": seed,
                        "resolved": bool(result["resolved"]), "done_seen": bool(result.get("done_seen")),
                        "in_tokens": result["in_tokens"], "out_tokens": result["out_tokens"],
                        "total_tokens": result["in_tokens"] + result["out_tokens"],
                        "turns": result["turns"], "n_edits": result["n_edits"],
                        "n_tests": result["n_tests"], "wall_sec": round(wall, 3),
                        "termination_reason": result["termination_reason"],
                        **_event_metrics(result["events"], task["defn_file"]),
                        "events": result["events"], "stream_tail": result["stream"][-2500:],
                    }
                    rows.append(row)
                    print(f"{task['name']} {arm} s{seed}: pass={row['resolved']} "
                          f"total={row['total_tokens']} grep={row['n_grep']} "
                          f"range={row['n_ranged_read']} whole={row['n_whole_read']} "
                          f"defn={row['n_definition']}", flush=True)
                finally:
                    env.close()
                _write_payload(out, {
                    "protocol": PROTOCOL_VERSION, "kind": "paired_retrieval",
                    "model": args.model, "model_meta": model_meta, "config": vars(args),
                    "protocol_source_sha256": _protocol_hashes(), "validation": validation,
                    "rows": rows,
                })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
