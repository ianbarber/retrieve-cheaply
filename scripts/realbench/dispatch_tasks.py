#!/usr/bin/env python3
"""Synthetic DISPATCH-AMBIGUITY tasks on a real language server (pyrefly).

Motivation (docs/real_repo_progress.md "semantic vs textual" / dispatch sections; REPORT.md 3-4):
a method `NAME` is overridden on N>=8 classes, so `grep 'def NAME'` returns N candidates and cannot
say WHICH one binds -- that depends on the receiver's *static type*, which grep cannot compute but a
type-aware go-to-definition (pyrefly LSP) can. Each task plants exactly ONE bug, in the single
override that binds for a statically-typed receiver in `pkg/app.py`. The agent must localize that one
override among N and fix a one-line bug.

`build_tasks(tmp_root)` materializes K=3 self-contained on-disk repos and returns a task dict each.
Run this module directly for GATE 1 (no model): it checks, per task, that the test fails at base,
passes after the gold fix, that grep sees >=8 `def NAME`, and that pyrefly's receiver-aware goto
resolves to the RIGHT (buggy) override file rather than a sibling.

  .venv-streams.system/bin/python scripts/realbench/dispatch_tasks.py
"""
from __future__ import annotations
import os
import re
import sys
import ast
import shutil
import tempfile
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Task source templates. Each package overrides one method `NAME` on 9 classes
# spread across 3 files; app.py constructs a statically-typed receiver of ONE
# class and calls x.NAME(...); exactly that class's override carries the bug.
# (Regular strings, NOT f-strings: the code below contains literal braces.)
# ---------------------------------------------------------------------------

# ===== Task A: codecs, method `serialize` (receiver JsonHandler) =====
A_BASE = '''\
class Handler:
    """Base codec: turn a dict into its serialized string form."""

    name = "base"

    def serialize(self, data: dict) -> str:
        raise NotImplementedError
'''

A_TEXT = '''\
import json

from pkg.base import Handler


class JsonHandler(Handler):
    name = "json"

    def serialize(self, data: dict) -> str:
        return json.dumps(data)


class XmlHandler(Handler):
    name = "xml"

    def serialize(self, data: dict) -> str:
        body = "".join("<%s>%s</%s>" % (k, v, k) for k, v in sorted(data.items()))
        return "<root>%s</root>" % body


class YamlHandler(Handler):
    name = "yaml"

    def serialize(self, data: dict) -> str:
        return "\\n".join("%s: %s" % (k, v) for k, v in sorted(data.items()))
'''

A_BINARY = '''\
import base64
import binascii

from pkg.base import Handler


class Base64Handler(Handler):
    name = "base64"

    def serialize(self, data: dict) -> str:
        raw = "&".join("%s=%s" % (k, v) for k, v in sorted(data.items())).encode()
        return base64.b64encode(raw).decode()


class HexHandler(Handler):
    name = "hex"

    def serialize(self, data: dict) -> str:
        raw = "&".join("%s=%s" % (k, v) for k, v in sorted(data.items())).encode()
        return binascii.hexlify(raw).decode()


class PickleHandler(Handler):
    name = "pickle"

    def serialize(self, data: dict) -> str:
        return "|".join("%s:%r" % (k, v) for k, v in sorted(data.items()))
'''

A_TABULAR = '''\
from pkg.base import Handler


class CsvHandler(Handler):
    name = "csv"

    def serialize(self, data: dict) -> str:
        keys = sorted(data)
        return ",".join(keys) + "\\n" + ",".join(str(data[k]) for k in keys)


class TsvHandler(Handler):
    name = "tsv"

    def serialize(self, data: dict) -> str:
        keys = sorted(data)
        return "\\t".join(keys) + "\\n" + "\\t".join(str(data[k]) for k in keys)


class IniHandler(Handler):
    name = "ini"

    def serialize(self, data: dict) -> str:
        return "\\n".join("%s = %s" % (k, v) for k, v in sorted(data.items()))
'''

A_APP = '''\
from pkg.handlers.text import JsonHandler


def run(x: JsonHandler, data: dict) -> str:
    """Serialize `data` with the given handler and return the string form."""
    return x.serialize(data)
'''

A_TEST = '''\
from pkg.app import run
from pkg.handlers.text import JsonHandler


def test_json_serialize_sorts_keys():
    # canonical JSON emits object keys in sorted order
    assert run(JsonHandler(), {"b": 2, "a": 1}) == '{"a": 1, "b": 2}'


if __name__ == "__main__":
    test_json_serialize_sorts_keys()
    print("OK")
'''

# ===== Task B: field validators, method `validate` (receiver EmailField) =====
B_BASE = '''\
class Field:
    """Base validator: return True iff `value` is well-formed for this field."""

    name = "base"

    def validate(self, value: str) -> bool:
        raise NotImplementedError
'''

