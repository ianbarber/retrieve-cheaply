#!/usr/bin/env python3
"""GAP D — "inference-hard" coding tasks: is a type-checker's INFERENCE a
NON-REDUNDANT information source for a capable coding agent?

WHY THIS SUITE EXISTS. Every prior "LSP information" null in this project was about
LOCALIZATION or ENUMERATION: the answer sat verbatim in a file the agent could read
(a key name, a signature) or was a list of reference sites. The one untested
information regime is INFERENCE — facts a type-checker DERIVES that a model might not
reliably derive by reading: overload resolution, generic TypeVar propagation, union
narrowing, structural/Protocol/TypedDict typing. The consumer (scripts/api_agent.py,
suite "gapd") runs a frontier model with a `check_types()` tool available vs not and
measures whether the type information helps. A clean NULL (the model infers correctly
from reading lib.py) is a perfectly good outcome; the suite is built to measure
redundancy honestly, NOT to manufacture LSP dependence.

SHAPE. Each task is a tiny two-file workspace: a `lib.py` carrying the real `typing`
construct (overload / TypeVar / union / Protocol / TypedDict), and a `target.py` the
model must fix. The model is shown only `target.py` (a stub) + the test, and may read
`lib.py`. lib.py is deliberately SMALL — unlike the effic_real* efficiency suites, the
read cost is NOT the variable here; the variable is whether the INFERENCE the checker
performs is recoverable by the model from the source. So there is no R3 read-truncation
machinery; the point is type-trickiness, not size.

CONTRAST (rich vs control). The 6 RICH tasks: the idiomatic-but-wrong fix produces a
target-scoped pyrefly TYPE error that NAMES the mismatch (so `check_types()` carries
real, specific information) AND fails the behavioural test with a LESS-informative
symptom (a wrong value / AttributeError / "list indices must be integers", not a
message that spells out the fix). The 2 CONTROL tasks: the wrong fix is a logic/value
bug that pyrefly CANNOT see (pyrefly-blind) — so `check_types()` is genuinely useless
there. control_gross is plain arithmetic; union_payment is union-SHAPED yet blind
because the attribute the wrong fix reaches for exists on BOTH arms — a direct negative
showing that union shape alone does not make the checker informative.

Schema mirrors scripts/synth_tasks_effic_real2.py (minus the vendored-lib / defn-span /
R3 machinery, which are efficiency-suite concerns): each task is a dict with
  name, group("rich"|"control"), target("target.py"), symbol,
  files{path:content}, test, gold_target, wrong_guess, wrong_kind("type"|"value"),
  wrong_note.

VERIFIER (`__main__`, adapts effic_real2 R1-R5 + a new R6):
  R1  stub fails the behavioural test.
  R2  gold passes the test AND is target-scoped pyrefly-clean.
  R4  the idiomatic wrong guess fails the behavioural test (non-guessable) and != gold.
  R5  the test does not leak the answer API (symbol call / member access used in gold).
  R6  THE INFO CHANNEL: rich -> the wrong guess yields >=1 target-scoped pyrefly TYPE
      error (printed verbatim so a human can judge it is genuinely informative);
      control -> the wrong guess yields 0 target-scoped errors (pyrefly is blind here).
Run with python3; one pyrefly process at a time.
"""


def _task(name, group, symbol, lib, head, gold_body, wrong_body, test, wrong_kind, wrong_note):
    """Assemble a task dict. `head` is the import(s)+def+docstring (ending in a newline);
    bodies are the indented function body (a single statement block). The stub raises
    NotImplementedError; gold/wrong substitute the real body."""
    stub = head + "    raise NotImplementedError\n"
    gold = head + "    " + gold_body + "\n"
    wrong = head + "    " + wrong_body + "\n"
    return dict(
        name=name, group=group, target="target.py", symbol=symbol,
        files={"target.py": stub, "lib.py": lib},
        test=test, gold_target=gold,
        wrong_guess=wrong, wrong_kind=wrong_kind, wrong_note=wrong_note)


