#!/usr/bin/env python3
"""Condition runner for the REAL-REPO efficiency suite (RefactorBench edition).

Mirrors scripts/synth_mf.py EXACTLY in interface (same flags, same per-row
metrics, same StreamAgent loop, same --dry-run prompt renderer) but the env is a
`RealRepoEnv` built from an on-disk vendored repo + its static-AST test, loaded
from scripts/real_repo_loader.py's candidate dicts (NOT an inlined files map).

The prompt shows ONLY the small editable file(s) numbered + the NAMES of the
other relevant files (the big definition file, readable via <read>/<defn>) + the
RefactorBench AST test as the spec. The symbol the fix depends on lives in the
large not-shown file, so <defn> is materially cheaper than <read> — the whole
point of the experiment.

Final-recipe invocation (condition A only):
  python scripts/real_mf.py [candidates.json] --out runs/real/real_mf_run.json \
      --model MODEL --conds A --lsp-tools [--force-lsp --relabel --save-sft] \
      [--lsp-defn] [--adapter PATH] [--names ...] [--seeds K] [--seed-start S]

  python scripts/real_mf.py candidates.json --dry-run   # render prompts, NO model,
                                                         # NO RealRepoEnv, NO pyrefly

pyrefly NOTE: a bare run uses the AST <defn> resolver (no pyrefly). Only --lsp-defn
backs <defn> with a live pyrefly LSP daemon — do NOT pass it while another pyrefly
process runs (daemon deadlocks under concurrency). --dry-run never builds an env.
"""
import os
import sys
import json
import time
import argparse

os.environ.setdefault("HF_HOME", "/mnt/nas/hf-cache")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEFAULT_CANDS = os.path.join(ROOT, "runs/real/refactorbench_candidates.json")

ap = argparse.ArgumentParser()
ap.add_argument("candidates", nargs="?", default=DEFAULT_CANDS,
                help="candidate JSON from scripts/real_repo_loader.py")
ap.add_argument("--out", default=os.path.join(ROOT, "runs/real/real_mf_run.json"))
ap.add_argument("--lsp-tools", action="store_true",
                help="advertise PULL LSP actions <defn sym=.../> and <findrefs sym=.../> alongside <read>")
ap.add_argument("--dry-run", action="store_true",
                help="render prompts for each task and exit (no model, no env, no pyrefly)")
ap.add_argument("--save-sft", action="store_true",
                help="store sft_input_ids/sft_labels in each row -> training-set harvest")
ap.add_argument("--force-lsp", action="store_true",
                help="deny <read> of non-editable files (forces the model onto <defn>/<findrefs>)")
ap.add_argument("--relabel", action="store_true",
                help="genuine on-policy relabel: mask the read-attempt tokens and keep the model's own <defn>")
ap.add_argument("--lsp-defn", action="store_true",
                help="back <defn> with a LIVE pyrefly LSP daemon (env.lsp_definition) instead of the AST resolver")
ap.add_argument("--conds", default="A", choices=["A"],
                help="condition(s) to run; the final recipe uses A only")
ap.add_argument("--names", default=None, help="comma list of task names to run (subset)")
ap.add_argument("--seeds", type=int, default=1)
ap.add_argument("--seed-start", type=int, default=0)
ap.add_argument("--temp", type=float, default=0.7)
ap.add_argument("--adapter", default=None)
ap.add_argument("--model", default="Qwen/Qwen2.5-Coder-7B-Instruct")
ap.add_argument("--gpu-only", action="store_true",
                help="force ALL weights onto cuda:0 (device_map={'':0}) instead of auto")
ap.add_argument("--max-new", type=int, default=2200)
ap.add_argument("--max-reads", type=int, default=6, help="cap on <read> calls")
ap.add_argument("--max-turns", type=int, default=12, help="cap on agent turns")
A = ap.parse_args()

# ---- load candidate tasks (the on-disk task dicts; no env constructed yet) ----
_data = json.load(open(A.candidates))
TASKS = _data["candidates"] if isinstance(_data, dict) else _data
if A.names:
    want = set(A.names.split(","))
    TASKS = [t for t in TASKS if t["name"] in want]
conds = A.conds.split(",")
n_seeds = 1 if A.temp == 0 else A.seeds


