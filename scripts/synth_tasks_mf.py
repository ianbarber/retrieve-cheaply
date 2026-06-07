#!/usr/bin/env python3
"""Multi-file task suite: the bug is in a TARGET file; the type definitions it
misuses live in OTHER workspace files the model is NOT shown. Unlike the
single-file suite, the checker's knowledge here is NON-REDUNDANT with the model's
context — the discriminating setting for "does the diagnostic channel add value".

Informativeness gradient (pre-registered prediction):
  group "plain" — the diagnostic TEXT itself carries the remote fact
                  (missing-argument names the param; bad-unpacking shows the tuple
                  shape) -> plain delivery (C/D) should beat A here if the channel
                  has value at all.
  group "rich"  — the diagnostic names the problem but only the remote DEFINITION
                  names the fix (renamed field/method/key) -> rich delivery
                  (definitions appended) should add value over plain delivery.
  group "control" — no type signal at all (truthiness logic bug) -> all arms equal.

Each task: files (dict path->content), target, test (runs in a fresh subprocess
with the workspace on sys.path; THE SPEC, shown to the model), gold_target (a
corrected target file; verifier proves solvability), group, sites.
"""

TASKS_MF = [
    # ---------------- group "plain" ----------------
    dict(
        name="mf_signature_drift", group="plain", sites=3, target="report.py",
        files={
            "textutil.py": '''\
def fmt_row(label: str, value: float, unit: str) -> str:
    return f"{label}: {value:.2f}{unit}"
''',
            "report.py": '''\
from textutil import fmt_row

def render(data: dict) -> list[str]:
    rows = []
    for k, v in data.items():
        rows.append(fmt_row(k, v))
    rows.append(fmt_row("subtotal", sum(data.values())))
    rows.append(fmt_row("items", float(len(data))))
    return rows
''',
        },
        test='''\
from report import render
assert render({"a": 1.0, "b": 2.5}) == ["a: 1.00", "b: 2.50", "subtotal: 3.50", "items: 2.00"]
''',
        gold_target='''\
from textutil import fmt_row

def render(data: dict) -> list[str]:
    rows = []
    for k, v in data.items():
        rows.append(fmt_row(k, v, ""))
    rows.append(fmt_row("subtotal", sum(data.values()), ""))
    rows.append(fmt_row("items", float(len(data)), ""))
    return rows
''',
    ),
    dict(
        name="mf_arity_drift", group="plain", sites=2, target="summary.py",
        files={
            "feed.py": '''\
def read_records() -> list[tuple[str, int, float]]:
    # (name, qty, unit_price) — price was added to the schema
    return [("apple", 3, 0.5), ("apple", 2, 0.5), ("pear", 1, 1.0)]
''',
            "summary.py": '''\
from feed import read_records

def totals() -> dict:
    out = {}
    for name, qty in read_records():
        out[name] = out.get(name, 0) + qty
    return out

def grand_total() -> float:
    s = 0.0
    for name, qty in read_records():
        s += qty
    return s
''',
        },
        test='''\
from summary import totals, grand_total
assert totals() == {"apple": 5, "pear": 1}
assert grand_total() == 6.0
''',
        gold_target='''\
from feed import read_records

def totals() -> dict:
    out = {}
    for name, qty, price in read_records():
        out[name] = out.get(name, 0) + qty
    return out

def grand_total() -> float:
    s = 0.0
    for name, qty, price in read_records():
        s += qty
    return s
''',
    ),
    dict(
        name="mf_ctor_param", group="plain", sites=2, target="builder.py",
        files={
            "models.py": '''\
from dataclasses import dataclass

@dataclass
class Vec:
    x: int
    y: int
    z: int
''',
            "builder.py": '''\
from dataclasses import astuple
from models import Vec

def make_points(pairs: list) -> list:
    out = []
    for a, b in pairs:
        out.append(Vec(a, b))
    out.append(Vec(0, 0))
    return [astuple(v) for v in out]
''',
        },
        test='''\
from builder import make_points
assert make_points([(1, 2), (3, 4)]) == [(1, 2, 0), (3, 4, 0), (0, 0, 0)]
''',
        gold_target='''\
from dataclasses import astuple
from models import Vec

def make_points(pairs: list) -> list:
    out = []
    for a, b in pairs:
        out.append(Vec(a, b, 0))
    out.append(Vec(0, 0, 0))
    return [astuple(v) for v in out]
''',
    ),
    dict(
        name="mf_optional_return", group="plain", sites=2, target="billing.py",
        files={
            "store.py": '''\
CATALOG = [{"sku": "A", "price": 2.0}, {"sku": "B", "price": 5.0}]

def find(sku: str):
    for item in CATALOG:
        if item["sku"] == sku:
            return item
    return None
''',
            "billing.py": '''\
from store import find

def line_price(sku: str, qty: int) -> float:
    item = find(sku)
    return item["price"] * qty

def invoice_total(order: list) -> float:
    # unknown skus are skipped
    total = 0.0
    for sku, qty in order:
        item = find(sku)
        total += item["price"] * qty
    return total
''',
        },
        test='''\
from billing import invoice_total, line_price
assert invoice_total([("A", 3), ("B", 1)]) == 11.0
assert invoice_total([("A", 2), ("ZZ", 9)]) == 4.0
assert line_price("B", 2) == 10.0
''',
        gold_target='''\
from store import find

def line_price(sku: str, qty: int) -> float:
    item = find(sku)
    if item is None:
        return 0.0
    return item["price"] * qty

def invoice_total(order: list) -> float:
    # unknown skus are skipped
    total = 0.0
    for sku, qty in order:
        item = find(sku)
        if item is None:
            continue
        total += item["price"] * qty
    return total
''',
    ),
    dict(
        name="mf_key_type", group="plain", sites=1, target="lookup.py",
        files={
            "index.py": '''\
PAIRS = [(1, "a"), (2, "b"), (3, "c")]

def build_index() -> dict[int, str]:
    return {k: v for k, v in PAIRS}
''',
            "lookup.py": '''\
from index import build_index

def lookup_all(keys: list) -> list:
    idx = build_index()
    return [idx[str(k)] for k in keys]
''',
        },
        test='''\
from lookup import lookup_all
assert lookup_all([2, 1]) == ["b", "a"]
''',
        gold_target='''\
from index import build_index

def lookup_all(keys: list) -> list:
    idx = build_index()
    return [idx[k] for k in keys]
''',
    ),
    # ---------------- group "rich" ----------------
    dict(
        name="mf_field_rename", group="rich", sites=3, target="grid.py",
        files={
            "models.py": '''\
from dataclasses import dataclass

@dataclass
class Cell:
    row: int
    x: int   # renamed from `col` during a refactor
''',
            "grid.py": '''\
from models import Cell

def corners(cells: list[Cell]):
    rows = [c.row for c in cells]
    cols = [c.col for c in cells]
    return (min(rows), min(cols), max(rows), max(cols))

def width(cells: list[Cell]) -> int:
    return max(c.col for c in cells) - min(c.col for c in cells) + 1

def bounding_area(cells: list[Cell]) -> int:
    top, left, bot, right = corners(cells)
    return (bot - top + 1) * (right - left + 1)
''',
        },
        test='''\
from models import Cell
from grid import bounding_area, width
cs = [Cell(0, 0), Cell(2, 3), Cell(1, 1)]
assert bounding_area(cs) == 3 * 4
assert width(cs) == 4
''',
        gold_target='''\
from models import Cell

def corners(cells: list[Cell]):
    rows = [c.row for c in cells]
    cols = [c.x for c in cells]
    return (min(rows), min(cols), max(rows), max(cols))

def width(cells: list[Cell]) -> int:
    return max(c.x for c in cells) - min(c.x for c in cells) + 1

def bounding_area(cells: list[Cell]) -> int:
    top, left, bot, right = corners(cells)
    return (bot - top + 1) * (right - left + 1)
''',
    ),
    dict(
        name="mf_method_rename", group="rich", sites=2, target="teller.py",
        files={
            "bank.py": '''\
class Account:
    def __init__(self, balance: int):
        self.balance = balance

    def deposit(self, amt: int) -> None:   # was `credit`
        self.balance += amt

    def withdraw(self, amt: int) -> None:  # was `debit`
        self.balance -= amt
''',
            "teller.py": '''\
from bank import Account

def process(acct: Account, txns: list) -> int:
    for t in txns:
        if t >= 0:
            acct.credit(t)
        else:
            acct.debit(-t)
    return acct.balance
''',
        },
        test='''\
from bank import Account
from teller import process
assert process(Account(100), [50, -30, 10]) == 130
''',
        gold_target='''\
from bank import Account

def process(acct: Account, txns: list) -> int:
    for t in txns:
        if t >= 0:
            acct.deposit(t)
        else:
            acct.withdraw(-t)
    return acct.balance
''',
    ),
    dict(
        name="mf_typeddict_key", group="rich", sites=2, target="digest.py",
        files={
            "schema.py": '''\
from typing import TypedDict

class Stats(TypedDict):
    total: int    # renamed from `sum`
    count: int

def analyze(xs: list) -> Stats:
    return {"total": sum(xs), "count": len(xs)}
''',
            "digest.py": '''\
from schema import analyze

def mean_of(xs: list) -> float:
    r = analyze(xs)
    return r["sum"] / r["count"]

def describe(xs: list) -> str:
    r = analyze(xs)
    return f"{r['sum']} over {r['count']}"
''',
        },
        test='''\
from digest import mean_of, describe
assert mean_of([2, 4, 6]) == 4.0
assert describe([2, 4, 6]) == "12 over 3"
''',
        gold_target='''\
from schema import analyze

def mean_of(xs: list) -> float:
    r = analyze(xs)
    return r["total"] / r["count"]

def describe(xs: list) -> str:
    r = analyze(xs)
    return f"{r['total']} over {r['count']}"
''',
    ),
    dict(
        name="mf_obj_not_dict", group="rich", sites=2, target="monitor.py",
        files={
            "client.py": '''\
from dataclasses import dataclass

@dataclass
class Response:
    status: int
    body: str

def fetch(path: str) -> Response:
    # now returns a Response object (was a dict)
    table = {"/health": (200, "ok"), "/jobs": (503, "busy")}
    code, body = table.get(path, (404, "missing"))
    return Response(code, body)
''',
            "monitor.py": '''\
from client import fetch

def healthy(path: str) -> bool:
    resp = fetch(path)
    return resp["status"] == 200

def report(paths: list) -> list:
    out = []
    for p in paths:
        resp = fetch(p)
        out.append((p, resp["status"]))
    return out
''',
        },
        test='''\
from monitor import healthy, report
assert healthy("/health") is True
assert healthy("/jobs") is False
assert report(["/health", "/nope"]) == [("/health", 200), ("/nope", 404)]
''',
        gold_target='''\
from client import fetch

def healthy(path: str) -> bool:
    resp = fetch(path)
    return resp.status == 200

def report(paths: list) -> list:
    out = []
    for p in paths:
        resp = fetch(p)
        out.append((p, resp.status))
    return out
''',
    ),
    # ---------------- group "control" ----------------
    dict(
        name="mf_control_truthiness", group="control", sites=1, target="limits.py",
        files={
            "defaults.py": '''\
FALLBACK = 99
''',
            "limits.py": '''\
from defaults import FALLBACK

def effective_limits(cfg: dict, keys: list) -> dict:
    out = {}
    for k in keys:
        v = cfg.get(k)
        out[k] = v if v else FALLBACK
    return out
''',
        },
        test='''\
from limits import effective_limits
# a configured 0 is meaningful and must be preserved; only ABSENT keys fall back
assert effective_limits({"a": 5, "b": 0}, ["a", "b", "c"]) == {"a": 5, "b": 0, "c": 99}
''',
        gold_target='''\
from defaults import FALLBACK

def effective_limits(cfg: dict, keys: list) -> dict:
    out = {}
    for k in keys:
        v = cfg.get(k)
        out[k] = v if v is not None else FALLBACK
    return out
''',
    ),
]