# ===================================================================================
# RICH — the correct fix hinges on a non-trivially INFERRED type; the wrong fix
# type-errors (pyrefly names the mismatch) AND fails the test less informatively.
# ===================================================================================

_OVERLOAD_QUERY = _task(
    "gapd_overload_query", "rich", "query",
    # @overload: the RETURN TYPE depends on the literal VALUE of the `one` flag.
    # query(one=True) -> dict[str,int]; the default call -> list[dict[str,int]].
    lib=(
        "from typing import overload, Literal\n\n"
        "@overload\n"
        "def query(table: str, *, one: Literal[True]) -> dict[str, int]: ...\n"
        "@overload\n"
        "def query(table: str, *, one: Literal[False] = ...) -> list[dict[str, int]]: ...\n"
        "def query(table, *, one=False):\n"
        "    rows = [{'n': 1}, {'n': 2}]\n"
        "    return rows[0] if one else rows\n"
    ),
    head=(
        "from lib import query\n\n"
        "def first_n(table: str) -> int:\n"
        '    """Return the value of column \'n\' from the single matching row."""\n'
    ),
    gold_body="row = query(table, one=True)\n    return row['n']",
    wrong_body="row = query(table)\n    return row['n']",
    test=(
        "from target import first_n\n"
        "assert first_n('t') == 1\n"
    ),
    wrong_kind="type",
    wrong_note=(
        "INFERENCE: the return type is overload-resolved by the literal flag — query(table) "
        "(default one=Literal[False]) -> list[dict[str,int]], NOT a dict; you must pass one=True "
        "to get a single dict. "
        "TEST SAYS: TypeError 'list indices must be integers or slices, not str' (a runtime crash "
        "that does not mention overloads). "
        "PYREFLY SAYS: [bad-index] 'Cannot index into `list[dict[str, int]]`' — it has RESOLVED the "
        "default overload to a list and tells you the value is a list, not a dict."),
)

_OVERLOAD_GET = _task(
    "gapd_overload_get", "rich", "Registry",
    # @overload by ARITY: get(key) -> int | None ; get(key, default: T) -> int | T.
    # Dropping the default leaves the return Optional, which the int signature rejects.
    lib=(
        "from typing import overload, TypeVar\n\n"
        "T = TypeVar('T')\n\n"
        "class Registry:\n"
        "    def __init__(self, d: dict[str, int]) -> None:\n"
        "        self._d = d\n"
        "    @overload\n"
        "    def get(self, key: str) -> int | None: ...\n"
        "    @overload\n"
        "    def get(self, key: str, default: T) -> int | T: ...\n"
        "    def get(self, key, default=None):\n"
        "        return self._d.get(key, default)\n"
    ),
    head=(
        "from lib import Registry\n\n"
        "def lookup(data: dict[str, int], key: str) -> int:\n"
        '    """Return the int stored at key, or 0 when the key is absent."""\n'
    ),
    gold_body="return Registry(data).get(key, 0)",
    wrong_body="return Registry(data).get(key)",
    test=(
        "from target import lookup\n"
        "assert lookup({'a': 5}, 'a') == 5\n"
        "assert lookup({}, 'x') == 0\n"
    ),
    wrong_kind="type",
    wrong_note=(
        "INFERENCE: the .get() overload set makes the 1-arg call return int | None and the 2-arg "
        "call return int | T; the idiomatic dict-style .get(key) therefore yields an Optional that "
        "the declared -> int forbids; you must pass the default (.get(key, 0)). "
        "TEST SAYS: bare AssertionError on the missing-key case (lookup returns None instead of 0) — "
        "no hint that the cause is an Optional return. "
        "PYREFLY SAYS: [bad-return] 'Returned type `int | None` is not assignable to declared return "
        "type `int`' — it names the inferred Optional precisely."),
)

