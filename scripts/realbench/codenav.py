#!/usr/bin/env python3
"""codenav: minimal language-server-style navigation, for the LSP ablation.

Runs INSIDE the SWE-bench container against /testbed (the checked-out repo). Pure stdlib,
compatible with the older pythons some task images ship. This is the "LSP tool" whose
presence we ablate: it returns just the relevant span/references instead of a whole-file read.

  codenav defn SYMBOL   go-to-definition: the definition span (file:line + source)
  codenav refs SYMBOL   find-references: up to N reference sites across the repo

Resolves bare `name`, `Class`, and `Class.method`. Test files are excluded as definition
sources (a symbol should resolve to real source, not a test). Candidate files are found with
grep first, so it stays cheap even on large repos (django/sympy). No AST end_lineno reliance
(works pre-3.8): the span is extracted by indentation, like an editor's definition peek.
"""
import io
import os
import re
import sys
import subprocess

# Task images ship heterogeneous pythons; some (e.g. django-11138 -> py3.6) default stdout to
# ASCII, which crashes when a definition span contains non-ASCII (e.g. U+2026). Force UTF-8.
for _name in ("stdout", "stderr"):
    _s = getattr(sys, _name, None)
    try:
        setattr(sys, _name, io.TextIOWrapper(_s.buffer, encoding="utf-8", errors="replace", line_buffering=True))
    except Exception:
        pass

ROOT = os.environ.get("CODENAV_ROOT", "/testbed")
MAX_SPAN = 160        # cap a definition span so a huge class body cannot blow the budget
MAX_REFS = 40


def _is_test(rel):
    b = os.path.basename(rel)
    return ("/tests/" in "/" + rel or "/test/" in "/" + rel
            or b.startswith("test_") or b.endswith("_test.py") or b == "conftest.py")


def _grep(pattern):
    cmd = ["grep", "-rInE", "--include=*.py", pattern, ROOT]
    try:
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             universal_newlines=True, timeout=40).stdout
    except Exception:
        return []
    return out.splitlines()


def _rel(p):
    try:
        return os.path.relpath(p, ROOT)
    except Exception:
        return p


def _extract_span(path, start_ln):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return ""
    i = start_ln - 1
    if i < 0 or i >= len(lines):
        return ""
    base_indent = len(lines[i]) - len(lines[i].lstrip())
    out = [lines[i]]
    j = i + 1
    while j < len(lines) and len(out) < MAX_SPAN:
        s = lines[j]
        if s.strip():
            ind = len(s) - len(s.lstrip())
            # stop at the next sibling/parent def/class/decorator (end of this definition)
            if ind < base_indent or (ind == base_indent and s.lstrip().startswith(("def ", "class ", "@", "async def "))):
                break
        out.append(s)
        j += 1
    return "".join(out).rstrip("\n")


def _candidates(name):
    pat = r"^[[:space:]]*(async def|def|class)[[:space:]]+%s\b" % re.escape(name)
    cands = []
    for h in _grep(pat):
        parts = h.split(":", 2)
        if len(parts) != 3:
            continue
        path, ln, text = parts
        rel = _rel(path)
        if _is_test(rel):
            continue
        try:
            cands.append((rel, int(ln), text, path))
        except ValueError:
            continue
    # non-test source, shallower paths first (favours canonical definitions)
    cands.sort(key=lambda c: (c[0].count("/"), len(c[0])))
    return cands


def defn(symbol):
    name = symbol.split(".")[-1]
    cands = _candidates(name)
    if not cands:
        sys.stderr.write("codenav: no definition found for '%s' under %s\n" % (symbol, ROOT))
        return 2
    rel, ln, _text, path = cands[0]
    span = _extract_span(path, ln)
    sys.stdout.write("# %s:%d  (definition of '%s')  [codenav defn]\n%s\n" % (rel, ln, name, span))
    if len(cands) > 1:
        others = ", ".join("%s:%d" % (r, l) for r, l, _, _ in cands[1:6])
        sys.stdout.write("\n# %d other definition(s): %s\n" % (len(cands) - 1, others))
    return 0


def refs(symbol):
    name = symbol.split(".")[-1]
    defpat = re.compile(r"^\s*(async def|def|class)\s+%s\b" % re.escape(name))
    shown = 0
    for h in _grep(r"\b%s\b" % re.escape(name)):
        parts = h.split(":", 2)
        if len(parts) != 3:
            continue
        path, ln, text = parts
        if defpat.match(text):
            continue
        sys.stdout.write("%s:%s: %s\n" % (_rel(path), ln, text.strip()[:160]))
        shown += 1
        if shown >= MAX_REFS:
            sys.stdout.write("# ... (truncated at %d references)\n" % MAX_REFS)
            break
    if shown == 0:
        sys.stderr.write("codenav: no references found for '%s'\n" % symbol)
        return 2
    return 0


def main(argv):
    if argv[:1] == ["--selfcheck"]:
        sys.stdout.write("codenav ok (root=%s)\n" % ROOT)
        return 0
    if len(argv) < 2 or argv[0] not in ("defn", "refs"):
        sys.stderr.write("usage: codenav {defn|refs} SYMBOL\n")
        return 64
    return defn(argv[1]) if argv[0] == "defn" else refs(argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
