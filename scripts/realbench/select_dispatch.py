#!/usr/bin/env python3
"""Dispatch-ambiguity selection scanner for the real-repo experiment.

Motivation (docs/real_repo_progress.md, 2026-07-02 "semantic vs textual" / dispatch sections):
`grep 'def <method>'` is genuinely UNDECIDABLE -- not merely noisy -- when the same method name is
defined/overridden on MANY classes (a base method overridden down a class hierarchy, or the same
method on many sibling classes). Which definition binds depends on the receiver's *static type*, which
grep cannot compute but a type-aware go-to-definition (pyrefly LSP) can. Verified shapes we already
know: django backend `operations.py` methods (`date_extract_sql` etc., one def per DB backend),
django `Field` methods (`to_python`/`get_internal_type`/`formfield`, 30+ overrides), sympy printer
`_print_X` methods (`_print_Pow`/`_print_Symbol`, 15+ Printer subclasses).

For each SWE-bench Verified task this scanner checks out the repo at base_commit and, from the GOLD
patch, identifies the method-call symbols the fix HINGES on:
  * EDIT symbols  -- methods whose body the patch modifies (enclosing `def` of the changed lines in the
                     base file) or a `def <name>` that appears in the added lines (the bug IS in one
                     specific override among many -- the strongest signal).
  * CALL symbols  -- methods invoked as `x.method(` in the added lines (the fix depends on dispatch of
                     an ambiguous method).
For every such symbol it counts how many `def <method>` definitions exist across the repo's non-test
source (the "override count"), how many files and how many classes those defs span, and whether the
edited site is itself one of those overrides. Tasks are scored by the maximum override count among the
symbols the fix hinges on. Methods with 0 in-repo defs (builtin / external receiver-type case) are
recorded separately but NOT ranked -- that is the distinct "receiver-type" category.

Ranking key = (fix_edits_override, max_override_count, n_classes) descending: edited-override tasks
(the cleanest dispatch bugs) first, then by ambiguity magnitude.

  python scripts/realbench/select_dispatch.py --per-repo 25 \
      --repos django/django,sympy/sympy,scikit-learn/scikit-learn,astropy/astropy,\
matplotlib/matplotlib,pydata/xarray,sphinx-doc/sphinx,pytest-dev/pytest,psf/requests,pylint-dev/pylint \
      --out runs/realbench/dispatch_candidates.json
"""
import os
import re
import sys
import ast
import json
import argparse
import warnings
from collections import defaultdict

warnings.filterwarnings("ignore")   # docstrings with `\*` raise SyntaxWarning on parse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from scripts.realbench import swe_loader as L

RESOLVER_FILE_CAP = 2500   # bound the def-index file set on huge repos (django/sympy stay under this)
MIN_AMBIG = 2              # override_count >= 2 to be "ambiguous" at all
STRONG_AMBIG = 5           # the condition we want: >= 5 overrides
GENERIC_MAX = 60           # override_count >= this => a lifecycle/protocol method, not domain dispatch

# Ubiquitous framework lifecycle/protocol methods: defined on almost every class, so the receiver's
# static type at the edit site is obvious (you are editing one specific class). These pass the raw
# "many defs" test but are NOT the interesting receiver-type-dispatch condition -- flagged, not ranked
# as sweet-spot. (Dunders and any method with >= GENERIC_MAX overrides are also treated as generic.)
GENERIC_METHODS = {"fit", "predict", "transform", "fit_transform", "predict_proba", "score",
                   "forward", "backward", "setup", "teardown", "run", "reset", "build", "clean",
                   "validate", "save", "load", "serialize", "deserialize", "render", "close"}


# --------------------------------------------------------------------------- file selection
def _top_package(rel):
    return rel.split("/")[0] if "/" in rel else ""


def is_test_file(rel):
    base = rel.split("/")[-1]
    return ("/tests/" in "/" + rel or "/test/" in "/" + rel
            or base.startswith("test_") or base.endswith("_test.py") or base == "conftest.py")