def task_meta(task):
    """(target, editable, shown) for the real-repo schema. No gold map: the
    RefactorBench AST test IS the spec (the env runs it). `shown` is the subset
    of editable files rendered numbered up front (the big definition file is in
    `file_list` but NOT shown -> the model must <read>/<defn> to reach it)."""
    editable = list(task["editable"]) or [task.get("def_file")]
    shown = list(task.get("shown") or editable)
    return editable[0], editable, shown


def _numbered(src):
    return "\n".join(f"{i+1:>3}| {ln}" for i, ln in enumerate(src.splitlines()))


def build_prompt(task, reader):
    """Mirror synth_mf.build_prompt, but driven by the RefactorBench instruction
    and an on-disk `reader(path)->src` (env.read_file at run time; a plain file
    read for --dry-run, so NO env is constructed). Shows the numbered editable
    file(s), names the other relevant files, embeds the AST test as the spec."""
    lsp_line = ("\nLanguage-server actions (cheap — return only the relevant lines): "
                "<defn sym=\"NAME\"/> shows a symbol's definition/signature (NAME may be "
                "qualified, e.g. `Class.method`); <findrefs sym=\"NAME\"/> lists where it is used."
                if A.lsp_tools else "")
    target, editable, shown = task_meta(task)
    file_list = task.get("file_list", editable)
    others = [f for f in file_list if f not in shown]
    multi = len(editable) > 1
    partial = multi and set(shown) != set(editable)   # some editable files HIDDEN -> discovery

    def _view(f):
        try:
            return f"`{f}`:\n{_numbered(reader(f))}"
        except Exception as e:
            return f"`{f}`: (could not read: {type(e).__name__})"
    body = "\n\n".join(_view(f) for f in shown)

    instr = task["instruction"].strip()
    if not multi:
        head = (f"Refactor task: {instr}\n\nEdit `{target}` so the test below passes.\n\n{body}\n\n")
        tail = f"Make line-range edits to `{target}`, then run <test/>."
    elif partial:
        head = (f"Refactor task: {instr}\n\nThe change spans MULTIPLE files. You are shown "
                f"`{shown[0]}` (below); the fix ALSO requires editing OTHER modules of the "
                f"package — find and fix EVERY affected file, or the test will still fail.\n\n{body}\n\n")
        tail = ("Inspect other modules with <read path=\"...\"/> (you get a numbered, editable view), then make "
                "line-range <edit path=\"FILE\" lines=\"START-END\"> edits to every affected module, then <test/>.")
    else:
        head = (f"Refactor task: {instr}\n\nThe change SPANS these editable files: "
                f"{', '.join('`'+f+'`' for f in editable)} — fix EVERY affected site.\n\n{body}\n\n")
        tail = ("Make line-range edits with <edit path=\"FILE\" lines=\"START-END\"> to each "
                "affected file, then run <test/>.")
    if others:
        whereabouts = (f"The workspace also contains these relevant files: {', '.join(others)} — you have "
                       f"NOT seen their contents; inspect any with <read path=\"...\"/> or look up a "
                       f"symbol with <defn sym=\"...\"/>.\n\n")
    else:
        whereabouts = ""
    test_src = open(task["test_spec"], encoding="utf-8", errors="replace").read()
    return (head + whereabouts +
            "The test that must pass (do NOT edit it; it is the spec):\n"
            f"```python\n{test_src}\n```\n" + tail + lsp_line)


# --------------------------------------------------------------------------- #
# --dry-run: render prompts WITHOUT constructing any env (no pyrefly, no model)
# --------------------------------------------------------------------------- #
if A.dry_run:
    for task in TASKS:
        def disk_reader(rel, _d=task["repo_dir"]):
            return open(os.path.join(_d, rel), encoding="utf-8", errors="replace").read()
        print(f"\n{'='*28} {task['name']} ({task['repo']}) {'='*28}")
        print(f"[symbol={task.get('target_symbol')}  conf={task.get('symbol_confidence')}  "
              f"kind={task.get('kind')}  shown={task.get('shown')}  "
              f"big={task.get('biggest_referenced_file')}({task.get('biggest_referenced_loc')}L)]")
        print("--- cond A prompt ---\n" + build_prompt(task, disk_reader))
    sys.exit(0)


# --------------------------------------------------------------------------- #
# real run (model + RealRepoEnv). Heavy imports are lazy so --dry-run never
# touches torch/transformers/GPU.
# --------------------------------------------------------------------------- #
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from scaffold.stream_agent import StreamAgent
from scaffold.real_env import RealRepoEnv

