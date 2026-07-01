#!/usr/bin/env python3
"""Selection scanner for the real-repo experiment (docs/real_repo_plan.md), criteria S1-S3.

For each SWE-bench Verified task it checks out the repo at base_commit and, from the GOLD patch, asks
whether the fix depends on a symbol defined in ANOTHER file (so `<defn>` would have something to fetch
that a whole-file read would pay for). It emits a ranked candidate pool with per-criterion evidence, so
the final ~15 are hand-audited from an auditable shortlist rather than hand-waved.

  S1 cross-file dependency : the fix uses a symbol whose definition resolves to a different in-repo file.
  S2 non-trivial symbol    : that symbol is a method / class / imported type (not a bare local helper).
  S3 expensive counterfactual : the definition's file is large (>= MIN_DEFN_LINES), so reading it whole
                                 is genuinely more expensive than a definition span.

S4 (test discriminates) and S5 (env tractable) need the task environment and are checked later, only for
tasks that pass S1-S3. No dependency install here; checkout + AST only.

  python scripts/realbench/select.py --n 60 [--repos psf/requests,pallets/flask] --out runs/realbench/candidates.json
"""
import os
import re
import sys
import ast
import json
import argparse
import warnings

warnings.filterwarnings("ignore")   # source files with `\*` in docstrings raise SyntaxWarning on parse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from scaffold.real_env import SymbolResolver
from scripts.realbench import swe_loader as L

MIN_DEFN_LINES = 300      # S3: a "large" file whose whole-file read the cheap action would replace
RESOLVER_FILE_CAP = 1600  # bound the AST resolver's file set on huge repos (django/sympy)


def _top_package(rel):
    return rel.split("/")[0] if "/" in rel else ""


def is_test_file(rel):
    """A test file, which should not count as a cross-file definition source."""
    base = rel.split("/")[-1]
    return ("/tests/" in "/" + rel or "/test/" in "/" + rel
            or base.startswith("test_") or base.endswith("_test.py") or base == "conftest.py")


def resolver_files(repo_dir, edited_files):
    """Repo-relative .py source dict scoped to the top packages of the edited files (bounded),
    excluding test files so a symbol never resolves to a test rather than real source."""
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


def local_names(src):
    """Top-level def/class names + imported names defined/bound in a file (to exclude from 'cross-file')."""
    names = set()
    try:
        tree = ast.parse(src)
    except Exception:
        return names
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
    return names


def candidate_symbols(added_lines):
    """Heuristic symbols the fix references: in-repo imports, call targets, attribute methods, CapWords."""
    text = "\n".join(added_lines)
    cands = {}   # name -> hint kind
    for m in re.finditer(r"^\s*from\s+([.\w]+)\s+import\s+(.+)$", text, flags=re.M):
        mod = m.group(1)
        for nm in re.split(r"[,\s]+", m.group(2).replace("(", " ").replace(")", " ")):
            nm = nm.strip().split(" as ")[0]
            if nm and nm != "*" and re.match(r"^[A-Za-z_]\w*$", nm):
                cands[nm] = "import"
    for m in re.finditer(r"\.([a-z_]\w+)\s*\(", text):          # attribute method calls
        cands.setdefault(m.group(1), "method")
    for m in re.finditer(r"\b([A-Z]\w+)\b", text):               # CapWords types/classes
        cands.setdefault(m.group(1), "type")
    for m in re.finditer(r"(?<![.\w])([a-z_]\w+)\s*\(", text):   # bare function calls
        cands.setdefault(m.group(1), "call")
    # drop python builtins / obvious noise
    import builtins
    for b in dir(builtins):
        cands.pop(b, None)
    for noise in ("self", "cls", "super", "len", "isinstance", "str", "int", "list", "dict",
                  "set", "tuple", "return", "print", "range", "enumerate", "getattr", "setattr"):
        cands.pop(noise, None)
    return cands


