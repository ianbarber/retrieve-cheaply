#!/usr/bin/env python3
"""Real-repository environment for the StreamAgent (RefactorBench edition).

`RealRepoEnv` mirrors `scaffold/mock_env.py::MultiFileEnv` EXACTLY (same method
names, signatures, return shapes, and rework accounting) but is backed by a
CHECKED-OUT real git repository on disk instead of an in-memory files-dict. This
lets the same `StreamAgent` drive large vendored repos (microsoft/RefactorBench)
with their static-AST tests, with no agent changes.

`SymbolResolver` adds QUALIFIED-symbol go-to-definition (`module.Class.method`,
`Class.method`, `module.Class`, `Class`, bare `function`) on top of the
top-level-name resolution the synthetic suite needed. A bare *method* name with
no class qualifier returns `(None, None)` on purpose (forces the model to
disambiguate), per the real-repo plan.

Operational gotchas honoured (the project has been burned by these):
  * pyrefly LSP daemons can deadlock under concurrency -> we spawn ONE at a time,
    terminate only the process owned by the client, and run strictly sequentially;
    every read has a timeout so a hang fails instead of blocking forever.
  * a standalone `pyrefly.toml` wants TOP-LEVEL keys (`project-includes=[...]`),
    NOT a `[tool.pyrefly]` table -> we (re)write the correct form when untracked.
  * RefactorBench AST tests use CWD-relative paths like `../src/...`, so we run
    them with CWD = a SUBDIRECTORY of the repo root (`test_cwd`, default rb_run).

The LSP client is reused verbatim from scripts/validate_pyrefly_lsp.py
(`LspClient`, `path_to_uri`, `uri_to_path`, `find_use_site`).
"""
from __future__ import annotations
import os
import ast
import json
import glob
import time
import shutil
import subprocess
import sys

from scaffold.tooling import pyrefly_or_name

PYREFLY = pyrefly_or_name()

# ----------------------------------------------------------------------------
# SymbolResolver — qualified-symbol AST go-to-definition
# ----------------------------------------------------------------------------
class SymbolResolver:
    """AST-resolve a (possibly qualified) symbol to its definition span + path.

    Parses every file ONCE at construction. Resolution forms:
      * bare `function`        -> top-level def/class/assignment (like MultiFileEnv).
      * `Class`                -> top-level ClassDef named Class.
      * `Class.method`         -> the method def inside ClassDef Class.
      * `module.Class`         -> top-level ClassDef Class in a file matching module.
      * `module.Class.method`  -> the method, in a file matching module.
      * bare `method` (no dot) -> (None, None)  [force disambiguation].

    `files` is a dict {relpath: source}. `resolve(sym)` -> (span_text, relpath)
    or (None, None). Spans are node.lineno..end_lineno (decorators excluded),
    identical to MultiFileEnv.goto_definition.
    """

    def __init__(self, files: dict):
        self.files = dict(files)
        self._trees = {}   # rel -> (tree, lines)
        for rel in sorted(self.files):
            try:
                src = self.files[rel]
                self._trees[rel] = (ast.parse(src), src.splitlines())
            except Exception:
                continue

    # --- helpers -----------------------------------------------------------
    @staticmethod
    def _mod_match(module_parts, rel):
        """True if `module_parts` (e.g. ['h11','_state']) is a suffix of the
        file's dotted module path, or module_parts is empty (no module hint)."""
        if not module_parts:
            return True
        mod = rel[:-3] if rel.endswith(".py") else rel
        comps = mod.replace(os.sep, "/").replace("/", ".").split(".")
        comps = [c for c in comps if c and c != "__init__"]
        n = len(module_parts)
        return comps[-n:] == list(module_parts)

    def _span(self, rel, node):
        _, lines = self._trees[rel]
        end = getattr(node, "end_lineno", node.lineno)
        return "\n".join(lines[node.lineno - 1:end]), rel

    # --- resolution forms --------------------------------------------------
    def _top_level(self, name):
        for rel in sorted(self._trees):
            tree, _ = self._trees[rel]
            for node in tree.body:
                hit = None
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == name:
                        hit = node
                elif isinstance(node, ast.Assign):
                    tgts = [t.id for t in node.targets if isinstance(t, ast.Name)]
                    if name in tgts:
                        hit = node
                elif isinstance(node, ast.AnnAssign):
                    if isinstance(node.target, ast.Name) and node.target.id == name:
                        hit = node
                if hit is not None:
                    return self._span(rel, hit)
        return None, None

    def _find_class(self, module_parts, cls):
        for rel in sorted(self._trees):
            if not self._mod_match(module_parts, rel):
                continue
            tree, _ = self._trees[rel]
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name == cls:
                    return self._span(rel, node)
        return None, None

    def _find_method(self, module_parts, cls, meth):
        for rel in sorted(self._trees):
            if not self._mod_match(module_parts, rel):
                continue
            tree, _ = self._trees[rel]
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name == cls:
                    for sub in node.body:
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == meth:
                            return self._span(rel, sub)
        return None, None

    def resolve(self, symbol):
        if not symbol:
            return None, None
        parts = symbol.split(".")
        if len(parts) == 1:
            # bare name: top-level only -> a bare METHOD name resolves to nothing.
            return self._top_level(parts[0])
        # qualified: prefer the Class.method interpretation, then module.Class.
        cls, meth = parts[-2], parts[-1]
        span, rel = self._find_method(parts[:-2], cls, meth)
        if span is not None:
            return span, rel
        span, rel = self._find_class(parts[:-1], parts[-1])
        if span is not None:
            return span, rel
        return None, None