_UNION_METHOD = _task(
    "gapd_union_method", "rich", "message",
    # union A | B: a method exists only on one arm; you must narrow (or pick a common
    # method) before calling it. render() is on both; escape() only on Html.
    lib=(
        "class Plain:\n"
        "    def __init__(self, body: str) -> None:\n"
        "        self.body = body\n"
        "    def render(self) -> str:\n"
        "        return self.body\n\n"
        "class Html:\n"
        "    def __init__(self, body: str) -> None:\n"
        "        self.body = body\n"
        "    def render(self) -> str:\n"
        "        return '<p>' + self.body + '</p>'\n"
        "    def escape(self) -> str:\n"
        "        return self.body.replace('<', '&lt;')\n\n"
        "def message(fmt: str, body: str) -> Plain | Html:\n"
        "    return Html(body) if fmt == 'html' else Plain(body)\n"
    ),
    head=(
        "from lib import message\n\n"
        "def show(fmt: str, body: str) -> str:\n"
        '    """Return the rendered message for the given format."""\n'
    ),
    gold_body="return message(fmt, body).render()",
    wrong_body="return message(fmt, body).escape()",
    test=(
        "from target import show\n"
        "assert show('plain', 'hi') == 'hi'\n"
        "assert show('html', 'hi') == '<p>hi</p>'\n"
    ),
    wrong_kind="type",
    wrong_note=(
        "INFERENCE: message() returns Plain | Html; render() is valid on the union but escape() "
        "exists only on the Html arm, so it is invalid on the union without narrowing. A model that "
        "reads only Html (or guesses a generic-sounding method) calls escape(). "
        "TEST SAYS: AttributeError \"'Plain' object has no attribute 'escape'\" on the plain case — a "
        "runtime crash, and only because that path was exercised. "
        "PYREFLY SAYS: [missing-attribute] 'Object of class `Plain` has no attribute `escape`' — "
        "statically, against the inferred union, before any path runs."),
)

_PROTOCOL_READER = _task(
    "gapd_protocol_reader", "rich", "consume",
    # Protocol: consume() requires a structural Readable (.read()). TextBox (.text())
    # is named to look right but does NOT satisfy it; Stream (.read()) does.
    lib=(
        "from typing import Protocol\n\n"
        "class Readable(Protocol):\n"
        "    def read(self) -> str: ...\n\n"
        "class TextBox:\n"
        "    def __init__(self, s: str) -> None:\n"
        "        self._s = s\n"
        "    def text(self) -> str:\n"
        "        return self._s\n\n"
        "class Stream:\n"
        "    def __init__(self, s: str) -> None:\n"
        "        self._s = s\n"
        "    def read(self) -> str:\n"
        "        return self._s\n\n"
        "def consume(src: Readable) -> str:\n"
        "    return src.read().upper()\n"
    ),
    head=(
        "from lib import consume, TextBox, Stream\n\n"
        "def shout(data: str) -> str:\n"
        '    """Wrap data in a source and return consume()\'s result."""\n'
    ),
    gold_body="return consume(Stream(data))",
    wrong_body="return consume(TextBox(data))",
    test=(
        "from target import shout\n"
        "assert shout('hi') == 'HI'\n"
    ),
    wrong_kind="type",
    wrong_note=(
        "INFERENCE: consume() requires anything STRUCTURALLY matching Readable (a .read() -> str); "
        "TextBox (with .text()) is the by-name temptation but does not satisfy the Protocol, Stream "
        "does. The model must match the Protocol's member, not the class name. "
        "TEST SAYS: AttributeError \"'TextBox' object has no attribute 'read'\" — a runtime crash that "
        "names the missing method but not the Protocol nor which class to use. "
        "PYREFLY SAYS: [bad-argument-type] 'Argument `TextBox` is not assignable to parameter `src` "
        "with type `Readable` in function `lib.consume`' — it frames it as a Protocol mismatch."),
)