def resolver_files(repo_dir, edited_files):
    """Repo-relative .py source dict scoped to the top packages of the edited files (bounded), test
    files excluded -- the "repo's non-test source" over which we count method definitions."""
    pkgs = {_top_package(f) for f in edited_files if _top_package(f)}
    files = {}
    for rel in L.repo_py_files(repo_dir):
        if pkgs and rel.split("/")[0] not in pkgs:
            continue
        if is_test_file(rel):
            continue
        try:
            files[rel] = open(os.path.join(repo_dir, rel), encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        if len(files) >= RESOLVER_FILE_CAP:
            break
    return files


# --------------------------------------------------------------------------- AST indexing
def _walk_defs(tree):
    """Yield (name, enclosing_class_or_None, lineno, end_lineno) for every def in a module tree.
    The enclosing class is the *innermost* ClassDef; defs nested inside a function have class None."""
    out = []

    def visit(node, cls):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append((child.name, cls, child.lineno, getattr(child, "end_lineno", child.lineno)))
                visit(child, None)
            else:
                visit(child, cls)

    visit(tree, None)
    return out


def build_def_index(files):
    """name -> list of (rel, class_or_None) for every `def name` across the non-test source.
    Mirrors what `grep -rE '^\\s*def name'` would count, but with class context attached."""
    index = defaultdict(list)
    for rel, src in files.items():
        try:
            tree = ast.parse(src)
        except Exception:
            continue
        for name, cls, _s, _e in _walk_defs(tree):
            index[name].append((rel, cls))
    return index


# --------------------------------------------------------------------------- patch -> edited methods
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def touched_old_lines(patch, target_rel):
    """Old-file line numbers the patch *changes* in `target_rel`: every removed line, plus the anchor
    line each insertion precedes. Context (unchanged) lines are NOT recorded -- otherwise a method that
    merely surrounds a change would be mis-flagged as edited. Used to find the enclosing `def` in the
    base file that the fix actually modifies."""
    out, cur, oldno = [], None, None
    for ln in patch.splitlines():
        m = re.match(r"^\+\+\+ b/(.+)$", ln)
        if m:
            cur, oldno = m.group(1), None
            continue
        if ln.startswith("--- "):
            continue
        h = _HUNK.match(ln)
        if h:
            oldno = int(h.group(1)) if cur == target_rel else None
            continue
        if cur != target_rel or oldno is None:
            continue
        if ln.startswith("\\"):            # "\ No newline at end of file"
            continue
        if ln.startswith("-"):             # removed line: exists in old file at oldno (a change)
            out.append(oldno); oldno += 1
        elif ln.startswith("+"):           # inserted line: anchored at the current old position (a change)
            out.append(oldno)
        else:                              # context line: advances old position but is NOT a change
            oldno += 1
    return out


def enclosing_defs(src, old_lines):
    """Map each changed old-line to the innermost def that covers it. Returns {name: is_method}."""
    try:
        tree = ast.parse(src)
    except Exception:
        return {}
    spans = _walk_defs(tree)   # (name, cls, start, end)
    hit = {}
    for L_ in old_lines:
        best = None
        for name, cls, s, e in spans:
            if s <= L_ <= e:
                if best is None or (e - s) < (best[3] - best[2]):
                    best = (name, cls, s, e)
        if best is not None:
            name, cls = best[0], best[1]
            hit[name] = hit.get(name, False) or (cls is not None)
    return hit


_ADDED_DEF = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(")
_CALL = re.compile(r"\.([a-z_]\w+)\s*\(")

# call-target noise: builtins/very-common methods that are never the interesting in-repo override.
_CALL_NOISE = {"format", "join", "split", "strip", "lower", "upper", "encode", "decode", "startswith",
               "endswith", "keys", "values", "items", "append", "extend", "pop", "update", "add",
               "get", "setdefault", "copy", "replace", "read", "write", "close", "group", "match",
               "search", "sub", "findall", "sort", "index", "count", "insert", "remove", "isoformat"}


def hinge_symbols(patch, edited_py, base_files):
    """Return {name: {'edit': bool, 'edit_is_method': bool, 'call': bool}} for the fix's hinge methods."""
    added = L.added_lines_by_file(patch)
    syms = {}

    def touch(name, edit=False, edit_is_method=False, call=False):
        d = syms.setdefault(name, {"edit": False, "edit_is_method": False, "call": False})
        d["edit"] |= edit
        d["edit_is_method"] |= edit_is_method
        d["call"] |= call

    for rel in edited_py:
        src = base_files.get(rel, "")
        # (1) enclosing def of every changed old-line = a method the patch edits
        for name, is_method in enclosing_defs(src, touched_old_lines(patch, rel)).items():
            touch(name, edit=True, edit_is_method=is_method)
        atext = "\n".join(added.get(rel, []))
        # (2) a `def name` in the added lines = a method the patch (re)defines
        for m in _ADDED_DEF.finditer(atext):
            touch(m.group(1), edit=True, edit_is_method=True)
        # (3) `x.method(` in the added lines = a method the fix calls / dispatches on
        for m in _CALL.finditer(atext):
            touch(m.group(1), call=True)
    return syms


# --------------------------------------------------------------------------- per-task scan
def _is_dunder(n):
    return n.startswith("__") and n.endswith("__")


def scan_task(t):
    repo, iid, base = t["repo"], t["instance_id"], t["base_commit"]
    d = L.ensure_clone(repo)
    L.checkout(d, base)
    patch = t["patch"]
    edited = [f for f in L.patched_files(patch) if f.endswith(".py")]
    base_files = resolver_files(d, edited)
    index = build_def_index(base_files)

    syms = hinge_symbols(patch, edited, base_files)

    records, builtin_calls = [], []
    for name, flags in syms.items():
        defs = index.get(name, [])
        oc = len(defs)
        files = sorted({r for r, _ in defs})
        classes = sorted({c for _, c in defs if c})
        module_defs = sum(1 for _, c in defs if c is None)
        kind = "edit" if flags["edit"] else "call"
        if oc == 0:
            # no in-repo def: builtin / external receiver-type method (only meaningful if it's a call)
            if flags["call"] and name not in _CALL_NOISE and not _is_dunder(name):
                builtin_calls.append(name)
            continue
        if flags["call"] and not flags["edit"] and name in _CALL_NOISE and oc < STRONG_AMBIG:
            continue   # drop builtin-ish call noise unless it is strongly ambiguous in-repo
        records.append({
            "symbol": name,
            "kind": kind,
            "override_count": oc,
            "n_files": len(files),
            "n_classes": len(classes),
            "module_level_defs": module_defs,
            "edited_here": flags["edit"],
            "edit_is_method": flags["edit_is_method"],
            "is_dunder": _is_dunder(name),
            "sample_defs": [f"{r}::{c or '<module>'}" for r, c in defs][:8],
        })

    # ambiguous hinge symbols = override_count >= 2
    ambig = [r for r in records if r["override_count"] >= MIN_AMBIG]
    score = max((r["override_count"] for r in ambig), default=0)

    # primary symbol: prefer an EDITED override, then higher count, then wider file-span, non-dunder.
    # (file-span, not n_classes: django backends define the SAME class name -- DatabaseOperations,
    # DatabaseWrapper -- in one module per backend, so distinct-class-name count reads 1 while the
    # defs genuinely span 5 files/backends. Span across files is the robust dispatch-ambiguity signal.)
    def pri_key(r):
        return (r["edited_here"] and r["edit_is_method"], r["override_count"],
                max(r["n_files"], r["n_classes"]), not r["is_dunder"])

    primary = max(ambig, key=pri_key) if ambig else None
    fix_edits_override = bool(primary and primary["edited_here"] and primary["edit_is_method"]
                             and primary["override_count"] >= MIN_AMBIG)
    generic_lifecycle = bool(primary and (primary["is_dunder"]
                             or primary["symbol"] in GENERIC_METHODS
                             or primary["override_count"] >= GENERIC_MAX))
    high_condition = bool(primary and primary["override_count"] >= STRONG_AMBIG
                          and max(primary["n_files"], primary["n_classes"]) >= 2)
    # the curated experimental target: strong ambiguity, multi-location, and a DOMAIN-specific method
    # (not a lifecycle/protocol hook) -- the date_extract_sql / _print_X / to_python shape.
    sweet_spot = bool(high_condition and not generic_lifecycle)

    return {
        "instance_id": iid, "repo": repo, "base_commit": base,
        "edited_files": edited,
        "n_source_files_indexed": len(base_files),
        "score": score,
        "primary_symbol": primary["symbol"] if primary else None,
        "primary_override_count": primary["override_count"] if primary else 0,
        "primary_n_files": primary["n_files"] if primary else 0,
        "primary_n_classes": primary["n_classes"] if primary else 0,
        "relation": ("EDITS" if fix_edits_override else ("CALLS" if primary else "-")),
        "fix_edits_override": fix_edits_override,
        "generic_lifecycle": generic_lifecycle,
        "high_condition": high_condition,
        "sweet_spot": sweet_spot,
        "n_ambiguous_symbols": len(ambig),
        "ambiguous_symbols": sorted(ambig, key=lambda r: -r["override_count"])[:8],
        "builtin_receiver_calls": sorted(set(builtin_calls))[:12],
    }


def rank_key(r):
    return (r.get("fix_edits_override", False), r.get("score", 0),
            max(r.get("primary_n_files", 0), r.get("primary_n_classes", 0)))


# --------------------------------------------------------------------------- driver
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400, help="max tasks to stream")
    ap.add_argument("--per-repo", type=int, default=None, help="cap tasks per repo for a spread")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--repos", default=None, help="comma-separated repo allowlist")
    ap.add_argument("--out", default="runs/realbench/dispatch_candidates.json")
    args = ap.parse_args()
    repos = set(args.repos.split(",")) if args.repos else None
    outp = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(outp), exist_ok=True)

    rows, per_repo = [], defaultdict(int)
    for i, t in enumerate(L.load_tasks(n=args.n, repos=repos, offset=args.offset)):
        if args.per_repo and per_repo[t["repo"]] >= args.per_repo:
            continue
        per_repo[t["repo"]] += 1
        try:
            r = scan_task(t)
        except Exception as e:
            r = {"instance_id": t["instance_id"], "repo": t["repo"],
                 "error": f"{type(e).__name__}: {e}"[:200]}
        rows.append(r)
        tag = ("EDIT-OVR" if r.get("fix_edits_override") else
               ("AMBIG" if r.get("score", 0) >= STRONG_AMBIG else
                ("err" if "error" in r else "-")))
        print(f"  [{len(rows):3}] {r['instance_id']:34} score={r.get('score','-'):>3} "
              f"{r.get('relation','-'):5} {tag:8} {r.get('primary_symbol') or ''}", flush=True)
        json.dump({"dataset": L.DATASET, "min_ambig": MIN_AMBIG, "strong_ambig": STRONG_AMBIG,
                   "resolver_file_cap": RESOLVER_FILE_CAP, "scanned": len(rows),
                   "rank_rule": "sort by (fix_edits_override, score=max_override_count, n_classes) desc",
                   "rows": rows}, open(outp, "w"), indent=2)

    ranked = [r for r in rows if r.get("score", 0) >= MIN_AMBIG]
    ranked.sort(key=rank_key, reverse=True)
    edits = [r for r in ranked if r.get("fix_edits_override")]
    strong = [r for r in ranked if r.get("high_condition")]
    sweet = [r for r in ranked if r.get("sweet_spot")]
    print(f"\n=== scanned {len(rows)} | ambiguous(score>=2) {len(ranked)} | "
          f"edit-override {len(edits)} | strong(>=5 & multi-loc) {len(strong)} | "
          f"sweet-spot(strong & domain method) {len(sweet)} ===\n")

    def table(title, items):
        print(title)
        hdr = (f"{'#':>2} {'instance_id':32} {'repo':20} {'method':24} {'ovr':>4} "
               f"{'files':>5} {'cls':>4} {'rel':6} {'gen':4}")
        print(hdr); print("-" * len(hdr))
        for j, r in enumerate(items):
            print(f"{j+1:>2} {r['instance_id']:32} {r['repo']:20} {(r.get('primary_symbol') or ''):24} "
                  f"{r.get('primary_override_count',0):>4} {r.get('primary_n_files',0):>5} "
                  f"{r.get('primary_n_classes',0):>4} {r.get('relation','-'):6} "
                  f"{('gen' if r.get('generic_lifecycle') else ''):4}")
        print()

    # curated set is ordered by the PRIMARY domain method's override count (not the global score,
    # which a generic co-symbol like `fit` can inflate) -- the honest "most dispatch-ambiguous" order.
    sweet.sort(key=lambda r: (r.get("primary_override_count", 0),
                              max(r.get("primary_n_files", 0), r.get("primary_n_classes", 0))),
               reverse=True)
    table("### CURATED SWEET SPOT (domain-specific dispatch, strongest experimental signal):", sweet[:20])
    table("### FULL RANKING top-20 (raw max override count; 'gen' = lifecycle/protocol method):",
          ranked[:20])
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
