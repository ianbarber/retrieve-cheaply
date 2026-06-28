#!/usr/bin/env python3
"""Resolver-coverage audit for RefactorBench candidates.

For every candidate (from scripts/real_repo_loader.py) we ask: does the task's
target symbol RESOLVE to a definition? This is exactly what the agent's
`<defn sym="X"/>` action depends on, so a low hit-rate here means the efficiency
experiment can't fire.

Two resolution paths:
  * AST (DEFAULT, pyrefly-FREE): `RealRepoEnv.goto_definition` == `SymbolResolver`.
    Strict (a bare method name returns nothing, by design) PLUS a relaxed
    whole-tree scan that reports whether the symbol is *present and qualifiable*.
  * LIVE pyrefly LSP (`RealRepoEnv.lsp_definition`): GUARDED behind `--use-lsp`,
    DEFAULT OFF. **Do not pass --use-lsp while a GPU eval is using pyrefly** —
    pyrefly's daemon deadlocks under concurrency. The main session runs that pass.

Emits CSV rows: task,repo,symbol,confidence,ast_hit,ast_file,ast_line_range,
ast_relaxed_hit,ast_relaxed_file[,lsp_hit,lsp_file].

Usage:
  python scripts/resolver_coverage_audit.py                 # AST only
  python scripts/resolver_coverage_audit.py --selftest      # unit tests, no repos
  python scripts/resolver_coverage_audit.py --use-lsp ...   # (main session only)
"""
from __future__ import annotations
import os
import sys
import csv
import json
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from scaffold.real_env import RealRepoEnv, SymbolResolver
from scripts.real_repo_loader import _relaxed_def_file, extract_symbol, parse_test

CSV_COLS = ["task", "repo", "symbol", "confidence", "ast_hit", "ast_file",
            "ast_line_range", "ast_relaxed_hit", "ast_relaxed_file"]
CSV_COLS_LSP = CSV_COLS + ["lsp_hit", "lsp_file"]


def _line_range(repo_dir, rel, span):
    """Locate `span` (a block of consecutive source lines) inside file `rel` and
    return '<start>-<end>' (1-based). Robust: matches the exact line block."""
    if not span or not rel:
        return ""
    try:
        src = open(os.path.join(repo_dir, rel), encoding="utf-8", errors="replace").read()
    except Exception:
        return ""
    lines = src.splitlines()
    sp = span.splitlines()
    if not sp:
        return ""
    for i in range(0, len(lines) - len(sp) + 1):
        if lines[i:i + len(sp)] == sp:
            return f"{i + 1}-{i + len(sp)}"
    return ""


def audit_one(task, env, use_lsp=False):
    """Resolve task['target_symbol'] (and any siblings) over the candidate's
    curated file_list. Returns a CSV-row dict. AST-only unless use_lsp."""
    repo_dir = task["repo_dir"]
    syms = task.get("target_symbols") or ([task["target_symbol"]] if task.get("target_symbol") else [])
    files = env._files_dict()

    ast_hit, ast_file, ast_range, used_sym = 0, "", "", task.get("target_symbol") or ""
    for s in syms:                       # take the first symbol that strictly resolves
        span, rel = env.goto_definition(s)   # AST-only (SymbolResolver); no pyrefly
        if rel is not None:
            ast_hit, ast_file = 1, rel
            ast_range = _line_range(repo_dir, rel, span)
            used_sym = s
            break

    # relaxed: is the symbol present ANYWHERE (incl. as a method) and qualifiable?
    rel_hit, rel_file = 0, ""
    for s in syms:
        f = _relaxed_def_file(files, s)
        if f:
            rel_hit, rel_file = 1, f
            break

    row = {"task": task["name"], "repo": task["repo"].replace("_refactor", ""),
           "symbol": used_sym, "confidence": task.get("symbol_confidence", ""),
           "ast_hit": ast_hit, "ast_file": ast_file, "ast_line_range": ast_range,
           "ast_relaxed_hit": rel_hit, "ast_relaxed_file": rel_file}

    if use_lsp:                          # GUARDED: only when explicitly requested
        lsp_hit, lsp_file = 0, ""
        for s in syms:
            span, rel = env.lsp_definition(s)   # LIVE pyrefly LSP daemon
            if rel is not None:
                lsp_hit, lsp_file = 1, rel
                break
        row["lsp_hit"], row["lsp_file"] = lsp_hit, lsp_file
    return row


def run_audit(cand_json, out_csv, use_lsp=False):
    data = json.load(open(cand_json))
    cands = data["candidates"]
    rows = []
    for task in cands:
        # AST-only resolver; write_pyrefly_config=False so we never touch pyrefly
        # config and never risk spawning a daemon on the shared socket.
        env = RealRepoEnv(repo_dir=task["repo_dir"], editable=task["editable"],
                          test_spec=task["test_spec"], file_list=task["file_list"],
                          test_kind="ast_file", write_pyrefly_config=use_lsp)
        try:
            rows.append(audit_one(task, env, use_lsp=use_lsp))
        finally:
            env.close()
    cols = CSV_COLS_LSP if use_lsp else CSV_COLS
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})
    return rows, cols