_GENERIC_GRID = _task(
    "gapd_generic_grid", "rich", "only",
    # generic TypeVar propagation: only(list[T]) -> T. Over a list[list[int]] the type
    # variable binds T = list[int], so a SINGLE only() returns a row (list[int]), not a
    # scalar; you must call only() twice to reach an int.
    lib=(
        "from typing import TypeVar\n\n"
        "T = TypeVar('T')\n\n"
        "def only(xs: list[T]) -> T:\n"
        "    return xs[0]\n"
    ),
    head=(
        "from lib import only\n\n"
        "def top_left(grid: list[list[int]]) -> int:\n"
        '    """Return the value in the top-left cell of the grid\n'
        '    (the first element of the first row)."""\n'
    ),
    gold_body="return only(only(grid))",
    wrong_body="return only(grid)",
    test=(
        "from target import top_left\n"
        "assert top_left([[1, 2], [3, 4]]) == 1\n"
    ),
    wrong_kind="type",
    wrong_note=(
        "INFERENCE: only(xs: list[T]) -> T applied to a list[list[int]] binds T = list[int], so "
        "only(grid) is a ROW (list[int]), not a cell; reaching an int needs only(only(grid)). A model "
        "that mis-tracks one level of generic nesting calls only() once. "
        "TEST SAYS: AssertionError (top_left returns the list [1, 2] instead of 1) — a wrong value, "
        "no mention of the type variable. "
        "PYREFLY SAYS: [bad-return] 'Returned type `list[int]` is not assignable to declared return "
        "type `int`' — it has propagated T and shows the result is a list[int]."),
)

_TYPEDDICT_VEC = _task(
    "gapd_typeddict_vec", "rich", "magnitude_sq",
    # TypedDict: magnitude_sq wants a Vec (a dict with required str keys 'x','y'), which
    # is NOT structurally a tuple/sequence. The "vector = (x, y)" guess is rejected.
    lib=(
        "from typing import TypedDict\n\n"
        "class Vec(TypedDict):\n"
        "    x: int\n"
        "    y: int\n\n"
        "def magnitude_sq(v: Vec) -> int:\n"
        "    return v['x'] * v['x'] + v['y'] * v['y']\n"
    ),
    head=(
        "from lib import magnitude_sq\n\n"
        "def origin_dist_sq(x: int, y: int) -> int:\n"
        '    """Build a vector from x and y and return its squared magnitude."""\n'
    ),
    gold_body="return magnitude_sq({'x': x, 'y': y})",
    wrong_body="return magnitude_sq((x, y))",
    test=(
        "from target import origin_dist_sq\n"
        "assert origin_dist_sq(3, 4) == 25\n"
    ),
    wrong_kind="type",
    wrong_note=(
        "INFERENCE: a Vec is a TypedDict (a mapping with required string keys x, y), NOT a positional "
        "tuple; the natural 'a vector is (x, y)' guess passes a tuple, which is not structurally a Vec. "
        "TEST SAYS: TypeError 'tuple indices must be integers or slices, not str' (raised inside "
        "magnitude_sq when it does v['x']) — a crash that does not mention TypedDict. "
        "PYREFLY SAYS: [bad-argument-type] 'Argument `tuple[int, int]` is not assignable to parameter "
        "`v` with type `Vec` in function `lib.magnitude_sq`' — it names the TypedDict mismatch."),
)


# ===================================================================================
# CONTROL — pyrefly-BLIND value/logic bugs; check_types() is genuinely useless here
# (within-suite negatives). The wrong fix is well-typed; only the test catches it.
# ===================================================================================

_CONTROL_GROSS = _task(
    "gapd_control_gross", "control", "tax_rate",
    # plain arithmetic: gross = net*(1+rate); dropping the +1 returns just the tax.
    # Everything is float -> pyrefly sees nothing.
    lib=(
        "def tax_rate(region: str) -> float:\n"
        "    return {'us': 0.07, 'eu': 0.20}.get(region, 0.0)\n"
    ),
    head=(
        "from lib import tax_rate\n\n"
        "def gross(net: float, region: str) -> float:\n"
        '    """Return the gross price: net plus the region\'s tax."""\n'
    ),
    gold_body="return net * (1 + tax_rate(region))",
    wrong_body="return net * tax_rate(region)",
    test=(
        "from target import gross\n"
        "assert gross(100.0, 'us') == 107.0\n"
    ),
    wrong_kind="value",
    wrong_note=(
        "CONTROL (pyrefly-blind): net * tax_rate(region) returns only the tax (7.0) instead of net + "
        "tax (107.0); both sides are float, so the types are correct. "
        "TEST SAYS: AssertionError (7.0 != 107.0). "
        "PYREFLY SAYS: nothing (0 target-scoped errors) — the bug is arithmetic, not type."),
)

