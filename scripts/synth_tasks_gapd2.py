#!/usr/bin/env python3
"""GAP D2 — the HELD-OUT-PATH suite: a FAIR test of whether a type-checker's
information is NON-REDUNDANT for a coding agent.

WHY THIS SUITE EXISTS (and how it differs from gapd). A skeptical review found the
original gapd suite RIGGED toward "the checker is redundant": in every task the wrong
fix ALSO crashed the single behavioural test the agent could run, so a model that just
ran the test already caught the bug — `check_types()` could never be the *unique*
in-budget detector. The type information was a free rider on a test that already failed.

THE FIX — two behavioural tests per task, with HELD-OUT scoring:
  * test (VISIBLE): the agent runs this via its <test>/run_tests tool. It is built to
    PASS for the plausible WRONG fix — it exercises only inputs on which the latent bug
    is dormant — so an agent running only this test believes it is DONE.
  * held_out (HELD-OUT oracle): the agent never sees or runs it. It exercises the buggy
    path, so the WRONG fix FAILS it and the GOLD passes it. It is the real correctness
    score (scaffold.mock_env.MultiFileEnv.score() runs it; api_agent records it as
    `resolved`, with the visible test as `visible_pass`).

Now a static type checker can finally be the UNIQUE in-budget detector: it flags the
wrong fix STATICALLY (independent of which inputs the visible test happens to cover),
while the visible test — by construction — is silent. The latent bug lives on an
"untested path"; the checker sees it without running anything.

THE FAIR-TEST INVARIANT (enforced by __main__, the opposite of the old rigged R4):
  V1  stub:  held-out score() FAILS (the stub is unimplemented).
  V2  gold:  visible run_tests() PASSES *and* held-out score() PASSES, target-clean.
  V3  wrong: visible run_tests() PASSES *but* held-out score() FAILS (the latent bug the
             visible test misses), and wrong_guess != gold_target.  <-- THE KEY.
  V4  checker is the detector: the WRONG fix yields >=1 pyrefly type error that NAMES the
             issue (printed verbatim). rich -> V4 holds; control -> V4 must NOT hold
             (pyrefly-blind), so check_types is genuinely useless there (within-suite
             negative).

CONTENTS. 6 RICH tasks (each a tiny two-file workspace: lib.py carries the real `typing`
construct; target.py is the file the model fixes) + 1 CONTROL (a plain logic bug with no
type signal). Every rich task's wrong fix passes the visible test and fails the held-out
test, and pyrefly flags it target-scoped. The control's wrong fix does the same
behaviourally but pyrefly cannot see it.

ON P3 (DROPPED — honest note). The review's P3 was an unsafe parameter-narrowing override
(IntSink.push narrows int|str -> int). It was dropped because it is NOT a fair test of a
*unique detector*: pyrefly's `bad-override` diagnostic lives in lib.py and is IDENTICAL
for the stub, the gold, and the wrong fix (verified empirically — the target stays
target-scoped-clean in all three cases, because the naive `make_sink(strict).push(label)`
genuinely type-checks against the declared `Sink.push(int | str)`). So check_types shows
the SAME output whether the agent's fix is right or wrong; it cannot DISCRIMINATE the
wrong fix, which is exactly what V4 requires. It is a standing warning about lib.py, not a
wrong-fix detector. Rather than ship a muddy task whose "correct behaviour" is also
arbitrary (a strict numeric sink has no well-defined answer for a text label), we drop it
and add two extra held-out variants in its place (R4 union-arm, R5 union-operand).

The schema deliberately OMITS gapd's `symbol`/`wrong_kind` and ADDS `held_out`:
  name, group("rich"|"control"), target("target.py"),
  files{"target.py": stub, "lib.py": typing-construct},
  test(VISIBLE), held_out(HELD-OUT), gold_target, wrong_guess, wrong_note.
(An optional `whole_program` bool marks tasks whose discriminating diagnostic is cross-file
so the verifier checks whole-program pyrefly; no current task needs it — P3 was the only
candidate and it is dropped — but the machinery is implemented and tested.)

Run the verifier with python3; one pyrefly process at a time
(pkill -9 -f "[p]yrefly" between stale daemons if needed). Do NOT wire this into
synth_mf.py (the local runner has no held-out scoring); api_agent.py loads it via
--suite gapd2 / TASKS_GAPD2.
"""