# --------------------------------------------------------------------------- #
# self-test (NON-pyrefly parts): symbol extraction, AST resolution, CSV I/O
# --------------------------------------------------------------------------- #
def selftest():
    import tempfile, subprocess
    ok = []

    def chk(name, cond, detail=""):
        ok.append(bool(cond))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))

    # 1. symbol extraction (loader, pyrefly-free)
    sym, syms, conf, method = extract_symbol(
        "expand-router-string-to-utils",
        "Move expand_router_string to celery/app/utils.py and import it into routes.",
        ["expand_router_string"], {"expand_router_string", "Router"})
    chk("extract_symbol picks the moved function", sym == "expand_router_string",
        f"{sym} ({conf}/{method})")

    # 2. AST resolution + line range over a tiny on-disk git repo (no pyrefly)
    d = tempfile.mkdtemp(prefix="rca_self_")
    subprocess.run(["git", "-C", d, "init", "-q"], check=True)
    pkg = os.path.join(d, "pkg")
    os.makedirs(pkg)
    big = ("# header\n" * 5) + "def helper(x):\n    return x + 1\n\nGREETING = 'hi'\n"
    open(os.path.join(pkg, "lib.py"), "w").write(big)
    open(os.path.join(pkg, "caller.py"), "w").write("from pkg.lib import helper\nhelper(2)\n")
    env = RealRepoEnv(repo_dir=d, editable=["pkg/caller.py"], test_spec="true",
                      file_list=["pkg/lib.py", "pkg/caller.py"], test_kind="command",
                      write_pyrefly_config=False)
    span, rel = env.goto_definition("helper")
    chk("goto_definition('helper') -> pkg/lib.py (AST)",
        rel == "pkg/lib.py" and span and span.startswith("def helper"), f"{rel}")
    rng = _line_range(d, rel, span)
    chk("line range of helper is 6-7", rng == "6-7", rng)
    task = {"name": "t", "repo": "x_refactor", "repo_dir": d,
            "target_symbol": "helper", "target_symbols": ["helper"],
            "symbol_confidence": "high"}
    row = audit_one(task, env, use_lsp=False)
    chk("audit_one row: ast_hit==1 and relaxed hit", row["ast_hit"] == 1 and row["ast_relaxed_hit"] == 1,
        str(row))
    # bare-method strict-miss but relaxed-hit
    open(os.path.join(pkg, "cls.py"), "w").write("class A:\n    def meth(self):\n        return 1\n")
    env2 = RealRepoEnv(repo_dir=d, editable=["pkg/cls.py"], test_spec="true",
                       file_list=["pkg/cls.py"], test_kind="command", write_pyrefly_config=False)
    t2 = {"name": "t2", "repo": "x_refactor", "repo_dir": d,
          "target_symbol": "meth", "target_symbols": ["meth"], "symbol_confidence": "med"}
    r2 = audit_one(t2, env2, use_lsp=False)
    chk("bare method 'meth': strict miss, relaxed hit",
        r2["ast_hit"] == 0 and r2["ast_relaxed_hit"] == 1, str(r2))
    env.close(); env2.close()

    # 3. CSV round-trip
    cpath = os.path.join(d, "out.csv")
    with open(cpath, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        w.writerow({k: row.get(k, "") for k in CSV_COLS})
    back = list(csv.DictReader(open(cpath)))
    chk("CSV round-trips one row with the strict columns",
        len(back) == 1 and back[0]["symbol"] == "helper" and back[0]["ast_hit"] == "1",
        str(back[0]))

    import shutil
    shutil.rmtree(d, ignore_errors=True)
    n = sum(ok)
    print(f"\nSELFTEST: {n}/{len(ok)} passed")
    return 0 if n == len(ok) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates",
                    default=os.path.join(ROOT, "runs/real/refactorbench_candidates.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "runs/real/resolver_coverage.csv"))
    ap.add_argument("--use-lsp", action="store_true",
                    help="ALSO run the LIVE pyrefly LSP path (deadlocks under "
                         "concurrent pyrefly; main session only). DEFAULT OFF.")
    ap.add_argument("--selftest", action="store_true",
                    help="run unit tests of the non-pyrefly parts and exit")
    A = ap.parse_args()

    if A.selftest:
        sys.exit(selftest())

    rows, cols = run_audit(A.candidates, A.out, use_lsp=A.use_lsp)
    n = len(rows)
    ast_hits = sum(r["ast_hit"] for r in rows)
    rel_hits = sum(r["ast_relaxed_hit"] for r in rows)
    print(f"{'TASK':42} {'SYMBOL':30} STRICT RELAXED  FILE")
    print("-" * 100)
    for r in rows:
        print(f"{r['task'][:42]:42} {r['symbol'][:30]:30} "
              f"{r['ast_hit']:^6} {r['ast_relaxed_hit']:^7}  {r['ast_file'] or r['ast_relaxed_file']}")
    print("-" * 100)
    print(f"AST strict hit-rate : {ast_hits}/{n} = {ast_hits / max(n,1):.0%}")
    print(f"AST relaxed hit-rate: {rel_hits}/{n} = {rel_hits / max(n,1):.0%}  (present + qualifiable)")
    if A.use_lsp:
        lsp_hits = sum(r.get("lsp_hit", 0) for r in rows)
        print(f"LIVE pyrefly LSP    : {lsp_hits}/{n} = {lsp_hits / max(n,1):.0%}")
    print(f"-> {A.out}")


if __name__ == "__main__":
    main()