_UNION_PAYMENT = _task(
    "gapd_union_payment", "control", "make_payment",
    # union-SHAPED but pyrefly-blind: make_payment -> Cash | Card; the fee lives inside
    # total(), but .amount exists on BOTH arms, so reaching for .amount type-checks while
    # silently dropping the card fee. The negative twin of gapd_union_method.
    lib=(
        "class Cash:\n"
        "    def __init__(self, amount: int) -> None:\n"
        "        self.amount = amount\n"
        "    def total(self) -> int:\n"
        "        return self.amount\n\n"
        "class Card:\n"
        "    def __init__(self, amount: int) -> None:\n"
        "        self.amount = amount\n"
        "    def total(self) -> int:\n"
        "        return self.amount + 2\n\n"
        "def make_payment(kind: str, amount: int) -> Cash | Card:\n"
        "    return Cash(amount) if kind == 'cash' else Card(amount)\n"
    ),
    head=(
        "from lib import make_payment\n\n"
        "def settle(kind: str, amount: int) -> int:\n"
        '    """Return the amount actually collected: cash pays its face\n'
        '    amount; card adds a fixed 2-unit processing fee."""\n'
    ),
    gold_body="return make_payment(kind, amount).total()",
    wrong_body="return make_payment(kind, amount).amount",
    test=(
        "from target import settle\n"
        "assert settle('cash', 10) == 10\n"
        "assert settle('card', 10) == 12\n"
    ),
    wrong_kind="value",
    wrong_note=(
        "CONTROL (union-shaped but pyrefly-blind): the fee is encoded in total(), but .amount is a "
        "field on BOTH Cash and Card, so .amount type-checks cleanly while dropping the card fee. This "
        "is the negative twin of gapd_union_method: same union shape, but the wrong member exists on "
        "every arm, so the checker is silent. "
        "TEST SAYS: AssertionError on the card case (.amount = 10, expected 12). "
        "PYREFLY SAYS: nothing (0 target-scoped errors) — int field present on both arms."),
)


TASKS_GAPD = [
    _OVERLOAD_QUERY,
    _OVERLOAD_GET,
    _UNION_METHOD,
    _PROTOCOL_READER,
    _GENERIC_GRID,
    _TYPEDDICT_VEC,
    _CONTROL_GROSS,
    _UNION_PAYMENT,
]


def _api_leak_tokens(t: dict) -> list[str]:
    """The answer API that must NOT appear in the test (R5): each member ACCESS (`.name(`)
    and the bare symbol call (`sym(`) used in the gold target — same check as effic_real2."""
    import re
    gold = t["gold_target"]
    toks = set()
    for m in re.findall(r"\.\w+\(", gold):
        toks.add(m)
    sym = t["symbol"]
    if re.search(r"(?<!\.)\b" + re.escape(sym) + r"\(", gold):
        toks.add(sym + "(")
    return sorted(toks)


