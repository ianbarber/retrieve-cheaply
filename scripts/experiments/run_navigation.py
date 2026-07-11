#!/usr/bin/env python3
"""Model runner for the frozen types x semantic-navigation experiment."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scaffold.stream_agent import StreamAgent  # noqa: E402
from scaffold.tooling import find_pyrefly  # noqa: E402
from scripts.experiments.navigation_tasks import (  # noqa: E402
    PROTOCOL_VERSION,
    _protocol_hashes,
    build_prompt,
    build_tasks,
    make_env,
    run_heldout,
)


ARMS = (
    "baseline", "semantic_auto", "semantic_avail", "semantic_framed",
    "semantic_span_control", "positive_control",
)
CORE_CELLS = (
    ("typed", "baseline"), ("typed", "semantic_auto"),
    ("erased", "baseline"), ("erased", "semantic_auto"),
)
DEPLOYMENT_CELLS = (
    ("typed", "semantic_avail"), ("typed", "semantic_framed"),
)
CONTROL_CELLS = (
    ("typed", "semantic_span_control"), ("typed", "positive_control"),
)

TOOLS = """You are fixing one one-line Python bug in an implementation module under pkg/units/.
Tools (emit one tag, inspect the result, then continue):
  <grep pat="regex"/>              search source and return file:line hits
  <read path="F" lines="A-B"/>     read a numbered source range
  <edit path="F" lines="A-B">...code...</edit>  replace a numbered range
  <test/>                            run the behavioral test
  <done/>                            finish after the test passes