def scan_task(t):
    """Return an evidence dict for one task (S1-S3 with the cross-file symbols found)."""
    repo, iid, base = t["repo"], t["instance_id"], t["base_commit"]
    d = L.ensure_clone(repo)
    L.checkout(d, base)
    patch = t["patch"]
    edited = [f for f in L.patched_files(patch) if f.endswith(".py")]
    added = L.added_lines_by_file(patch)
    files = resolver_files(d, edited)
    res = SymbolResolver(files)

    def nlines(rel):
        return len(files.get(rel, "").splitlines()) if rel in files else None

    xdeps = []       # cross-file symbols the fix depends on
    for a in edited:
        a_src = files.get(a, "")
        a_local = local_names(a_src)
        cands = candidate_symbols(added.get(a, []))
        for name, kind in cands.items():
            if name in a_local:
                continue
            span, defrel = res.resolve(name)
            if span and defrel and defrel != a:
                xdeps.append({"symbol": name, "hint_kind": kind, "edited_file": a,
                              "edited_lines": nlines(a), "def_file": defrel,
                              "def_lines": nlines(defrel)})

    # de-dup by (symbol, def_file)
    seen, uniq = set(), []
    for x in xdeps:
        k = (x["symbol"], x["def_file"])
        if k not in seen:
            seen.add(k); uniq.append(x)

    s1 = len(uniq) > 0
    strong_kinds = {"import", "type", "method"}
    s2 = any(x["hint_kind"] in strong_kinds for x in uniq)
    s3 = any((x["def_lines"] or 0) >= MIN_DEFN_LINES for x in uniq)
    # score: cross-file symbols weighted, bonus for large defn files and non-trivial kinds
    score = 0
    for x in uniq:
        score += 2 if x["hint_kind"] in strong_kinds else 1
        if (x["def_lines"] or 0) >= MIN_DEFN_LINES:
            score += 2
    # S6 tractability: a small edit site (primary file) and a small gold patch, so the agent can
    # localize and fix in one/few shots and the measured token gap is retrieval, not wading through
    # a 1600-line file. (S3's large file is the cross-file DEFINITION B, not the edit site A.)
    primary = edited[0] if edited else None
    primary_lines = nlines(primary) if primary else None
    patch_added = sum(len(added.get(a, [])) for a in edited)
    tractable = (primary_lines is not None and primary_lines <= 900 and patch_added <= 40)
    f2p = json.loads(t["FAIL_TO_PASS"]); p2p = json.loads(t["PASS_TO_PASS"])
    return {"instance_id": iid, "repo": repo, "base_commit": base,
            "edited_files": edited, "primary_file": primary, "primary_file_lines": primary_lines,
            "gold_added_lines": patch_added, "n_f2p": len(f2p), "n_p2p": len(p2p),
            "S1_cross_file": s1, "S2_nontrivial": s2, "S3_expensive_read": s3, "S6_tractable": tractable,
            "admissible": s1 and s2 and s3, "audit_ready": s1 and s2 and s3 and tractable, "score": score,
            "xdeps": sorted(uniq, key=lambda x: -(x["def_lines"] or 0))[:8]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--repos", default=None, help="comma-separated repo allowlist")
    ap.add_argument("--out", default="runs/realbench/candidates.json")
    args = ap.parse_args()
    repos = set(args.repos.split(",")) if args.repos else None
    os.makedirs(os.path.dirname(os.path.join(ROOT, args.out)), exist_ok=True)

    rows = []
    for i, t in enumerate(L.load_tasks(n=args.n, repos=repos, offset=args.offset)):
        try:
            r = scan_task(t)
        except Exception as e:
            r = {"instance_id": t["instance_id"], "repo": t["repo"], "error": f"{type(e).__name__}: {e}"[:200]}
        rows.append(r)
        tag = "ADMISSIBLE" if r.get("admissible") else ("err" if "error" in r else "-")
        print(f"  [{i+1:3}] {r['instance_id']:34} score={r.get('score','-'):>3} {tag} "
              f"S1={r.get('S1_cross_file')} S2={r.get('S2_nontrivial')} S3={r.get('S3_expensive_read')}",
              flush=True)
        outp = os.path.join(ROOT, args.out)
        json.dump({"dataset": L.DATASET, "min_defn_lines": MIN_DEFN_LINES,
                   "scanned": len(rows), "rows": rows}, open(outp, "w"), indent=2)
    adm = [r for r in rows if r.get("admissible")]
    adm.sort(key=lambda r: -r["score"])
    print(f"\n=== {len(adm)}/{len(rows)} admissible (S1&S2&S3) ===")
    for r in adm[:20]:
        top = r["xdeps"][0] if r["xdeps"] else {}
        print(f"  score={r['score']:>3} {r['instance_id']:34} "
              f"{top.get('symbol','')}({top.get('hint_kind','')}) in {top.get('def_file','')} "
              f"[{top.get('def_lines')}L]")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