def _task(name, group, lib, head, gold_body, wrong_body, test, held_out, regime,
          wrong_note, whole_program=False):
    """Assemble a task dict. `head` is import(s)+def+docstring (ending in a newline);
    `gold_body`/`wrong_body` are the full indented function body (already including the
    4-space indent and trailing newline). The stub raises NotImplementedError."""
    stub = head + "    raise NotImplementedError\n"
    return dict(
        name=name, group=group, target="target.py",
        files={"target.py": stub, "lib.py": lib},
        test=test, held_out=held_out,
        gold_target=head + gold_body, wrong_guess=head + wrong_body,
        regime=regime, wrong_note=wrong_note, whole_program=whole_program)


# ===================================================================================
# RICH — the wrong fix passes the VISIBLE test (its bug is dormant on those inputs) but
# fails the HELD-OUT test (which hits the buggy path), and pyrefly flags it statically.
# ===================================================================================

# P1 — optional-None narrowing dropped, latent until a key is missing. -------------
_P1_OPTIONAL_SUM = _task(
    "gapd2_optional_sum", "rich",
    lib=(
        "class Cache:\n"
        "    def __init__(self) -> None:\n"
        "        self._d: dict[str, int] = {}\n"
        "    def seed(self, k: str, v: int) -> None:\n"
        "        self._d[k] = v\n"
        "    def find(self, k: str) -> int | None:\n"
        "        return self._d.get(k)\n"
    ),
    head=(
        "from lib import Cache\n\n"
        "def total(cache: Cache, keys: list[str]) -> int:\n"
        '    """Sum the cached values for keys; a missing key contributes 0."""\n'
    ),
    gold_body="    return sum(cache.find(k) or 0 for k in keys)\n",
    wrong_body="    return sum(cache.find(k) for k in keys)\n",
    test=(
        "from target import total\n"
        "from lib import Cache\n"
        "c = Cache()\n"
        "c.seed('a', 1)\n"
        "c.seed('b', 2)\n"
        "assert total(c, ['a', 'b']) == 3\n"
    ),
    held_out=(
        "from target import total\n"
        "from lib import Cache\n"
        "c = Cache()\n"
        "c.seed('a', 1)\n"
        "assert total(c, ['a', 'missing']) == 1\n"
    ),
    regime="untested-path",
    wrong_note=(
        "REGIME untested-path: Cache.find returns int | None (None on a missing key); the "
        "fix must absorb the None ('... or 0'). "
        "VISIBLE seeds every key it queries, so find() never returns None and the bare "
        "sum(cache.find(k) ...) totals fine. "
        "HELD-OUT queries a MISSING key, so the wrong fix sums an int with None and raises "
        "TypeError; the gold returns the partial sum. "
        "PYREFLY: [no-matching-overload] 'No matching overload found for function `sum` "
        "called with arguments: (Generator[int | None])' — flagged with no input run."),
)