B_SCALAR = '''\
from pkg.base import Field


class IntField(Field):
    name = "int"

    def validate(self, value: str) -> bool:
        return value.lstrip("-").isdigit()


class FloatField(Field):
    name = "float"

    def validate(self, value: str) -> bool:
        try:
            float(value)
            return True
        except ValueError:
            return False


class BoolField(Field):
    name = "bool"

    def validate(self, value: str) -> bool:
        return value in ("true", "false")
'''

B_TEXT = '''\
from pkg.base import Field


class StrField(Field):
    name = "str"

    def validate(self, value: str) -> bool:
        return len(value) > 0


class EmailField(Field):
    name = "email"

    def validate(self, value: str) -> bool:
        return "@" in value


class SlugField(Field):
    name = "slug"

    def validate(self, value: str) -> bool:
        return len(value) > 0 and all(c.isalnum() or c == "-" for c in value)
'''

B_NET = '''\
from pkg.base import Field


class UrlField(Field):
    name = "url"

    def validate(self, value: str) -> bool:
        return value.startswith(("http://", "https://"))


class IpField(Field):
    name = "ip"

    def validate(self, value: str) -> bool:
        parts = value.split(".")
        return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


class UuidField(Field):
    name = "uuid"

    def validate(self, value: str) -> bool:
        hexpart = value.replace("-", "").lower()
        return len(hexpart) == 32 and all(c in "0123456789abcdef" for c in hexpart)
'''

B_APP = '''\
from pkg.fields.text import EmailField


def run(x: EmailField, value: str) -> bool:
    """Validate `value` with the given field and return the verdict."""
    return x.validate(value)
'''

B_TEST = '''\
from pkg.app import run
from pkg.fields.text import EmailField


def test_email_requires_domain_dot():
    assert run(EmailField(), "user@example.com") is True
    assert run(EmailField(), "user@localhost") is False


if __name__ == "__main__":
    test_email_requires_domain_dot()
    print("OK")
'''

# ===== Task C: expression nodes, method `to_str` (receiver MulNode) =====
C_BASE = '''\
class Node:
    """Base expression node: render itself to a string."""

    def to_str(self) -> str:
        raise NotImplementedError
'''

C_ATOM = '''\
from pkg.base import Node


class NumNode(Node):
    def __init__(self, value: int) -> None:
        self.value = value

    def to_str(self) -> str:
        return str(self.value)


class VarNode(Node):
    def __init__(self, name: str) -> None:
        self.vname = name

    def to_str(self) -> str:
        return self.vname
'''

C_ARITH = '''\
from pkg.base import Node


class AddNode(Node):
    def __init__(self, left: Node, right: Node) -> None:
        self.left = left
        self.right = right

    def to_str(self) -> str:
        return "(%s + %s)" % (self.left.to_str(), self.right.to_str())


class SubNode(Node):
    def __init__(self, left: Node, right: Node) -> None:
        self.left = left
        self.right = right

    def to_str(self) -> str:
        return "(%s - %s)" % (self.left.to_str(), self.right.to_str())


class MulNode(Node):
    def __init__(self, left: Node, right: Node) -> None:
        self.left = left
        self.right = right

    def to_str(self) -> str:
        return "(%s + %s)" % (self.left.to_str(), self.right.to_str())


class DivNode(Node):
    def __init__(self, left: Node, right: Node) -> None:
        self.left = left
        self.right = right

    def to_str(self) -> str:
        return "(%s / %s)" % (self.left.to_str(), self.right.to_str())
'''

C_MISC = '''\
from pkg.base import Node


class PowNode(Node):
    def __init__(self, base: Node, exp: Node) -> None:
        self.base = base
        self.exp = exp

    def to_str(self) -> str:
        return "(%s ** %s)" % (self.base.to_str(), self.exp.to_str())
'''

C_APP = '''\
from pkg.nodes.arith import MulNode


def run(x: MulNode) -> str:
    """Render the expression node to a string."""
    return x.to_str()
'''

C_TEST = '''\
from pkg.app import run
from pkg.nodes.arith import MulNode
from pkg.nodes.atom import NumNode


def test_mul_renders_product():
    assert run(MulNode(NumNode(6), NumNode(7))) == "(6 * 7)"


if __name__ == "__main__":
    test_mul_renders_product()
    print("OK")
'''