if __name__ == "__main__":
    import os as _os
    import sys
    import json
    import subprocess
    sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
    from scaffold.mock_env import MultiFileEnv, PYREFLY

    def passes(env):
        return env.run_tests()["resolved"]

    def target_errs(env, target):
        """UNCAPPED, TARGET-FILE-SCOPED pyrefly errors (full dicts), so we can both count and
        print the diagnostic text for R6."""
        try:
            r = subprocess.run([PYREFLY, "check", "--output-format", "json"], cwd=env.ws,
                               capture_output=True, text=True, timeout=90)
            errs = json.loads(r.stdout or "{}").get("errors", [])
        except Exception as e:
            return [{"name": "INVOKE_FAIL", "description": str(e)}]
        return [e for e in errs if _os.path.basename(e.get("path", "") or "") == target]

    def _diag_text(e):
        return (e.get("concise_description") or e.get("description") or "")[:200]

    print(f"{'task':24} {'grp':8} {'R1':5} {'R2':5} {'R2err':6} {'R4':6} {'kind':6} "
          f"{'R5':6} {'R6(info)':16}")
    allok = True
    diag_dump = []   # (task, list of "[code] text") for the wrong version
    for t in TASKS_GAPD:
        tgt = t["target"]
        sym = t["symbol"]

        # R1: stub fails the behavioural test.
        e1 = MultiFileEnv(t["files"], tgt, t["test"])
        r1 = not passes(e1)
        # informational: does the defn channel resolve the symbol?
        defn_span, defn_path = e1.goto_definition(sym)
        e1.close()
        defn_ok = defn_span is not None

        # R2: gold passes + target-scoped pyrefly-clean.
        gold_all = {**t["files"], tgt: t["gold_target"]}
        e2 = MultiFileEnv(gold_all, tgt, t["test"])
        r2_pass = passes(e2)
        gold_terrs = target_errs(e2, tgt)
        e2.close()
        r2_clean = len(gold_terrs) == 0

        # wrong guess: behavioural failure + target-scoped diagnostics.
        wrong_all = {**t["files"], tgt: t["wrong_guess"]}
        e4 = MultiFileEnv(wrong_all, tgt, t["test"])
        wrong_pass = passes(e4)
        wrong_terrs = target_errs(e4, tgt)
        e4.close()

        # R4: the idiomatic wrong guess fails the test, and differs from gold.
        r4 = (not wrong_pass) and (t["wrong_guess"] != t["gold_target"])

        # R5: no API leak in the test.
        leak_toks = [tok for tok in _api_leak_tokens(t) if tok in t["test"]]
        r5 = len(leak_toks) == 0

        # R6: info channel. rich -> wrong yields >=1 target TYPE error; control -> 0.
        n_werr = len(wrong_terrs)
        if t["group"] == "rich":
            r6 = n_werr > 0
            r6_str = f"rich:{n_werr}err"
        else:
            r6 = n_werr == 0
            r6_str = f"ctrl:{n_werr}err"

        diag_dump.append((t["name"], t["group"], [f"[{e.get('name')}] {_diag_text(e)}"
                                                  for e in wrong_terrs]))

        ok = r1 and r2_pass and r2_clean and r4 and r5 and r6
        if not ok:
            allok = False
        print(f"{t['name']:24} {t['group']:8} "
              f"{'FAIL' if r1 else 'PASS!':5} "
              f"{'PASS' if r2_pass else 'FAIL!':5} "
              f"{len(gold_terrs):<6} "
              f"{'fails' if r4 else 'SOLVES!':6} {t['wrong_kind']:6} "
              f"{'ok' if r5 else 'LEAK!':6} "
              f"{(r6_str + (' ok' if r6 else ' BAD!')):16}"
              f"{'' if ok else '  <-- PROBLEM'}")
        if not defn_ok:
            print(f"     ! note: goto_definition({sym!r}) did not resolve in workspace")
        if not r2_clean:
            print(f"     ! R2 gold NOT target-clean: {[(e.get('name'), _diag_text(e)) for e in gold_terrs][:3]}")
        if not r4:
            print(f"     ! R4 wrong guess did not fail the test (wrong_pass={wrong_pass}) "
                  f"or == gold")
        if leak_toks:
            print(f"     ! R5 API surface leaked into test: {leak_toks}")
        if not r6:
            print(f"     ! R6 info-channel expectation violated for group={t['group']}: "
                  f"wrong target-errs={n_werr} (rich wants >0, control wants 0)")

    # R6 evidence: print the actual wrong-version diagnostic text per task.
    print("\n--- R6 evidence: target-scoped pyrefly diagnostics on the WRONG guess ---")
    for name, grp, diags in diag_dump:
        if diags:
            print(f"  {name} ({grp}):")
            for d in diags:
                print(f"      {d}")
        else:
            print(f"  {name} ({grp}): (no target-scoped type errors — pyrefly is blind here)")

    print(f"\nALL OK ({len(TASKS_GAPD)} tasks)" if allok else "\nPROBLEMS — fix before review")