# P2 — TypedDict NotRequired-key typo masked by .get's default. --------------------
_P2_TYPEDDICT_KEY = _task(
    "gapd2_typeddict_key", "rich",
    lib=(
        "from typing import TypedDict, NotRequired\n\n"
        "class Order(TypedDict):\n"
        "    item: str\n"
        "    qty: int\n"
        "    discount: NotRequired[int]\n\n"
        "def price(o: Order, unit: int) -> int:\n"
        "    return o['qty'] * unit - o.get('discount', 0)\n"
    ),
    head=(
        "from lib import price\n\n"
        "def checkout(item: str, qty: int, unit: int, discount: int) -> int:\n"
        '    """Build an order and return its price; the discount is subtracted off."""\n'
    ),
    gold_body='    return price({"item": item, "qty": qty, "discount": discount}, unit)\n',
    wrong_body='    return price({"item": item, "qty": qty, "disc": discount}, unit)\n',
    test=(
        "from target import checkout\n"
        "assert checkout('book', 2, 5, 0) == 10\n"
    ),
    held_out=(
        "from target import checkout\n"
        "assert checkout('book', 2, 5, 3) == 7\n"
    ),
    regime="untested-path",
    wrong_note=(
        "REGIME untested-path: 'discount' is a NotRequired TypedDict key read via "
        "o.get('discount', 0); misspelling it ('disc') is silently swallowed by the default. "
        "VISIBLE passes discount=0, so the default-0 and the real value coincide and the "
        "typo is invisible. "
        "HELD-OUT passes discount=3, so the wrong order (key 'disc') falls back to 0 and "
        "over-charges; the gold subtracts 3. "
        "PYREFLY: [bad-typed-dict-key] 'Key `disc` is not defined in TypedDict `Order`' — "
        "the typo is named statically."),
)

# R3 — Literal-keyed overload whose default path returns int | None. ---------------
_R3_OVERLOAD_DEFAULT = _task(
    "gapd2_overload_default", "rich",
    lib=(
        "from typing import overload, Literal\n\n"
        "@overload\n"
        "def lookup(data: dict[str, int], key: str, mode: Literal['strict']) -> int: ...\n"
        "@overload\n"
        "def lookup(data: dict[str, int], key: str, mode: Literal['lenient'] = ...) -> int | None: ...\n"
        "def lookup(data, key, mode='lenient'):\n"
        "    if key in data:\n"
        "        return data[key]\n"
        "    return 0 if mode == 'strict' else None\n"
    ),
    head=(
        "from lib import lookup\n\n"
        "def score(data: dict[str, int], key: str) -> int:\n"
        '    """Return the integer stored at key; an absent key scores 0."""\n'
    ),
    gold_body="    return lookup(data, key, 'strict')\n",
    wrong_body="    return lookup(data, key)\n",
    test=(
        "from target import score\n"
        "assert score({'a': 5}, 'a') == 5\n"
    ),
    held_out=(
        "from target import score\n"
        "assert score({'a': 5}, 'x') == 0\n"
    ),
    regime="untested-path",
    wrong_note=(
        "REGIME untested-path: the Literal-keyed overload returns int only on the 'strict' "
        "arm; the default ('lenient') arm returns int | None. The fix must select the strict "
        "overload. "
        "VISIBLE queries a PRESENT key, so even the default overload returns the real int and "
        "the test passes. "
        "HELD-OUT queries an ABSENT key, so the default arm returns None (!= 0) and the wrong "
        "fix fails; the gold's 'strict' arm returns 0. "
        "PYREFLY: [bad-return] 'Returned type `int | None` is not assignable to declared "
        "return type `int`' — the overload is resolved to the Optional arm statically."),
)

# R4 — union method valid on only one arm; visible hits only the safe arm. ----------
_R4_UNION_ATTR = _task(
    "gapd2_union_attr", "rich",
    lib=(
        "class Basic:\n"
        "    def __init__(self, bal: int) -> None:\n"
        "        self.bal = bal\n"
        "    def balance(self) -> int:\n"
        "        return self.bal\n\n"
        "class Savings:\n"
        "    def __init__(self, bal: int) -> None:\n"
        "        self.bal = bal\n"
        "    def balance(self) -> int:\n"
        "        return self.bal\n"
        "    def available(self) -> int:\n"
        "        return self.bal\n\n"
        "def open_account(savings: bool, bal: int) -> Basic | Savings:\n"
        "    return Savings(bal) if savings else Basic(bal)\n"
    ),
    head=(
        "from lib import open_account\n\n"
        "def spendable(savings: bool, bal: int) -> int:\n"
        '    """Return the spendable balance of the account."""\n'
    ),
    gold_body="    return open_account(savings, bal).balance()\n",
    wrong_body="    return open_account(savings, bal).available()\n",
    test=(
        "from target import spendable\n"
        "assert spendable(True, 10) == 10\n"
    ),
    held_out=(
        "from target import spendable\n"
        "assert spendable(False, 10) == 10\n"
    ),
    regime="untested-path",
    wrong_note=(
        "REGIME untested-path: open_account returns Basic | Savings; balance() is on both "
        "arms, available() is on Savings only (and on Savings it equals balance()). "
        "VISIBLE constructs a Savings account (savings=True), where .available() exists and "
        "returns the same value as .balance(), so the wrong fix passes. "
        "HELD-OUT constructs a Basic account (savings=False), which has no .available(), so "
        "the wrong fix raises AttributeError; the gold's .balance() works on both arms. "
        "PYREFLY: [missing-attribute] 'Object of class `Basic` has no attribute `available`' "
        "— flagged against the inferred union, before any arm runs."),
)