# ----------------------------------------------------------------------------
# RealRepoEnv — checked-out-repo backend mirroring MultiFileEnv
# ----------------------------------------------------------------------------
class RealRepoEnv:
    """A MultiFileEnv-shaped environment backed by a real repo directory.

    Constructor args:
      repo_dir       : abs path to the checked-out repo (its root).
      editable       : list of repo-relative paths the agent may edit.
      test_spec      : EITHER a shell command string OR a path to a python
                       AST-test file (RefactorBench style). See `test_kind`.
      base_commit    : if given, `git checkout -f <commit>` at construction
                       (and on reset()).
      file_list      : explicit list of repo-relative files for list_files().
      file_glob      : OR a glob (relative to repo_dir, e.g. "h11/*.py" or
                       "src/flask/**/*.py") naming the relevant package subset.
                       (If neither given, list_files() == editable.)
      test_cwd       : repo-relative subdir to run AST tests from (default
                       "rb_run"); the test's `../src/...` paths resolve against
                       THIS dir's parent (= repo root). Created if missing.
      test_kind      : "auto" (default) | "command" | "ast_file".
      pyrefly_subtree: repo-relative path to `pyrefly check` (default: the dir
                       of the first editable file, else the package root).
      test_timeout   : seconds for run_tests (default 60).
      lsp_index_sleep, lsp_timeout : pyrefly-LSP daemon indexing wait / per-RPC
                       timeout (generous; never hang).
      write_pyrefly_config : (re)write a correct standalone pyrefly.toml when the
                       repo's is missing/wrong-form and untracked (default True).
      force_diag     : if set, pyrefly_diagnostics returns it verbatim (plumbing).
    """

    def __init__(self, repo_dir, editable, test_spec, base_commit=None,
                 file_list=None, file_glob=None, test_cwd="rb_run",
                 test_kind="auto", pyrefly_subtree=None, test_timeout=60,
                 lsp_index_sleep=2.0, lsp_timeout=25.0,
                 write_pyrefly_config=True, force_diag=None):
        self.repo_dir = os.path.abspath(repo_dir)
        self.editable = list(editable or [])
        self.test_spec = test_spec
        self.base_commit = base_commit
        self.file_list = list(file_list) if file_list else None
        self.file_glob = file_glob
        self.test_cwd = test_cwd
        self.pyrefly_subtree = pyrefly_subtree
        self.test_timeout = test_timeout
        self.lsp_index_sleep = lsp_index_sleep
        self.lsp_timeout = lsp_timeout
        self.force_diag = force_diag
        self.lsp_latencies = []
        self.lsp_errors = []
        self._py = sys.executable
        self._lsp_module = None

        # test kind
        is_file = isinstance(test_spec, str) and os.path.isfile(test_spec) and test_spec.endswith(".py")
        if test_kind == "command":
            self._test_is_command = True
        elif test_kind == "ast_file":
            self._test_is_command = False
        else:  # auto
            self._test_is_command = not is_file

        if base_commit:
            subprocess.run(["git", "-C", self.repo_dir, "checkout", "-f", base_commit],
                           capture_output=True, text=True)

        if write_pyrefly_config:
            self._ensure_pyrefly_config()

        self._reset_accounting()

    # --- accounting (identical to MultiFileEnv) ----------------------------
    def _reset_accounting(self):
        self.chars_written = 0
        self.chars_deleted_after_first = 0
        self.first_write_done = False
        self.n_edits = 0
        self.edit_regions = {}

    def reset(self):
        """Restore the working tree to base_commit (or discard tracked changes)
        and zero the rework accounting, for the next task on the same repo."""
        if self.base_commit:
            subprocess.run(["git", "-C", self.repo_dir, "checkout", "-f", self.base_commit],
                           capture_output=True, text=True)
        else:
            subprocess.run(["git", "-C", self.repo_dir, "checkout", "-f", "--", "."],
                           capture_output=True, text=True)
        self._reset_accounting()

    # --- paths / files -----------------------------------------------------
    def _abspath(self, rel):
        p = os.path.normpath(os.path.join(self.repo_dir, rel))
        if not (p == self.repo_dir or p.startswith(self.repo_dir + os.sep)):
            raise ValueError(f"path escapes repo: {rel}")
        return p

    def read_file(self, path=None):
        rel = path or (self.editable[0] if self.editable else None)
        if rel is None:
            raise ValueError("no path given and no editable default")
        with open(self._abspath(rel)) as f:
            return f.read()

    def list_files(self):
        """Curated/relevant file list (NEVER the whole repo tree)."""
        if self.file_list is not None:
            return sorted(self.file_list)
        if self.file_glob:
            base = len(self.repo_dir) + 1
            hits = glob.glob(os.path.join(self.repo_dir, self.file_glob), recursive=True)
            rels = sorted(p[base:] for p in hits if os.path.isfile(p))
            # always include editable files even if outside the glob
            for e in self.editable:
                if e not in rels:
                    rels.append(e)
            return sorted(rels)
        return sorted(self.editable)

    def _files_dict(self):
        out = {}
        for rel in self.list_files():
            try:
                out[rel] = self.read_file(rel)
            except Exception:
                continue
        return out

    # --- edits (rework accounting identical to MockEnv/MultiFileEnv) -------
    def apply_edit(self, path, search, replace):
        path = path or (self.editable[0] if self.editable else None)
        try:
            cur = self.read_file(path)
        except FileNotFoundError:
            return False, f"no such file: {path}"
        if search not in cur:
            return False, "search not found"
        self.chars_written += len(replace)
        if self.first_write_done:
            self.chars_deleted_after_first += len(search)
        self.first_write_done = True
        self.n_edits += 1
        with open(self._abspath(path), "w") as f:
            f.write(cur.replace(search, replace, 1))
        return True, "ok"

    def apply_line_edit(self, path, start, end, new_text):
        path = path or (self.editable[0] if self.editable else None)
        try:
            cur = self.read_file(path)
        except FileNotFoundError:
            return False, f"no such file: {path}"
        lines = cur.splitlines(keepends=True)
        n = len(lines)
        if not (1 <= start <= end <= n):
            return False, f"line range {start}-{end} out of bounds ({path} has {n} lines)"
        removed = "".join(lines[start - 1:end])
        nt = new_text if new_text.endswith("\n") else new_text + "\n"
        new = "".join(lines[:start - 1]) + nt + "".join(lines[end:])
        self.chars_written += len(nt)
        if self.first_write_done:
            self.chars_deleted_after_first += len(removed)
        self.first_write_done = True
        self.n_edits += 1
        with open(self._abspath(path), "w") as f:
            f.write(new)
        return True, "ok"

    # --- go-to-definition (AST) -------------------------------------------
    def goto_definition(self, symbol):
        """REAL AST go-to-definition over the relevant files. Handles bare
        top-level names (identical to MultiFileEnv) AND qualified symbols
        (module.Class.method, Class.method, ...) via SymbolResolver. Returns
        (span, relpath) or (None, None)."""
        return SymbolResolver(self._files_dict()).resolve(symbol)

    # --- find-references (word-scan; see caveat in final report) ----------
    def find_references(self, symbol):
        """Find files that USE `symbol` (whole-word, last dotted component),
        excluding its definition site. Word-scan over the curated file list (an
        LSP-references result would be more precise; word-scan is robust and
        never spawns a daemon). Returns sorted ["relpath:line", ...]."""
        import re as _re
        last = symbol.split(".")[-1]
        pat = _re.compile(r"\b" + _re.escape(last) + r"\b")
        _, defpath = self.goto_definition(symbol)
        hits = []
        for rel in self.list_files():
            if rel == defpath:
                continue
            try:
                src = self.read_file(rel)
            except Exception:
                continue
            for i, line in enumerate(src.splitlines(), 1):
                if pat.search(line):
                    hits.append(f"{rel}:{i}")
                    break
        return sorted(hits)

    # --- live pyrefly LSP go-to-definition --------------------------------
    def _lsp_mod(self):
        if self._lsp_module is None:
            import importlib.util
            mod = sys.modules.get("validate_pyrefly_lsp")
            if mod is None:
                here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                path = os.path.join(here, "scripts", "validate_pyrefly_lsp.py")
                spec = importlib.util.spec_from_file_location("validate_pyrefly_lsp", path)
                mod = importlib.util.module_from_spec(spec)
                sys.modules["validate_pyrefly_lsp"] = mod
                spec.loader.exec_module(mod)
            self._lsp_module = mod
        return self._lsp_module

    def _lsp_query(self, use_rel, use_line0, use_col0):
        """Spawn ONE pyrefly LSP daemon over the repo, didOpen the relevant
        files, query textDocument/definition at the use-site, return
        (rel, start_line0, end_line0, span) or (None,None,None,None). Never hangs."""
        mod = self._lsp_mod()
        LspClient = mod.LspClient
        path_to_uri = mod.path_to_uri
        uri_to_path = mod.uri_to_path
        files = self._files_dict()
        client = LspClient(self.repo_dir)
        try:
            client.request("initialize", {
                "processId": os.getpid(),
                "rootUri": path_to_uri(self.repo_dir),
                "capabilities": {"textDocument": {
                    "definition": {"linkSupport": True},
                    "synchronization": {"didOpen": True},
                }},
                "workspaceFolders": [{"uri": path_to_uri(self.repo_dir), "name": "repo"}],
            }, timeout=self.lsp_timeout)
            client.notify("initialized", {})
            for rel, content in files.items():
                client.notify("textDocument/didOpen", {"textDocument": {
                    "uri": path_to_uri(self._abspath(rel)),
                    "languageId": "python", "version": 1, "text": content,
                }})
            time.sleep(self.lsp_index_sleep)
            result = client.request("textDocument/definition", {
                "textDocument": {"uri": path_to_uri(self._abspath(use_rel))},
                "position": {"line": int(use_line0), "character": int(use_col0)},
            }, timeout=self.lsp_timeout)
        finally:
            client.close()
        if not result:
            return None, None, None, None
        loc = result[0] if isinstance(result, list) else result
        if "targetUri" in loc:
            uri = loc["targetUri"]
            rng = loc.get("targetSelectionRange") or loc["targetRange"]
        else:
            uri = loc["uri"]
            rng = loc["range"]
        tgt = uri_to_path(uri)
        rel = os.path.relpath(tgt, self.repo_dir)
        ls0 = rng["start"]["line"]
        ls1 = rng["end"]["line"]
        try:
            with open(tgt) as f:
                srclines = f.read().splitlines()
            span = "\n".join(srclines[ls0:ls1 + 1])
        except Exception:
            span = ""
        return rel, ls0, ls1, span

    def lsp_definition(self, symbol, file=None, line=None, col=None):
        """Live pyrefly-LSP go-to-definition, same (span, relpath) shape as
        goto_definition. If a use-site (file + line[/col]) is given, query the
        definition THERE (1-based line/col from the model -> 0-based for LSP);
        otherwise auto-find a use-site of the symbol's last component. The
        LSP-resolved location is expanded to the enclosing TOP-LEVEL node's full
        source span (same as MultiFileEnv.lsp_definition). Returns (None,None) on
        any error (never hangs)."""
        started = time.perf_counter()
        try:
            if file is not None and (line is not None or col is not None):
                use_rel = file
                use_line0 = max(0, int(line) - 1) if line is not None else 0
                use_col0 = max(0, int(col) - 1) if col is not None else 0
            else:
                last = symbol.split(".")[-1]
                _, defpath = self.goto_definition(symbol)
                use = self._lsp_mod().find_use_site(self._files_dict(), last, defpath)
                if use is None:
                    return None, None
                use_rel, use_line0, use_col0 = use
            rel, ls0, ls1, span = self._lsp_query(use_rel, use_line0, use_col0)
            if rel is None:
                return None, None
            # expand the def LOCATION to the enclosing top-level node's full body
            line1 = int(ls0 or 0) + 1
            try:
                src = self.read_file(rel)
                tree = ast.parse(src)
                lines = src.splitlines()
                for node in tree.body:
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef,
                                         ast.AsyncFunctionDef, ast.Assign, ast.AnnAssign)):
                        end = getattr(node, "end_lineno", node.lineno)
                        if node.lineno <= line1 <= end:
                            return "\n".join(lines[node.lineno - 1:end]), rel
            except Exception:
                pass
            return (span or None), rel
        except Exception as exc:
            self.lsp_errors.append(f"{type(exc).__name__}: {exc}")
            return None, None
        finally:
            self.lsp_latencies.append(time.perf_counter() - started)

    # --- pyrefly diagnostics ----------------------------------------------
    def _pyrefly_subtree_abs(self):
        sub = self.pyrefly_subtree
        if sub is None:
            sub = os.path.dirname(self.editable[0]) if self.editable else "."
        return self._abspath(sub) if sub not in ("", ".") else self.repo_dir

    def _ensure_pyrefly_config(self):
        cfg = os.path.join(self.repo_dir, "pyrefly.toml")
        want = 'project-includes = ["**/*.py"]\n'
        try:
            tracked = subprocess.run(
                ["git", "-C", self.repo_dir, "ls-files", "--error-unmatch", "pyrefly.toml"],
                capture_output=True, text=True).returncode == 0
        except Exception:
            tracked = False
        if tracked:
            return  # don't pollute a tracked config / git diff
        if os.path.exists(cfg):
            try:
                cur = open(cfg).read()
            except Exception:
                cur = ""
            if "[tool.pyrefly]" not in cur and "project-includes" in cur:
                return  # already a valid standalone config
        try:
            with open(cfg, "w") as f:
                f.write(want)
        except Exception:
            pass

    def pyrefly_diagnostics(self, path=None):
        """`pyrefly check` over the relevant subtree; same formatted lines as
        MultiFileEnv: `[error] {basename} L{n} {code}: {msg}` (cap 10)."""
        if self.force_diag is not None:
            return self.force_diag
        target = self._pyrefly_subtree_abs()
        try:
            r = subprocess.run([PYREFLY, "check", "--output-format", "json", target],
                               cwd=self.repo_dir, capture_output=True, text=True, timeout=self.test_timeout)
            data = json.loads(r.stdout or "{}")
        except Exception:
            return ""
        diags = data.get("errors", []) if isinstance(data, dict) else []
        # if a path is given, surface its errors first (still cap 10 overall)
        if path:
            base = os.path.basename(path)
            diags = sorted(diags, key=lambda d: os.path.basename(d.get("path", "") or "") != base)
        out = []
        for d in diags[:10]:
            line = d.get("line", "?")
            fp = os.path.basename(d.get("path", "") or "")
            code = d.get("name", "diag")
            msg = (d.get("concise_description") or d.get("description") or "")[:160]
            out.append(f"[error] {fp} L{line} {code}: {msg}")
            if isinstance(line, int):
                self.edit_regions[line] = self.edit_regions.get(line, 0) + 1
        return "\n".join(out)

    # --- tests -------------------------------------------------------------
    def run_tests(self):
        """Run the task's test. AST-test files (RefactorBench) are copied into a
        repo subdir (`test_cwd`) and run with CWD = that subdir so their
        `../src/...` relative paths resolve. A command string is run with the
        same CWD via the shell. resolved = (exit code 0). MultiFileEnv-shaped."""
        cwd = os.path.join(self.repo_dir, self.test_cwd)
        os.makedirs(cwd, exist_ok=True)
        try:
            if self._test_is_command:
                r = subprocess.run(self.test_spec, shell=True, cwd=cwd,
                                   capture_output=True, text=True, timeout=self.test_timeout)
            else:
                dst = os.path.join(cwd, "_rb_test.py")
                shutil.copyfile(self.test_spec, dst)
                r = subprocess.run([self._py, dst], cwd=cwd,
                                   capture_output=True, text=True, timeout=self.test_timeout)
        except subprocess.TimeoutExpired:
            return {"resolved": False, "f2p_pass": 0, "f2p_total": 1,
                    "p2p_pass": 0, "p2p_total": 0, "failure": "timeout"}
        ok = (r.returncode == 0)
        if ok:
            fail = ""
        else:
            err = (r.stderr or "").strip()
            out = (r.stdout or "").strip()
            tail = err.splitlines() or out.splitlines()
            fail = tail[-1] if tail else "test failed"
        return {"resolved": ok, "f2p_pass": int(ok), "f2p_total": 1,
                "p2p_pass": 0, "p2p_total": 0, "failure": fail[:300]}

    # --- metrics / patch / close ------------------------------------------
    def metrics(self):
        rr = self.chars_deleted_after_first / max(self.chars_written, 1)
        cycles = sum(v - 1 for v in self.edit_regions.values() if v > 1)
        return {"rework_ratio": round(rr, 3), "n_edits": self.n_edits,
                "edit_error_cycles": cycles, "chars_written": self.chars_written,
                "chars_deleted_after_first": self.chars_deleted_after_first}

    def current_patch(self):
        """`git -C repo_dir diff` (tracked-file changes). Returns "" if the repo
        is not a git checkout (e.g. RefactorBench vendored trees ship no .git)."""
        try:
            r = subprocess.run(["git", "-C", self.repo_dir, "diff"],
                               capture_output=True, text=True, timeout=30)
            return r.stdout
        except Exception:
            return ""

    def close(self):
        """No-op: the environment does not own the repository; each LSP client closes itself."""


if __name__ == "__main__":
    # Minimal self-check (no GPU, no model). The full proof is scripts/smoke_real_env.py.
    import re as _re
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scaffold.stream_agent import DEFN_RE
    m1 = DEFN_RE.search('<defn sym="Account"/>')
    assert m1 and m1.group("sym") == "Account" and not m1.group("file"), "backward-compat broke"
    m2 = DEFN_RE.search('<defn sym="A.b" file="x.py" line="3" col="5"/>')
    assert m2 and m2.group("sym") == "A.b" and m2.group("file") == "x.py" \
        and m2.group("line") == "3" and m2.group("col") == "5", "use-site capture broke"
    print("DEFN_RE OK (backward-compat + use-site).")