# One spec per task: files (rel -> source), the buggy override to locate, the
# one-line fix, the overriding files (editable), and the override count N.
TASK_SPECS = [
    {
        "name": "codec_serialize",
        "symbol": "serialize",
        "files": {
            "pkg/__init__.py": "",
            "pkg/base.py": A_BASE,
            "pkg/handlers/__init__.py": "",
            "pkg/handlers/text.py": A_TEXT,
            "pkg/handlers/binary.py": A_BINARY,
            "pkg/handlers/tabular.py": A_TABULAR,
            "pkg/app.py": A_APP,
            "test_dispatch.py": A_TEST,
        },
        "editable": ["pkg/handlers/text.py", "pkg/handlers/binary.py", "pkg/handlers/tabular.py"],
        "n_overrides": 9,
        "buggy_rel": "pkg/handlers/text.py",
        "buggy_class": "JsonHandler",
        "buggy_method": "serialize",
        "buggy_needle": "json.dumps(data)",
        "fixed_line": "        return json.dumps(data, sort_keys=True)",
    },
    {
        "name": "field_validate",
        "symbol": "validate",
        "files": {
            "pkg/__init__.py": "",
            "pkg/base.py": B_BASE,
            "pkg/fields/__init__.py": "",
            "pkg/fields/scalar.py": B_SCALAR,
            "pkg/fields/text.py": B_TEXT,
            "pkg/fields/net.py": B_NET,
            "pkg/app.py": B_APP,
            "test_dispatch.py": B_TEST,
        },
        "editable": ["pkg/fields/scalar.py", "pkg/fields/text.py", "pkg/fields/net.py"],
        "n_overrides": 9,
        "buggy_rel": "pkg/fields/text.py",
        "buggy_class": "EmailField",
        "buggy_method": "validate",
        "buggy_needle": 'return "@" in value',
        "fixed_line": '        return "@" in value and "." in value.split("@")[-1]',
    },
    {
        "name": "node_to_str",
        "symbol": "to_str",
        "files": {
            "pkg/__init__.py": "",
            "pkg/base.py": C_BASE,
            "pkg/nodes/__init__.py": "",
            "pkg/nodes/atom.py": C_ATOM,
            "pkg/nodes/arith.py": C_ARITH,
            "pkg/nodes/misc.py": C_MISC,
            "pkg/app.py": C_APP,
            "test_dispatch.py": C_TEST,
        },
        "editable": ["pkg/nodes/atom.py", "pkg/nodes/arith.py", "pkg/nodes/misc.py"],
        "n_overrides": 8,  # 2 (atom) + 4 (arith) + 1 (misc) + 1 (base) = 8 def to_str
        "buggy_rel": "pkg/nodes/arith.py",
        "buggy_class": "MulNode",
        "buggy_method": "to_str",
        "buggy_needle": "+",
        "fixed_line": '        return "(%s * %s)" % (self.left.to_str(), self.right.to_str())',
    },
]


# --------------------------------------------------------------------------- helpers
def _write(repo_dir, rel, content):
    p = os.path.join(repo_dir, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(p) else None
    with open(p, "w") as f:
        f.write(content)


def _git(repo_dir, *args):
    return subprocess.run(["git", "-C", repo_dir, *args], capture_output=True, text=True)


def _find_use_site(app_src, symbol):
    """1-based (line, col) of the method-name token in `x.NAME(` inside app.py."""
    pat = re.compile(r"\bx\." + re.escape(symbol) + r"\b")
    for i, line in enumerate(app_src.splitlines(), 1):
        m = pat.search(line)
        if m:
            col0 = m.start() + 2  # skip the "x." prefix -> first char of the method name
            return i, col0 + 1    # 1-based line, 1-based col
    raise RuntimeError("no x.%s( use-site found in app.py" % symbol)


def _locate_line_in_method(src, cls, method, needle):
    """1-based line number of the first `needle` line inside cls.method (AST-scoped
    so a textually-shared body -- e.g. Add and Mul both '+' -- is unambiguous)."""
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == method:
                    for ln in range(sub.lineno, getattr(sub, "end_lineno", sub.lineno) + 1):
                        if needle in lines[ln - 1]:
                            return ln
    raise RuntimeError("needle %r not found in %s.%s" % (needle, cls, method))


# --------------------------------------------------------------------------- builder
def build_tasks(tmp_root):
    """Materialize K=3 self-contained dispatch repos under tmp_root; return a task
    dict each (name, repo_dir, editable, target_file, symbol, use_site, n_overrides,
    gold, base_commit, test_spec)."""
    os.makedirs(tmp_root, exist_ok=True)
    tasks = []
    for spec in TASK_SPECS:
        repo_dir = os.path.join(tmp_root, spec["name"])
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir)
        os.makedirs(repo_dir)
        for rel, content in spec["files"].items():
            _write(repo_dir, rel, content)

        # commit the base tree so RealRepoEnv(base_commit=...) restores a clean state per run
        _git(repo_dir, "init", "-q")
        _git(repo_dir, "add", "-A")
        _git(repo_dir, "-c", "user.email=streams@local", "-c", "user.name=streams",
             "commit", "-q", "-m", "base")
        base_commit = _git(repo_dir, "rev-parse", "HEAD").stdout.strip()

        app_src = spec["files"]["pkg/app.py"]
        use_line, use_col = _find_use_site(app_src, spec["symbol"])
        gold_line = _locate_line_in_method(spec["files"][spec["buggy_rel"]],
                                           spec["buggy_class"], spec["buggy_method"],
                                           spec["buggy_needle"])
        gold = {"path": spec["buggy_rel"], "start": gold_line, "end": gold_line,
                "new_text": spec["fixed_line"]}

        tasks.append({
            "name": spec["name"],
            "repo_dir": repo_dir,
            "editable": list(spec["editable"]),
            "target_file": "pkg/app.py",
            "symbol": spec["symbol"],
            "use_site": {"file": "pkg/app.py", "line": use_line, "col": use_col},
            "n_overrides": spec["n_overrides"],
            "gold": gold,
            "base_commit": base_commit,
            # run from repo root (test_cwd=".") so `import pkg` resolves; command form.
            "test_spec": '%s -m pytest -q test_dispatch.py' % sys.executable,
            "buggy_rel": spec["buggy_rel"],
        })
    return tasks