# R5 — int | str union operand: arithmetic without narrowing. ----------------------
_R5_UNION_OP = _task(
    "gapd2_union_operand", "rich",
    lib=(
        "def cell(raw: str) -> int | str:\n"
        '    """Digit strings parse to int; everything else stays a string."""\n'
        "    return int(raw) if raw.isdigit() else raw\n"
    ),
    head=(
        "from lib import cell\n\n"
        "def bump(raw: str) -> str:\n"
        '    """Numeric cells return their successor as a string; non-numeric cells\n'
        '    are returned unchanged."""\n'
    ),
    gold_body=(
        "    v = cell(raw)\n"
        "    return str(v + 1) if isinstance(v, int) else v\n"
    ),
    wrong_body="    return str(cell(raw) + 1)\n",
    test=(
        "from target import bump\n"
        "assert bump('4') == '5'\n"
    ),
    held_out=(
        "from target import bump\n"
        "assert bump('ab') == 'ab'\n"
    ),
    regime="untested-path",
    wrong_note=(
        "REGIME untested-path: cell returns int | str; '+ 1' is valid only on the int arm, "
        "so the fix must narrow (isinstance) before incrementing. "
        "VISIBLE passes a DIGIT string, so cell returns an int, '+ 1' works, and bump('4') "
        "== '5'. "
        "HELD-OUT passes a NON-DIGIT string, so cell returns a str, 'ab' + 1 raises "
        "TypeError; the gold returns it unchanged. "
        "PYREFLY: [unsupported-operation] '`+` is not supported between `str` and "
        "`Literal[1]`' — the str arm of the union is rejected statically."),
)

# R6 — optional-field dereference, latent until the field is None. -----------------
_R6_OPTIONAL_ATTR = _task(
    "gapd2_optional_attr", "rich",
    lib=(
        "class Node:\n"
        "    def __init__(self, val: int, nxt: 'Node | None' = None) -> None:\n"
        "        self.val = val\n"
        "        self.nxt = nxt\n"
    ),
    head=(
        "from lib import Node\n\n"
        "def next_val(node: Node) -> int:\n"
        '    """Return the value of the node after `node`; if there is no next\n'
        '    node, return node\'s own value."""\n'
    ),
    gold_body="    return node.nxt.val if node.nxt is not None else node.val\n",
    wrong_body="    return node.nxt.val\n",
    test=(
        "from target import next_val\n"
        "from lib import Node\n"
        "assert next_val(Node(1, Node(2))) == 2\n"
    ),
    held_out=(
        "from target import next_val\n"
        "from lib import Node\n"
        "assert next_val(Node(5)) == 5\n"
    ),
    regime="untested-path",
    wrong_note=(
        "REGIME untested-path: Node.nxt is typed Node | None; dereferencing .val requires a "
        "None guard. "
        "VISIBLE passes a node that HAS a next node, so node.nxt.val resolves and the wrong "
        "fix passes. "
        "HELD-OUT passes a tail node (nxt is None), so node.nxt.val raises AttributeError on "
        "None; the gold falls back to node.val. "
        "PYREFLY: [missing-attribute] 'Object of class `NoneType` has no attribute `val`' — "
        "the optional field is flagged statically."),
)


