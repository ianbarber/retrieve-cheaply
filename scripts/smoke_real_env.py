#!/usr/bin/env python3
"""CPU-only smoke test for scaffold/real_env.py (RealRepoEnv + SymbolResolver)
and the backward-compatible stream_agent.py <defn> extension.

NO ML MODEL is loaded (CUDA disabled below). Proves the 5 checks from the build
plan against a shallow h11 @ v0.14.0 clone in the scratchpad:
  1. RealRepoEnv checks out / reads files / lists relevant files.
  2. run_tests() = PASS on the unmodified repo, FAIL when a file is corrupted.
  3. goto_definition AND lsp_definition both resolve ConnectionState -> _state.py.
  4. SymbolResolver resolves Connection.send -> the method body.
  5. The extended DEFN_RE: backward-compat + new file/line/col fields.

Run:
  pkill -9 -f "[p]yrefly"
  CUDA_VISIBLE_DEVICES="" .venv-streams/bin/python scripts/smoke_real_env.py
"""
import os
import sys

os.environ["CUDA_VISIBLE_DEVICES"] = ""   # belt-and-braces: no GPU
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SCRATCH = ("/tmp/claude-1000/-home-ianbarber-Projects-Streams/"
           "4c20856c-b6b1-4797-847f-d0c62bde21b4/scratchpad")
REPO = os.path.join(SCRATCH, "h11")
BASE_COMMIT = "467c5cfc5f9a1364c7da6b754d591092ee409931"

from scaffold.real_env import RealRepoEnv, SymbolResolver
from scaffold.stream_agent import DEFN_RE

PASS = "PASS"
FAIL = "FAIL"
results = []


def check(name, ok, detail=""):
    tag = PASS if ok else FAIL
    results.append(ok)
    print(f"[{tag}] {name}" + (f"  -- {detail}" if detail else ""), flush=True)


# AST-test file (RefactorBench-style: reads ../h11/_state.py relative to test_cwd)
AST_TEST = os.path.join(SCRATCH, "smoke_ast_test.py")
with open(AST_TEST, "w") as f:
    f.write(
        "import ast, os, unittest\n"
        "class T(unittest.TestCase):\n"
        "    def test_connectionstate(self):\n"
        "        p = '../h11/_state.py'\n"
        "        self.assertTrue(os.path.exists(p))\n"
        "        tree = ast.parse(open(p).read())\n"
        "        cls = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name=='ConnectionState']\n"
        "        self.assertTrue(cls, 'ConnectionState class missing')\n"
        "        meths = [s.name for s in cls[0].body if isinstance(s,(ast.FunctionDef,ast.AsyncFunctionDef))]\n"
        "        self.assertIn('process_event', meths)\n"
        "if __name__=='__main__':\n"
        "    unittest.main()\n"
    )


