#!/usr/bin/env python3
"""Multi-file task suite v2 — rebuilt for power after two adversarial reviews.

DESIGN BAR (every task must clear it; enforced by the verifier at bottom):
  R1. Multi-file, NON-REDUNDANT: the type fact the fix needs lives in a HIDDEN remote
      file (not the shown target). So the checker can carry INFORMATION, not just
      localization (the single-file suite's fatal flaw).
  R2. test <=> diagnostics <=> correct: the behavioural test FULLY CONSTRAINS every
      edited site (every buggy path is exercised), and the GOLD fix is BOTH test-green
      AND pyrefly-clean. => "test green" and "no diagnostics" cannot disagree, which is
      what produced the v1 reversers (mf_optional_return: pass green with errors live;
      mf_typeddict_key: false all-clear on a type-valid wrong key).
  R3. NO TRANSCRIPTION: the diagnostic must not contain the literal replacement value
      (no "Missing argument `unit`" -> add unit=""). The verifier flags any task whose
      diagnostic text contains a gold fix token.
  R4. NO SPEC IN COMMENTS: intent lives only in the test's assertion VALUES, never prose.
  R5. REALISTIC: ordinary refactor/schema-drift bugs, not examiner reverse-engineering of
      a diagnostic (no `idx[str(k)]`, no `add_tags(tags=None,*more)` strawmen).

GROUPS (the informativeness gradient):
  rich    — the diagnostic NAMES THE PROBLEM but only the remote DEFINITION names the FIX
            (renamed symbol, changed signature/type/protocol/enum/generic). The genuine
            "does the type signal carry value" tasks. This is the headline category.
  plain   — the diagnostic TEXT conveys the remote fact needed (e.g. a tuple's arity),
            but applying it still needs reasoning, not transcription.
  control — multi-file, remote type USED CORRECTLY, multi-site, but the bug is a LOGIC
            error the type checker cannot see. Tests whether the channel is just an
            edit-error/anti-thrashing aid (benefit here would undercut a type-signal claim).

Each task: name, group, bug_class, sites, target, files{path:src}, test, gold_target,
fix_tokens (literal tokens of the fix — for the transcription check),
wrong_typevalid (optional: a type-VALID but behaviourally-WRONG target the test must
still reject — guards against false-all-clear).
"""