print(f"[load] {A.model}{' + '+A.adapter if A.adapter else ''}  temp={A.temp} "
      f"seeds={A.seed_start}..{A.seed_start+n_seeds-1}", flush=True)
tok = AutoTokenizer.from_pretrained(A.model)
_dm = {"": 0} if A.gpu_only else "auto"
model = AutoModelForCausalLM.from_pretrained(A.model, dtype=torch.bfloat16, device_map=_dm)
if A.adapter:
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, A.adapter)
model = model.eval()

agg = {c: {"rows": []} for c in conds}
os.makedirs(os.path.dirname(A.out), exist_ok=True)


def checkpoint():
    json.dump({"model": A.model, "config": vars(A),
               "rows": {c: agg[c]["rows"] for c in conds}}, open(A.out + ".partial", "w"))


for task in TASKS:
    target, editable, shown = task_meta(task)
    for c in conds:
        for seed in range(A.seed_start, A.seed_start + n_seeds):
            env = RealRepoEnv(repo_dir=task["repo_dir"], editable=editable,
                              test_spec=task["test_spec"], file_list=task["file_list"],
                              test_kind="ast_file", write_pyrefly_config=A.lsp_defn)
            env.reset()   # clean working tree before this seed (vendored repo persists on disk)
            agent = StreamAgent(model, tok, env,
                                max_new_tokens=A.max_new, max_reads=A.max_reads,
                                max_turns=A.max_turns, edit_mode="line",
                                temperature=A.temp, seed=seed,
                                force_lsp=A.force_lsp, relabel=A.relabel,
                                advertised_symbols=(task.get("target_symbols", []) if A.lsp_tools else []),
                                use_lsp_defn=A.lsp_defn)
            t0 = time.time()
            r = agent.run(build_prompt(task, env.read_file), target, editable=editable)
            dt = time.time() - t0
            m = r["metrics"]
            row = {"task": task["name"], "group": task["repo"], "cond": c, "seed": seed,
                   "resolved": bool(r["resolved"]), "bailed": r.get("bailed"),
                   "in_tokens": r["in_tokens"], "out_tokens": r["out_tokens"],
                   "sec": round(dt, 1), "rework_ratio": m.get("rework_ratio"),
                   "n_edits": m.get("n_edits"), "n_tests": r["n_tests"],
                   "n_reads": r["n_reads"], "n_greps": r.get("n_greps", 0), "n_lsp": r.get("n_lsp", 0),
                   "turns": r["turns"], "symbol": task.get("target_symbol"),
                   "stream_tail": r["stream"][-3000:], "events": r["events"]}
            if A.save_sft:
                row["sft_input_ids"] = r["sft_input_ids"]; row["sft_labels"] = r["sft_labels"]
                row["n_train_tokens"] = r.get("n_train_tokens")
            agg[c]["rows"].append(row)
            env.reset(); env.close()   # leave the vendored repo clean for the next task/run
            print(f"  [{task['name'][:26]:26}] {c} s{seed}: resolved={row['resolved']} "
                  f"reads={row['n_reads']} lsp={row['n_lsp']} tests={row['n_tests']} "
                  f"edits={row['n_edits']} out={row['out_tokens']} ({row['sec']}s)", flush=True)
    checkpoint()

print("\n=== aggregate ===", flush=True)
summary = {}
for c in conds:
    rs = agg[c]["rows"]
    res = [r for r in rs if r["resolved"]]
    bygrp = {}
    for g in sorted({r["group"] for r in rs}):
        sub = [r for r in rs if r["group"] == g]
        bygrp[g] = f"{sum(r['resolved'] for r in sub)}/{len(sub)}"
    summary[c] = {"resolve_rate": round(len(res)/len(rs), 3) if rs else 0, "n": len(rs),
                  "by_group": bygrp,
                  "mean_reads": round(sum(r['n_reads'] for r in rs)/max(len(rs), 1), 2),
                  "mean_lsp": round(sum(r['n_lsp'] for r in rs)/max(len(rs), 1), 2)}
    print(f"  {c}: resolve={summary[c]['resolve_rate']} ({len(res)}/{len(rs)})  "
          f"by_group={bygrp}  mean_reads={summary[c]['mean_reads']} mean_lsp={summary[c]['mean_lsp']}",
          flush=True)

json.dump({"model": A.model, "adapter": A.adapter, "config": vars(A), "summary": summary,
           "rows": {c: agg[c]["rows"] for c in conds}}, open(A.out, "w"), indent=2)
print(f"-> {A.out}", flush=True)