def main():
    if not os.path.isdir(os.path.join(REPO, ".git")):
        print(f"FATAL: h11 clone not found at {REPO}", file=sys.stderr)
        return 1

    env = RealRepoEnv(
        repo_dir=REPO,
        editable=["h11/_state.py", "h11/_connection.py"],
        test_spec=AST_TEST,            # AST-test file (auto-detected)
        base_commit=BASE_COMMIT,
        file_glob="h11/*.py",
        test_cwd="rb_run",
    )

    print("=" * 72)
    print("CHECK 1 — construct / checkout / read / list")
    print("=" * 72)
    files = env.list_files()
    check("1a list_files() returns the curated h11 package subset (not whole tree)",
          all(p.startswith("h11/") for p in files) and "h11/_state.py" in files
          and 8 <= len(files) <= 20,
          f"{len(files)} files, e.g. {files[:4]}")
    src = env.read_file("h11/_state.py")
    check("1b read_file('h11/_state.py') returns real source",
          "class ConnectionState" in src, f"{len(src)} chars")

    print()
    print("=" * 72)
    print("CHECK 5 — DEFN_RE backward-compat + new use-site fields")
    print("=" * 72)
    m1 = DEFN_RE.search('<defn sym="Account"/>')
    bc = bool(m1) and m1.group("sym") == "Account" and m1.group("file") is None \
        and m1.group("line") is None and m1.group("col") is None
    check('5a bare <defn sym="Account"/> still matches, sym=="Account", no file/line/col',
          bc, f'groups={m1.groupdict() if m1 else None}')
    m2 = DEFN_RE.search('<defn sym="A.b" file="x.py" line="3" col="5"/>')
    nf = bool(m2) and m2.group("sym") == "A.b" and m2.group("file") == "x.py" \
        and m2.group("line") == "3" and m2.group("col") == "5"
    check('5b <defn sym="A.b" file="x.py" line="3" col="5"/> captures all fields',
          nf, f'groups={m2.groupdict() if m2 else None}')

    print()
    print("=" * 72)
    print("CHECK 4 — SymbolResolver: Class.method -> method body")
    print("=" * 72)
    sr = SymbolResolver(env._files_dict())
    span, rel = sr.resolve("Connection.send")
    ok4 = span is not None and rel == "h11/_connection.py" and span.lstrip().startswith("def send(")
    check("4a SymbolResolver('Connection.send') -> _connection.py def send(...)",
          ok4, f"{rel} | {span.splitlines()[0] if span else None}")
    span_q, rel_q = sr.resolve("_state.ConnectionState.process_event")
    ok4b = span_q is not None and rel_q == "h11/_state.py" and "def process_event" in span_q.splitlines()[0]
    check("4b SymbolResolver('_state.ConnectionState.process_event') -> _state.py (module-qualified)",
          ok4b, f"{rel_q} | {span_q.splitlines()[0] if span_q else None}")
    bare_span, bare_rel = sr.resolve("send")
    check("4c bare method name 'send' (no class) -> (None, None) [forces disambiguation]",
          bare_span is None and bare_rel is None, f"({bare_span}, {bare_rel})")

    print()
    print("=" * 72)
    print("CHECK 3 — cross-file resolution of ConnectionState")
    print("=" * 72)
    g_span, g_rel = env.goto_definition("ConnectionState")
    ok3a = g_span is not None and g_rel == "h11/_state.py" and "class ConnectionState" in g_span.splitlines()[0]
    check("3a goto_definition('ConnectionState') -> h11/_state.py (AST)",
          ok3a, f"{g_rel} | {g_span.splitlines()[0] if g_span else None}")
    print("    [spawning a live pyrefly LSP daemon — sequential, killed after]")
    l_span, l_rel = env.lsp_definition("ConnectionState")
    ok3b = l_span is not None and l_rel == "h11/_state.py" and "class ConnectionState" in l_span
    check("3b lsp_definition('ConnectionState') -> h11/_state.py (live pyrefly LSP)",
          ok3b, f"{l_rel} | {(l_span.splitlines()[0] if l_span else None)}")

    print()
    print("=" * 72)
    print("CHECK 2 — run_tests PASS on clean repo, FAIL when corrupted")
    print("=" * 72)
    tr_pass = env.run_tests()
    check("2a run_tests() == PASS on the unmodified repo", bool(tr_pass.get("resolved")),
          f"resolved={tr_pass.get('resolved')}, failure={tr_pass.get('failure')!r}")
    ok_edit, info = env.apply_edit("h11/_state.py", "class ConnectionState:", "class ConnectionStateXYZ:")
    tr_fail = env.run_tests()
    check("2b run_tests() == FAIL after corrupting _state.py", not tr_fail.get("resolved"),
          f"edit_ok={ok_edit}, resolved={tr_fail.get('resolved')}, failure={tr_fail.get('failure')!r}")
    env.reset()   # restore the working tree for the next task
    restored = "class ConnectionState:" in env.read_file("h11/_state.py")
    check("2c reset() restores the corrupted file (git checkout -f)", restored)

    print()
    print("    metrics() after the corrupting edit + reset:")
    print("   ", env.metrics())
    env.close()

    print()
    n_ok = sum(results)
    print("=" * 72)
    print(f"SUMMARY: {n_ok}/{len(results)} sub-checks passed")
    print("=" * 72)
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