TASKS_MF2 = [

    # ============================== RICH ==============================
    dict(name="rich_field_rename", group="rich", bug_class="renamed dataclass field, 3 sites", sites=3,
         target="grid.py", fix_tokens=[".x"],
         files={"geom.py": '''\
from dataclasses import dataclass

@dataclass
class Cell:
    row: int
    x: int      # was `col`; renamed in a coordinate-system refactor
''',
                "grid.py": '''\
from geom import Cell

def bounds(cells: list[Cell]):
    rows = [c.row for c in cells]
    cols = [c.col for c in cells]
    return min(rows), min(cols), max(rows), max(cols)

def width(cells: list[Cell]) -> int:
    xs = [c.col for c in cells]
    return max(xs) - min(xs) + 1

def height(cells: list[Cell]) -> int:
    rs = [c.row for c in cells]
    return max(rs) - min(rs) + 1
'''},
         test='''\
from geom import Cell
from grid import bounds, width, height
cs = [Cell(0, 0), Cell(2, 3), Cell(1, 1)]
assert bounds(cs) == (0, 0, 2, 3)
assert width(cs) == 4
assert height(cs) == 3
''',
         gold_target='''\
from geom import Cell

def bounds(cells: list[Cell]):
    rows = [c.row for c in cells]
    cols = [c.x for c in cells]
    return min(rows), min(cols), max(rows), max(cols)

def width(cells: list[Cell]) -> int:
    xs = [c.x for c in cells]
    return max(xs) - min(xs) + 1

def height(cells: list[Cell]) -> int:
    rs = [c.row for c in cells]
    return max(rs) - min(rs) + 1
'''),

    dict(name="rich_method_rename", group="rich", bug_class="renamed methods, 2 sites", sites=2,
         target="teller.py", fix_tokens=["deposit", "withdraw"],
         files={"bank.py": '''\
class Account:
    def __init__(self, balance: int):
        self.balance = balance

    def deposit(self, amt: int) -> None:    # was `credit`
        self.balance += amt

    def withdraw(self, amt: int) -> None:   # was `debit`
        self.balance -= amt
''',
                "teller.py": '''\
from bank import Account

def process(acct: Account, txns: list[int]) -> int:
    for t in txns:
        if t >= 0:
            acct.credit(t)
        else:
            acct.debit(-t)
    return acct.balance
'''},
         test='''\
from bank import Account
from teller import process
assert process(Account(100), [50, -30, 10]) == 130
assert process(Account(0), [-5]) == -5
''',
         gold_target='''\
from bank import Account

def process(acct: Account, txns: list[int]) -> int:
    for t in txns:
        if t >= 0:
            acct.deposit(t)
        else:
            acct.withdraw(-t)
    return acct.balance
'''),

    dict(name="rich_generic_widened", group="rich", bug_class="value type widened int->list[int] (multimap)", sites=2,
         target="report.py", fix_tokens=["sum(", "for v in", "extend"],
         files={"store.py": '''\
def scores() -> dict[str, list[int]]:
    # values became LISTS when the schema allowed multiple entries per name
    return {"ann": [3, 1], "bo": [5], "cy": [2, 2]}
''',
                "report.py": '''\
from store import scores

def total_for(name: str) -> int:
    return scores()[name] + 0

def grand_total() -> int:
    s = 0
    for name in scores():
        s += scores()[name]
    return s
'''},
         test='''\
from report import total_for, grand_total
assert total_for("ann") == 4
assert total_for("bo") == 5
assert grand_total() == 4 + 5 + 4
''',
         gold_target='''\
from store import scores

def total_for(name: str) -> int:
    return sum(scores()[name])

def grand_total() -> int:
    s = 0
    for name in scores():
        s += sum(scores()[name])
    return s
'''),

    dict(name="rich_enum_member", group="rich", bug_class="enum member renamed; old name used", sites=2,
         target="router.py", fix_tokens=["ACTIVE", "PAUSED"],
         files={"states.py": '''\
from enum import Enum

class Status(Enum):
    ACTIVE = 1      # was OPEN
    PAUSED = 2      # was HOLD
    CLOSED = 3
''',
                "router.py": '''\
from states import Status

def can_accept(s: Status) -> bool:
    return s == Status.OPEN

def is_waiting(s: Status) -> bool:
    return s == Status.HOLD
'''},
         test='''\
from states import Status
from router import can_accept, is_waiting
assert can_accept(Status.ACTIVE) is True
assert can_accept(Status.CLOSED) is False
assert is_waiting(Status.PAUSED) is True
assert is_waiting(Status.ACTIVE) is False
''',
         gold_target='''\
from states import Status

def can_accept(s: Status) -> bool:
    return s == Status.ACTIVE

def is_waiting(s: Status) -> bool:
    return s == Status.PAUSED
'''),

    dict(name="rich_callback_sig", group="rich", bug_class="callback signature changed 1->2 args", sites=1,
         target="pipeline.py", fix_tokens=["acc + x * x"],
         files={"engine.py": '''\
from typing import Callable

def fold(items: list[int], step: Callable[[int, int], int], start: int) -> int:
    # step is now (accumulator, item) -> int  (was a 1-arg transform)
    acc = start
    for it in items:
        acc = step(acc, it)
    return acc
''',
                "pipeline.py": '''\
from engine import fold

def sum_squares(xs: list[int]) -> int:
    return fold(xs, lambda x: x * x, 0)
'''},
         test='''\
from pipeline import sum_squares
assert sum_squares([1, 2, 3]) == 14
assert sum_squares([]) == 0
''',
         gold_target='''\
from engine import fold

def sum_squares(xs: list[int]) -> int:
    return fold(xs, lambda acc, x: acc + x * x, 0)
'''),

    dict(name="rich_return_obj_vs_tuple", group="rich", bug_class="return shape tuple->object, fields remote", sites=2,
         target="monitor.py", fix_tokens=[".code", ".body"],
         files={"client.py": '''\
from dataclasses import dataclass

@dataclass
class Reply:
    code: int
    body: str

def call(path: str) -> Reply:
    # now returns a Reply object (previously a (code, body) tuple)
    table = {"/up": (200, "ok"), "/down": (503, "busy")}
    c, b = table.get(path, (404, "missing"))
    return Reply(c, b)
''',
                "monitor.py": '''\
from client import call

def ok(path: str) -> bool:
    code, body = call(path)
    return code == 200

def describe(path: str) -> str:
    code, body = call(path)
    return f"{code}:{body}"
'''},
         test='''\
from monitor import ok, describe
assert ok("/up") is True
assert ok("/down") is False
assert describe("/up") == "200:ok"
assert describe("/missing") == "404:missing"
''',
         gold_target='''\
from client import call

def ok(path: str) -> bool:
    r = call(path)
    return r.code == 200

def describe(path: str) -> str:
    r = call(path)
    return f"{r.code}:{r.body}"
'''),

    dict(name="rich_field_type_change", group="rich", bug_class="remote field type int->str, arithmetic breaks", sites=2,
         target="billing.py", fix_tokens=["int(", "float("],
         files={"models.py": '''\
from dataclasses import dataclass

@dataclass
class Line:
    sku: str
    qty: str        # came from a CSV import; now a string, was an int
    price: int
''',
                "billing.py": '''\
from models import Line

def subtotal(line: Line) -> int:
    return line.qty * line.price

def total(lines: list[Line]) -> int:
    return sum(line.qty * line.price for line in lines)
'''},
         test='''\
from models import Line
from billing import subtotal, total
ls = [Line("a", "2", 5), Line("b", "3", 10)]
assert subtotal(ls[0]) == 10
assert total(ls) == 40
''',
         gold_target='''\
from models import Line

def subtotal(line: Line) -> int:
    return int(line.qty) * line.price

def total(lines: list[Line]) -> int:
    return sum(int(line.qty) * line.price for line in lines)
'''),

    dict(name="optional_return", group="plain", bug_class="remote helper now returns Optional, 2 sites", sites=2,
         target="pricing.py", fix_tokens=["is None"],
         files={"catalog.py": '''\
from dataclasses import dataclass

@dataclass
class Item:
    sku: str
    price: float

CATALOG = [Item("A", 2.0), Item("B", 5.0)]

def find(sku: str):
    for item in CATALOG:
        if item.sku == sku:
            return item
    return None      # now returns None for unknown skus (used to raise)
''',
                "pricing.py": '''\
from catalog import find

def unit_price(sku: str) -> float:
    return find(sku).price

def order_total(order: list) -> float:
    total = 0.0
    for sku, qty in order:
        total += find(sku).price * qty
    return total
'''},
         # test constrains BOTH sites incl. the unknown-sku path (fixes v1 under-constraint)
         test='''\
from pricing import unit_price, order_total
assert unit_price("A") == 2.0
assert unit_price("ZZ") == 0.0
assert order_total([("A", 3), ("B", 1)]) == 11.0
assert order_total([("A", 2), ("ZZ", 9)]) == 4.0
''',
         gold_target='''\
from catalog import find

def unit_price(sku: str) -> float:
    item = find(sku)
    if item is None:
        return 0.0
    return item.price

def order_total(order: list) -> float:
    total = 0.0
    for sku, qty in order:
        item = find(sku)
        if item is None:
            continue
        total += item.price * qty
    return total
'''),

    dict(name="rich_arity_drift", group="rich", bug_class="remote record schema gained a field, 2 unpack sites", sites=2,
         target="summary.py", fix_tokens=["price", "_"],
         files={"feed.py": '''\
def rows() -> list[tuple[str, int, float]]:
    # schema gained a trailing `price`; was (name, qty)
    return [("apple", 3, 0.5), ("apple", 2, 0.5), ("pear", 1, 1.0)]
''',
                "summary.py": '''\
from feed import rows

def counts() -> dict:
    out: dict = {}
    for name, qty in rows():
        out[name] = out.get(name, 0) + qty
    return out

def units() -> int:
    n = 0
    for name, qty in rows():
        n += qty
    return n
'''},
         test='''\
from summary import counts, units
assert counts() == {"apple": 5, "pear": 1}
assert units() == 6
''',
         gold_target='''\
from feed import rows

def counts() -> dict:
    out: dict = {}
    for name, qty, price in rows():
        out[name] = out.get(name, 0) + qty
    return out

def units() -> int:
    n = 0
    for name, qty, price in rows():
        n += qty
    return n
'''),

    # ============================== PLAIN ==============================
    dict(name="plain_optional_get", group="plain", bug_class="Optional from dict.get, distractor", sites=1,
         target="limits.py", fix_tokens=["is None", "get(k, "],
         files={"cfg.py": '''\
def load() -> dict[str, int]:
    return {"a": 5, "b": 0}
''',
                "limits.py": '''\
from cfg import load

def scaled(keys: list[str], factor: int) -> dict[str, int]:
    src = load()
    out = {}
    for k in keys:
        v = src.get(k)
        out[k] = v * factor
    return out
'''},
         # a configured 0 must survive (distractor against `if v:`); missing key -> 0
         test='''\
from limits import scaled
assert scaled(["a", "b", "c"], 2) == {"a": 10, "b": 0, "c": 0}
''',
         gold_target='''\
from cfg import load

def scaled(keys: list[str], factor: int) -> dict[str, int]:
    src = load()
    out = {}
    for k in keys:
        v = src.get(k)
        out[k] = (v if v is not None else 0) * factor
    return out
'''),

    dict(name="plain_bad_index_key", group="plain", bug_class="indexing remote dict[int,...] with str", sites=1,
         target="lookup.py", fix_tokens=["[k]"],
         files={"idx.py": '''\
def table() -> dict[int, str]:
    return {1: "a", 2: "b", 3: "c"}
''',
                "lookup.py": '''\
from idx import table

def names(keys: list[int]) -> list[str]:
    t = table()
    return [t[str(k)] for k in keys]
'''},
         test='''\
from lookup import names
assert names([2, 1]) == ["b", "a"]
''',
         gold_target='''\
from idx import table

def names(keys: list[int]) -> list[str]:
    t = table()
    return [t[k] for k in keys]
'''),

    dict(name="plain_none_default_arg", group="plain", bug_class="None passed where remote wants list", sites=1,
         target="collect.py", fix_tokens=["[]"],
         files={"util.py": '''\
def extend(base: list, *items) -> list:
    for it in items:
        base.append(it)
    return base
''',
                "collect.py": '''\
from util import extend

def gather(groups: list) -> list:
    acc = extend(None)
    for g in groups:
        acc = extend(acc, *g)
    return acc
'''},
         test='''\
from collect import gather
assert gather([["a", "b"], ["c"]]) == ["a", "b", "c"]
assert gather([]) == []
''',
         gold_target='''\
from util import extend

def gather(groups: list) -> list:
    acc = extend([])
    for g in groups:
        acc = extend(acc, *g)
    return acc
'''),

    # ============================== CONTROL (no type signal) ==============================
    dict(name="ctrl_truthiness", group="control", bug_class="truthiness drops legit 0 (logic, no type signal)", sites=1,
         target="limits.py", fix_tokens=["is not None"],
         files={"cfg.py": '''\
from dataclasses import dataclass

@dataclass
class Defaults:
    fallback: int

DEF = Defaults(99)
''',
                "limits.py": '''\
from cfg import Defaults, DEF

def effective(cfg: dict, keys: list[str], d: Defaults) -> dict:
    out = {}
    for k in keys:
        v = cfg.get(k)
        out[k] = v if v else d.fallback
    return out
'''},
         test='''\
from cfg import DEF
from limits import effective
assert effective({"a": 5, "b": 0}, ["a", "b", "c"], DEF) == {"a": 5, "b": 0, "c": 99}
''',
         gold_target='''\
from cfg import Defaults, DEF

def effective(cfg: dict, keys: list[str], d: Defaults) -> dict:
    out = {}
    for k in keys:
        v = cfg.get(k)
        out[k] = v if v is not None else d.fallback
    return out
'''),

    dict(name="ctrl_off_by_one", group="control", bug_class="off-by-one over a correctly-typed remote list", sites=2,
         target="windows.py", fix_tokens=["len(xs)", "+ 1", "i + 1"],
         files={"series.py": '''\
def data() -> list[int]:
    return [4, 1, 7, 3, 9]
''',
                "windows.py": '''\
from series import data

def pairwise_max() -> list[int]:
    xs = data()
    out = []
    for i in range(len(xs) - 1):
        out.append(max(xs[i], xs[i]))     # bug: compares xs[i] with itself, not xs[i+1]
    return out

def last_three() -> list[int]:
    xs = data()
    return xs[len(xs) - 3:len(xs) - 1]    # bug: drops the final element
'''},
         test='''\
from windows import pairwise_max, last_three
assert pairwise_max() == [4, 7, 7, 9]
assert last_three() == [7, 3, 9]
''',
         gold_target='''\
from series import data

def pairwise_max() -> list[int]:
    xs = data()
    out = []
    for i in range(len(xs) - 1):
        out.append(max(xs[i], xs[i + 1]))
    return out

def last_three() -> list[int]:
    xs = data()
    return xs[len(xs) - 3:]
'''),

    dict(name="ctrl_wrong_op", group="control", bug_class="wrong comparison operator (logic)", sites=2,
         target="filt.py", fix_tokens=[">", ">="],
         files={"nums.py": '''\
def values() -> list[int]:
    return [-2, 0, 3, -1, 5]
''',
                "filt.py": '''\
from nums import values

def positives() -> list[int]:
    return [v for v in values() if v < 0]

def count_nonneg() -> int:
    return sum(1 for v in values() if v < 0)
'''},
         test='''\
from filt import positives, count_nonneg
assert positives() == [3, 5]
assert count_nonneg() == 3
''',
         gold_target='''\
from nums import values

def positives() -> list[int]:
    return [v for v in values() if v > 0]

def count_nonneg() -> int:
    return sum(1 for v in values() if v >= 0)
'''),
]


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from scaffold.mock_env import MultiFileEnv

    def diag(files, target, test):
        e = MultiFileEnv(files, target, test); d = e.pyrefly_diagnostics(); e.close(); return d
    def passes(files, target, test):
        e = MultiFileEnv(files, target, test); ok = e.run_tests()["resolved"]; e.close(); return ok

    print(f"{'task':26} {'grp':8} {'buggy':6} {'gold':6} {'pyflerr':7} {'leak?':6} {'falseclear':10}")
    allok = True
    for t in TASKS_MF2:
        d_bug = diag(t["files"], t["target"], t["test"])
        nerr = d_bug.count("[error]")
        bug_fail = not passes(t["files"], t["target"], t["test"])
        gold_files = {**t["files"], t["target"]: t["gold_target"]}
        gold_pass = passes(gold_files, t["target"], t["test"])
        gold_diag = diag(gold_files, t["target"], t["test"])
        gold_clean = gold_diag.count("[error]") == 0
        # R3 transcription: does the buggy diagnostic literally contain a fix token?
        leak = any(tok and tok in d_bug for tok in t.get("fix_tokens", []))
        # R2 false-all-clear: a type-valid but wrong fix the test must still reject
        fc = "n/a"
        if t.get("wrong_typevalid"):
            wf = {**t["files"], t["target"]: t["wrong_typevalid"]}
            wf_clean = diag(wf, t["target"], t["test"]).count("[error]") == 0
            wf_fail = not passes(wf, t["target"], t["test"])
            fc = "BAD" if (wf_clean and wf_fail) else "ok"
        is_control = t["group"] == "control"
        # control: no type signal expected (nerr can be 0); others must fire
        ok = bug_fail and gold_pass and gold_clean and not leak and (nerr > 0 or is_control)
        if not ok: allok = False
        print(f"{t['name']:26} {t['group']:8} {'FAIL' if bug_fail else 'PASS!':6} "
              f"{'PASS' if gold_pass else 'FAIL!':6} {nerr:<7} {'LEAK' if leak else 'ok':6} {fc:10}"
              f"{'' if ok else '   <-- PROBLEM'}")
        if not gold_clean:
            print(f"      ! gold not pyrefly-clean: {gold_diag.splitlines()[:1]}")
    print(f"\nN={len(TASKS_MF2)}  groups:", {g: sum(1 for t in TASKS_MF2 if t['group']==g) for g in ('rich','plain','control')})
    print("ALL OK" if allok else "PROBLEMS — fix before review")