# ===================================================================================
# CONTROL — a pyrefly-BLIND held-out bug: a plain logic error, no type signal. The
# wrong fix is well-typed; only the held-out test catches it, so check_types is useless
# here (the within-suite negative).
# ===================================================================================

_C1_BULK_DISCOUNT = _task(
    "gapd2_control_bulk", "control",
    lib=(
        "def unit_price(region: str) -> int:\n"
        "    return {'us': 3, 'eu': 5}.get(region, 4)\n"
    ),
    head=(
        "from lib import unit_price\n\n"
        "def order_total(units: int, region: str) -> int:\n"
        '    """Order total: units times the region\'s unit price. Orders of 10 or\n'
        '    more units get one unit free."""\n'
    ),
    gold_body="    return (units - 1 if units >= 10 else units) * unit_price(region)\n",
    wrong_body="    return units * unit_price(region)\n",
    test=(
        "from target import order_total\n"
        "assert order_total(3, 'us') == 9\n"
    ),
    held_out=(
        "from target import order_total\n"
        "assert order_total(10, 'us') == 27\n"
    ),
    regime="untested-path",
    wrong_note=(
        "CONTROL (pyrefly-blind): the bulk discount (one free unit at >=10 units) is pure "
        "arithmetic; every value is int, so the wrong fix is perfectly well-typed. "
        "VISIBLE orders 3 units (< 10), where no discount applies, so both fixes give 9. "
        "HELD-OUT orders 10 units, where the gold charges for 9 (= 27) and the wrong fix "
        "charges for 10 (= 30). "
        "PYREFLY: nothing (0 errors) — the bug is a missing branch, not a type mismatch, so "
        "check_types is genuinely useless here."),
)


TASKS_GAPD2 = [
    _P1_OPTIONAL_SUM,
    _P2_TYPEDDICT_KEY,
    _R3_OVERLOAD_DEFAULT,
    _R4_UNION_ATTR,
    _R5_UNION_OP,
    _R6_OPTIONAL_ATTR,
    _C1_BULK_DISCOUNT,
]