def make_env(task, lsp_index_sleep=2.0, lsp_timeout=25.0):
    """RealRepoEnv wired for a dispatch task: file_glob covers the whole pkg (so the
    LSP opens app.py + base + every override), tests run from the repo root."""
    from scaffold.real_env import RealRepoEnv
    return RealRepoEnv(
        task["repo_dir"], editable=task["editable"], test_spec=task["test_spec"],
        base_commit=task["base_commit"], test_kind="command", test_cwd=".",
        file_glob="pkg/**/*.py", lsp_index_sleep=lsp_index_sleep, lsp_timeout=lsp_timeout,
    )


# --------------------------------------------------------------------------- GATE 1
def _gate1():
    tmp_root = os.path.join(tempfile.gettempdir(), "streams_dispatch_gate1")
    tasks = build_tasks(tmp_root)
    print("# GATE 1 (no model): dispatch task validation")
    print("# tmp_root = %s\n" % tmp_root)
    hdr = ("%-16s %-10s %-4s %6s %6s %6s  %-24s %s"
           % ("task", "symbol", "N", "base", "gold", "grep", "lsp_relpath", "== buggy?"))
    print(hdr)
    print("-" * len(hdr))

    all_ok = True
    details = []
    for t in tasks:
        env = make_env(t)
        try:
            # (a) fails at base
            base_fail = not env.run_tests().get("resolved")

            # (c) textual grep for `def NAME` returns >= 8 hits (over the curated file list)
            pat = re.compile(r"\bdef\s+" + re.escape(t["symbol"]) + r"\b")
            grep_hits = 0
            for rel in env.list_files():
                try:
                    src = env.read_file(rel)
                except Exception:
                    continue
                grep_hits += sum(1 for ln in src.splitlines() if pat.search(ln))

            # (d) pyrefly receiver-aware goto -> the RIGHT (buggy) override file
            us = t["use_site"]
            span, relpath = env.lsp_definition(t["symbol"], file=us["file"],
                                               line=us["line"], col=us["col"])
            lsp_relpath = relpath or "(none)"
            lsp_ok = (relpath == t["buggy_rel"])

            # (b) gold fix makes it pass, then revert
            g = t["gold"]
            ok_edit, info = env.apply_line_edit(g["path"], g["start"], g["end"], g["new_text"])
            gold_pass = ok_edit and env.run_tests().get("resolved")
            env.reset()

            row_ok = base_fail and gold_pass and grep_hits >= 8 and lsp_ok
            all_ok = all_ok and row_ok
            print("%-16s %-10s %-4d %6s %6s %6d  %-24s %s"
                  % (t["name"], t["symbol"], t["n_overrides"],
                     "FAIL" if base_fail else "pass?", "PASS" if gold_pass else "no",
                     grep_hits, lsp_relpath, "YES" if lsp_ok else "NO  <-- CRUX"))
            details.append((t, span, relpath, lsp_ok))
        finally:
            env.close()

    print("\n# use-sites and pyrefly spans:")
    for t, span, relpath, lsp_ok in details:
        us = t["use_site"]
        head = (span or "").splitlines()[0:2]
        print("  [%s] x.%s at %s:%d:%d -> %s%s"
              % (t["name"], t["symbol"], us["file"], us["line"], us["col"],
                 relpath, "" if lsp_ok else "  (WRONG file!)"))
        for h in head:
            print("        | %s" % h)

    print("\nGATE 1: %s" % ("ALL PASS" if all_ok else "FAILURES PRESENT"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(_gate1())