"""
SEMANTIC = (
    "  <defn sym=\"NAME\" file=\"F\" line=\"N\" col=\"C\"/>  "
    "ask the language server which definition binds at a use site\n"
)
NEUTRAL_SYS = TOOLS + SEMANTIC
AUTO_SYS = TOOLS + (
    "A language-server result from the visible call site is supplied in the user message. It is the "
    "current source definition, not a proposed fix. Use it as compact context; infer and apply a fix only "
    "if the task evidence supports one.\n"
)
FRAMED_SYS = TOOLS + SEMANTIC + (
    "The semantic definition lookup is cheap and precise when same-named implementations are ambiguous. "
    "Prefer one lookup at the visible call site when it can replace registry tracing.\n"
)
POSITIVE_SYS = """You are completing an edit-only positive control. The user supplies the exact
known-correct method with its file and line range. Copy it with <edit path="F" lines="A-B">...</edit>,
then emit <test/> and <done/>. Do not retrieve or infer another implementation.
"""
def _method_from_lsp(task: dict, variant: str, env) -> tuple[str, str | None, float]:
    use = task["variants"][variant]["use_site"]
    started = time.perf_counter()
    enclosing, path = env.lsp_definition(
        task["method"], file=use["file"], line=use["line"], col=use["col"]
    )
    latency = time.perf_counter() - started
    if not path or not enclosing:
        return "(language server returned no discriminating definition)", path, latency
    source = env.read_file(path)
    lines = source.splitlines()
    tree = ast.parse(source)
    candidates = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == task["method"]:
            end = node.end_lineno or node.lineno
            span = "\n".join(lines[node.lineno - 1:end])
            if span in enclosing:
                candidates.append((node.lineno, end, span))
    if len(candidates) != 1:
        return f"# {path}\n{enclosing}", path, latency
    start, end, span = candidates[0]
    return _format_method_span(path, start, end, span), path, latency


def _format_method_span(path: str, start: int, end: int, span: str) -> str:
    numbered = "\n".join(f"{start + i:>4}| {line}" for i, line in enumerate(span.splitlines()))
    return f"# {path}:{start}-{end}\n{numbered}"


def _method_from_metadata(task: dict) -> tuple[str, str]:
    data = task["target_method_span"]
    return (
        _format_method_span(task["target_path"], data["start"], data["end"], data["source"]),
        task["target_path"],
    )


def _positive_result(task: dict) -> str:
    data = task["target_method_span"]
    gold = task["gold"]
    if gold["start"] != gold["end"] or not (data["start"] <= gold["start"] <= data["end"]):
        raise ValueError("positive control requires a one-line gold edit inside the supplied method")
    lines = data["source"].splitlines()
    lines[gold["start"] - data["start"]] = gold["new_text"]
    numbered = "\n".join(
        f"{data['start'] + i:>4}| {line}"
        for i, line in enumerate(lines)
    )
    return f"# {task['target_path']}:{data['start']}-{data['end']}\n{numbered}"


def _metrics(task: dict, events: list[dict], supplied_path: str | None) -> dict:
    first_edit_idx = next(
        (i for i, event in enumerate(events)
         if event.get("type") in ("line_edit", "edit") and event.get("ok")),
        len(events),
    )
    before = events[:first_edit_idx]
    localized = supplied_path == task["target_path"] or any(
        (event.get("path") == task["target_path"]
         and event.get("type") in ("read", "defn"))
        or (event.get("type") == "grep" and event.get("paths") == [task["target_path"]])
        for event in before
    )
    edits = [event for event in events if event.get("type") in ("line_edit", "edit") and event.get("ok")]
    wrong = [event for event in edits if event.get("path") != task["target_path"]]
    first_defn = next((i for i, event in enumerate(events) if event.get("type") == "defn"), None)
    read_after_semantic = bool(supplied_path is not None and any(
        event.get("type") == "read" and event.get("path") == task["target_path"]
        for event in before
    ))
    if first_defn is not None:
        read_after_semantic = any(
            event.get("type") == "read" and event.get("path") == task["target_path"]
            for event in events[first_defn + 1:first_edit_idx]
        )
    return {
        "correct_file_localized_before_first_edit": localized,
        "first_edit_path": edits[0].get("path") if edits else None,
        "wrong_file_edits": len(wrong),
        "semantic_then_target_read": read_after_semantic,
    }


def _control_floor_failure(cells: str, rows: list[dict]) -> str | None:
    required = {
        "positive": {"positive_control"},
        "span-control": {"semantic_span_control"},
        "controls": {"positive_control", "semantic_span_control"},
    }.get(cells)
    if required is None:
        return None
    observed = {row["arm"] for row in rows}
    if not rows or observed != required or not all(row["held_out_pass"] for row in rows):
        return f"{cells} floor failed; stop before causal pilot"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-7B-Instruct")
    parser.add_argument("--revision", default=None)
    parser.add_argument("--split", choices=("pilot", "apparatus", "confirmation"), default="pilot")
    parser.add_argument(
        "--cells", choices=("core", "deployment", "all", "positive", "span-control", "controls"),
        default="core",
    )
    parser.add_argument("--names", default=None)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-new", type=int, default=2200)
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--max-reads", type=int, default=12)
    parser.add_argument("--gpu-only", action="store_true")
    parser.add_argument("--tmp-root", default=None)
    args = parser.parse_args()

    cells = {
        "core": CORE_CELLS,
        "deployment": DEPLOYMENT_CELLS,
        "all": tuple(dict.fromkeys(CORE_CELLS + DEPLOYMENT_CELLS)),
        "positive": (("typed", "positive_control"),),
        "span-control": (("typed", "semantic_span_control"),),
        "controls": CONTROL_CELLS,
    }[args.cells]
    root = args.tmp_root or str(Path(tempfile.gettempdir()) / "streams_navigation_v2_runs")
    tasks = build_tasks(Path(root) / args.split, args.split)
    if args.names:
        wanted = set(args.names.split(","))
        tasks = [task for task in tasks if task["name"] in wanted]
    if not tasks:
        raise ValueError("no navigation tasks selected")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision)
    device_map = {"": 0} if args.gpu_only else "auto"
    model = AutoModelForCausalLM.from_pretrained(
        args.model, revision=args.revision, dtype=torch.bfloat16, device_map=device_map
    ).eval()
    model_meta = {
        "revision": getattr(model.config, "_commit_hash", None),
        "transformers": __import__("transformers").__version__,
        "torch": torch.__version__,
        "dtype": str(model.dtype),
    }

    rows = []
    pyrefly = find_pyrefly()
    pyrefly_version = __import__("subprocess").run(
        [pyrefly, "--version"], capture_output=True, text=True
    ).stdout.strip()
    n_seeds = 1 if args.temperature == 0 else args.seeds
    for task in tasks:
        for variant, arm in cells:
            for seed in range(args.seed_start, args.seed_start + n_seeds):
                env = make_env(task, variant)
                try:
                    supplied = None
                    supplied_path = None
                    lsp_latency = 0.0
                    prompt = build_prompt(task, variant)
                    if arm in ("semantic_auto", "semantic_span_control"):
                        if arm == "semantic_auto":
                            supplied, supplied_path, lsp_latency = _method_from_lsp(task, variant, env)
                        else:
                            supplied, supplied_path = _method_from_metadata(task)
                        if variant == "typed" and supplied_path != task["target_path"]:
                            raise RuntimeError(
                                f"typed automatic result did not resolve the gold override: {supplied_path}"
                            )
                        if variant == "erased" and supplied_path not in (None, "pkg/base.py"):
                            raise RuntimeError(
                                f"erased automatic result unexpectedly discriminated: {supplied_path}"
                            )
                        if env.lsp_errors:
                            raise RuntimeError(f"automatic semantic query failed: {env.lsp_errors}")
                        if task["gold"]["new_text"] in supplied:
                            raise RuntimeError("semantic context contains the gold replacement")
                        prompt += (
                            "\n\nThe following current source span was supplied from a language-server "
                            "definition result at the visible call site. It is source context, not a "
                            "proposed correction.\n<semantic_result kind=\"current_source\">\n"
                            + supplied + "\n</semantic_result>"
                        )
                    elif arm == "positive_control":
                        supplied = _positive_result(task)
                        supplied_path = task["target_path"]
                        prompt += (
                            "\n\nThis is an edit-competence positive control. Localization and retrieval are "
                            "already complete. Copy the known-correct method below into the stated file "
                            "and lines, run the test, and stop. Do not grep, inspect the registry, or choose "
                            "another implementation.\n<correct_definition_control>\n"
                            + supplied + "\n</correct_definition_control>"
                        )

                    system = FRAMED_SYS if arm == "semantic_framed" else NEUTRAL_SYS
                    if arm in ("semantic_auto", "semantic_span_control"):
                        system = AUTO_SYS
                    if arm == "positive_control":
                        system = POSITIVE_SYS
                    tool_enabled = arm in ("semantic_avail", "semantic_framed")
                    if not tool_enabled and arm not in (
                        "positive_control", "semantic_auto", "semantic_span_control"
                    ):
                        system = TOOLS
                    agent = StreamAgent(
                        model, tokenizer, env, edit_mode="line", sys_override=system,
                        max_new_tokens=args.max_new, max_turns=args.max_turns,
                        max_reads=0 if arm == "positive_control" else args.max_reads,
                        temperature=args.temperature, seed=seed,
                        use_lsp_defn=tool_enabled, lsp_disabled=not tool_enabled,
                        lsp_fallback=False,
                    )
                    started = time.perf_counter()
                    result = agent.run(prompt, "pkg/app.py", editable=task["editable"])
                    elapsed = time.perf_counter() - started
                    if arm == "semantic_span_control" and (
                        result["n_lsp"] or env.lsp_latencies or env.lsp_errors
                    ):
                        raise RuntimeError("metadata span control unexpectedly queried the language server")
                    held_out_pass = run_heldout(task, variant)
                    row = {
                        "task": task["name"], "family": task["seed"], "split": args.split,
                        "variant": variant, "arm": arm, "seed": seed,
                        "resolved": held_out_pass, "visible_pass": bool(result["resolved"]),
                        "held_out_pass": held_out_pass, "bailed": result.get("bailed"),
                        "in_tokens": result["in_tokens"], "out_tokens": result["out_tokens"],
                        "turns": result["turns"], "n_reads": result["n_reads"],
                        "n_lsp": result["n_lsp"], "n_tests": result["n_tests"],
                        "n_edits": result["n_edits"], "wall_sec": round(elapsed, 3),
                        "server_latency_ms": round(sum(env.lsp_latencies) * 1000, 1),
                        "server_call_latencies_ms": [round(value * 1000, 1)
                                                     for value in env.lsp_latencies],
                        "server_errors": list(env.lsp_errors),
                        "semantic_supplied_path": supplied_path,
                        "semantic_payload_sha256": (
                            hashlib.sha256(supplied.encode()).hexdigest() if supplied else None
                        ),
                        "semantic_payload_source": (
                            "live_lsp" if arm == "semantic_auto" else
                            "pristine_task_metadata" if arm == "semantic_span_control" else None
                        ),
                        **_metrics(task, result["events"], supplied_path),
                        "events": result["events"], "stream_tail": result["stream"][-2500:],
                    }
                    rows.append(row)
                    print(f"{task['name']} {variant}/{arm} s{seed}: pass={row['resolved']} "
                          f"in={row['in_tokens']} lsp={row['n_lsp']} edits={row['n_edits']}", flush=True)
                finally:
                    env.close()
                Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                Path(args.out).write_text(json.dumps({
                    "protocol": PROTOCOL_VERSION, "model": args.model,
                    "model_meta": model_meta, "config": vars(args), "cells": cells,
                    "protocol_source_sha256": _protocol_hashes(),
                    "pyrefly": {"path": pyrefly, "version": pyrefly_version}, "rows": rows,
                }, indent=2) + "\n", encoding="utf-8")
    floor_failure = _control_floor_failure(args.cells, rows)
    if floor_failure:
        print(floor_failure, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