# ===================================================================================
# VERIFIER (__main__) — enforce the FAIR-TEST INVARIANT V1..V4 (held-out scoring).
# ===================================================================================
if __name__ == "__main__":
    import os as _os
    import sys
    import json
    import subprocess
    sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
    from scaffold.mock_env import MultiFileEnv, PYREFLY

    # Kill any stale pyrefly daemon before we start; we run strictly sequentially.
    subprocess.run(["pkill", "-9", "-f", "[p]yrefly"], capture_output=True)

    def pyrefly_errs(env, target, whole_program):
        """UNCAPPED pyrefly errors (full dicts). target-scoped unless whole_program, in
        which case all workspace errors count (cross-file diagnostics, e.g. in lib.py)."""
        try:
            r = subprocess.run([PYREFLY, "check", "--output-format", "json"], cwd=env.ws,
                               capture_output=True, text=True, timeout=90)
            errs = json.loads(r.stdout or "{}").get("errors", [])
        except Exception as e:
            return [{"name": "INVOKE_FAIL", "description": str(e)}]
        if whole_program:
            return errs
        return [e for e in errs if _os.path.basename(e.get("path", "") or "") == target]

    def _diag_text(e):
        return (e.get("concise_description") or e.get("description") or "")[:200]

    def _splice(t, body_src):
        return {**t["files"], t["target"]: body_src}

    print(f"{'task':24} {'grp':8} {'V1':5} {'V2vis':6} {'V2held':7} {'V2clean':8} "
          f"{'V3vis':6} {'V3held':7} {'V4':10}")
    allok = True
    diag_dump = []     # (name, group, [diag lines]) for the wrong fix
    regime_lines = []  # one descriptive line per task

    for t in TASKS_GAPD2:
        tgt = t["target"]
        wp = t.get("whole_program", False)

        # V1 — stub: held-out score() FAILS (unimplemented). (behavioural only)
        e_stub = MultiFileEnv(t["files"], tgt, t["test"], held_out_src=t["held_out"],
                              skip_pyrefly=True)
        v1 = not e_stub.score()["resolved"]
        e_stub.close()

        # V2 — gold: visible PASSES, held-out PASSES, target-scoped pyrefly clean.
        e_gold = MultiFileEnv(_splice(t, t["gold_target"]), tgt, t["test"],
                              held_out_src=t["held_out"])
        v2_vis = e_gold.run_tests()["resolved"]
        v2_held = e_gold.score()["resolved"]
        gold_errs = pyrefly_errs(e_gold, tgt, whole_program=False)
        e_gold.close()
        v2_clean = len(gold_errs) == 0

        # V3 — wrong: visible PASSES but held-out FAILS, and wrong != gold.
        e_wrong = MultiFileEnv(_splice(t, t["wrong_guess"]), tgt, t["test"],
                               held_out_src=t["held_out"])
        v3_vis = e_wrong.run_tests()["resolved"]
        v3_held_fail = not e_wrong.score()["resolved"]
        wrong_errs = pyrefly_errs(e_wrong, tgt, whole_program=wp)
        e_wrong.close()
        v3 = v3_vis and v3_held_fail and (t["wrong_guess"] != t["gold_target"])

        # V4 — checker is the detector. rich -> >=1 error that names the issue;
        #       control -> 0 errors (pyrefly-blind).
        n_werr = len(wrong_errs)
        if t["group"] == "rich":
            v4 = n_werr >= 1
            v4_str = f"rich:{n_werr}err"
        else:
            v4 = n_werr == 0
            v4_str = f"ctrl:{n_werr}err"

        diag_dump.append((t["name"], t["group"],
                          [f"[{e.get('name')}] {_os.path.basename(e.get('path','') or '')} "
                           f"L{e.get('line')}: {_diag_text(e)}" for e in wrong_errs]))
        regime_lines.append((t["name"], t["group"], t["regime"], t["wrong_note"]))

        ok = v1 and v2_vis and v2_held and v2_clean and v3 and v4
        if not ok:
            allok = False
        print(f"{t['name']:24} {t['group']:8} "
              f"{'FAIL' if v1 else 'PASS!':5} "
              f"{'PASS' if v2_vis else 'FAIL!':6} "
              f"{'PASS' if v2_held else 'FAIL!':7} "
              f"{'clean' if v2_clean else 'DIRTY!':8} "
              f"{'PASS' if v3_vis else 'FAIL!':6} "
              f"{'FAIL' if v3_held_fail else 'PASS!':7} "
              f"{(v4_str + (' ok' if v4 else ' BAD!')):10}"
              f"{'' if ok else '   <-- PROBLEM'}")
        if not v2_clean:
            print(f"     ! V2 gold NOT target-clean: "
                  f"{[(e.get('name'), _diag_text(e)) for e in gold_errs][:3]}")
        if not v3:
            print(f"     ! V3 violated: wrong visible_pass={v3_vis} held_out_fail="
                  f"{v3_held_fail} differs={(t['wrong_guess'] != t['gold_target'])}")
        if not v4:
            print(f"     ! V4 violated for group={t['group']}: wrong errs={n_werr} "
                  f"(rich wants >=1, control wants 0)")

    # V4 evidence — the diagnostic check_types() would surface on the WRONG fix.
    print("\n--- V4 evidence: the pyrefly diagnostic check_types() surfaces on the WRONG fix ---")
    for name, grp, diags in diag_dump:
        if diags:
            print(f"  {name} ({grp}):")
            for d in diags:
                print(f"      {d}")
        else:
            print(f"  {name} ({grp}): (no type errors — pyrefly is blind here)")

    # Per-task summary: regime / what the visible covers / what held-out adds / pyrefly.
    print("\n--- per-task regime summary ---")
    for name, grp, regime, note in regime_lines:
        print(f"  [{grp}/{regime}] {name}:")
        print(f"      {note}")

    print(f"\nALL OK ({len(TASKS_GAPD2)} tasks)" if allok
          else "\nPROBLEMS — fix before review")