if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from scaffold.mock_env import MultiFileEnv

    print(f"{'task':24} {'grp':7} {'buggy':7} {'gold':6} {'pyflerr':7} diag mentions remote file?")
    ok_all = True
    for t in TASKS_MF:
        env = MultiFileEnv(t["files"], t["target"], t["test"])
        buggy = env.run_tests()["resolved"]
        diag = env.pyrefly_diagnostics()
        nerr = diag.count("[error]")
        remotes = [f for f in t["files"] if f != t["target"]]
        mentions = any(os.path.basename(rf) in diag for rf in remotes) or any(
            w in diag for w in ("Missing argument", "Cannot unpack", "no attribute",
                                 "not subscriptable", "TypedDict", "Stats", "Response"))
        # gold fix must pass
        env2 = MultiFileEnv({**t["files"], t["target"]: t["gold_target"]}, t["target"], t["test"])
        gold = env2.run_tests()["resolved"]
        flag = "" if (not buggy and gold and (nerr > 0 or t["group"] == "control")) else "  <-- PROBLEM"
        if flag: ok_all = False
        print(f"{t['name']:24} {t['group']:7} {'FAIL' if not buggy else 'PASS!':7} "
              f"{'PASS' if gold else 'FAIL!':6} {nerr:<7} {mentions}{flag}")
        for ln in diag.splitlines()[:2]:
            print(f"    {ln[:150]}")
        env.close(); env2.close()
    print("\nALL OK" if ok_all else "\nPROBLEMS FOUND")
