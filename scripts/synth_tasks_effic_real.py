#!/usr/bin/env python3
"""REAL-CODE definition-sufficient efficiency suite (mirror of synth_tasks_effic.py).

Identical in SHAPE to the synthetic `effic` suite, except the "big file" the agent must
consult is REAL, idiomatic, pure-Python library source — not synthetic filler. Each task
asks the agent to use one TOP-LEVEL symbol (a function/class) defined deep inside a large
vendored library module. Reading the whole module costs thousands of characters; a cheap
`<defn sym/>` returns the same definition in a few dozen lines. The suite tests whether the
preference for the cheaper retrieval action generalizes from synthetic to real code.

The libraries are chosen because their public APIs are genuinely NON-GUESSABLE: the correct
argument order / return-tuple order is the OPPOSITE of the idiomatic Python guess, so a model
that does not retrieve writes the idiomatic-but-wrong call and fails.

  - toolz (1.1.0, UNTYPED): functional helpers whose arg order is reversed vs the stdlib /
    idiom, e.g. `accumulate(binop, seq)` (cf. `itertools.accumulate(iterable, func)`),
    `groupby(key, seq)` (cf. `itertools.groupby(iterable, key)`), `nth(n, seq)`,
    `take(n, seq)`, `get(ind, seq, default)`, `get_in(keys, coll, default)`. Because toolz
    ships no type information, pyrefly cannot catch the misuse — the wrong guess fails at
    RUNTIME (wrong_kind="value"): these are pyrefly-blind, so solving them requires genuine
    retrieval, not a reaction to a type diagnostic.
  - more-itertools (11.1.0, TYPED via .pyi stubs): `take(n, iterable)` and `tail(n, iterable)`
    (arg order reversed vs the natural `(iterable, n)`) are caught by pyrefly AT THE TARGET as
    bad-argument-type (wrong_kind="type"); `partition(pred, iterable) -> (false, true)` has a
    non-obvious RETURN order (false items FIRST) that is type-clean but wrong if guessed.

Vendoring: whole packages are committed under scripts/effic_real_vendor/ (toolz, more_itertools).
The `files` dict of each task is built by READING those vendored files at import time via
`_pkg_files(pkg)`, so the real library source is exercised for real (imports resolve, behavioural
tests run the genuine implementation). The toolz `curried`/`sandbox` alternate-namespace
subpackages are intentionally NOT vendored — they re-bind every core symbol as a module-level
alias (`get = curry(toolz.get)`) which would shadow the real definition for go-to-definition.
See scripts/effic_real_vendor/VENDOR.md for versions and provenance.

Task schema (same as synth_tasks_effic.py, plus `defn_file`):
  name, group, target, symbol, defn_file (relpath of the module defining `symbol`),
  files = {target.py: stub, <real lib files...>},
  test, gold_target,
  symbol_defns = {"defn": {sym: real def span}, "members": ..., "refs": ...},
  wrong_guess, wrong_kind, wrong_note.

Verifier (run as `__main__`) checks for each task:
  R1 the stub fails the test;
  R2 the gold passes AND is pyrefly-clean *scoped to target.py* (the vendored libraries carry
     pre-existing pyrefly noise in their OWN files — toolz ~40, more_itertools ~17 errors — which
     is not the model's concern; we count only errors whose basename == the target file);
  R3 the symbol's defining real module is >= 150 lines AND defn_lines*5 < module_lines, AND the
     def starts within 15000 chars (the agent's <read> truncates at 16000, so a too-deep symbol
     would be a read-truncation confound rather than a fair defn-vs-read comparison);
  R4 the idiomatic wrong guess fails (type: target-scoped pyrefly errors > 0; value: test fails),
     so retrieval is required;
  R5 the test does not leak the real call-name / member-access the gold uses.
"""
import os
import ast

VENDOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "effic_real_vendor")


def _pkg_files(pkg: str) -> dict:
    """Walk the committed vendored snapshot of `pkg` and return {relpath: content} for every
    .py / .pyi / py.typed file — the real library source the workspace will contain. Relpaths are
    package-rooted (e.g. 'toolz/itertoolz.py') so imports resolve when written into the workspace."""
    out = {}
    root = os.path.join(VENDOR_DIR, pkg)
    for dirpath, _dirnames, filenames in os.walk(root):
        for f in sorted(filenames):
            if f.endswith((".py", ".pyi")) or f == "py.typed":
                ap = os.path.join(dirpath, f)
                rel = os.path.relpath(ap, VENDOR_DIR)
                with open(ap) as fh:
                    out[rel] = fh.read()
    return out


def _defn_span(defn_file: str, symbol: str) -> str:
    """Return the exact top-level source span of `symbol` in the vendored module `defn_file`,
    identical to what the env's AST `goto_definition` would return — extracted from the real source
    (never hand-pasted), so the recorded `defn` stays in sync with the vendored code."""
    path = os.path.join(VENDOR_DIR, defn_file)
    with open(path) as fh:
        src = fh.read()
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
            end = getattr(node, "end_lineno", node.lineno)
            return "\n".join(lines[node.lineno - 1:end])
    raise KeyError(f"{symbol} not a top-level def in {defn_file}")


# vendored source, read once at import time (NOT pasted as string literals)
TOOLZ_FILES = _pkg_files("toolz")
MI_FILES = _pkg_files("more_itertools")
_PKG_FILES = {"toolz": TOOLZ_FILES, "more_itertools": MI_FILES}


def _task(name, group, pkg, defn_file, symbol, sig, doc, gold_body, wrong_body,
          test, wrong_kind, wrong_note, members):
    """Build one task dict. `sig` is the target function signature (e.g. 'kth(seq, k)'); the
    target imports `symbol` from `pkg` and the stub/gold/wrong share the same head."""
    head = f"from {pkg} import {symbol}\n\ndef {sig}:\n    \"\"\"{doc}\"\"\"\n"
    stub = head + "    raise NotImplementedError\n"
    gold = head + f"    {gold_body}\n"
    wrong = head + f"    {wrong_body}\n"
    files = {"target.py": stub, **_PKG_FILES[pkg]}
    return dict(
        name=name, group=group, target="target.py", symbol=symbol, defn_file=defn_file,
        files=files, test=test, gold_target=gold,
        symbol_defns={"defn": {symbol: _defn_span(defn_file, symbol)},
                      "members": {symbol: members},
                      "refs": {symbol: ["target.py"]}},
        wrong_guess=wrong, wrong_kind=wrong_kind, wrong_note=wrong_note)


_IT = "toolz/itertoolz.py"
_DT = "toolz/dicttoolz.py"
_RC = "more_itertools/recipes.py"


TASKS_EFFIC_REAL = [
    # ============================ RICH — toolz, arg-order, pyrefly-blind (value) =============
    # accumulate(binop, seq): toolz puts the BINOP first — the reverse of itertools.accumulate.
    _task("effic_real_accumulate", "rich", "toolz", _IT, "accumulate",
          "running_max(xs: list[int]) -> list",
          "Return the running maximum of xs: out[i] is the largest of xs[: i + 1].",
          "return list(accumulate(max, xs))",
          "return list(accumulate(xs, max))",
          "from target import running_max\n"
          "assert running_max([3, 1, 4, 1, 5, 9, 2]) == [3, 3, 4, 4, 5, 9, 9]\n"
          "assert running_max([7]) == [7]\n",
          "value",
          "idiomatic accumulate(xs, max) like itertools.accumulate(iterable, func) (real: binop, seq) "
          "-> binop=list, not callable -> runtime TypeError (toolz is untyped, pyrefly-blind)",
          "accumulate(binop, seq, initial=no_default)  # toolz: BINOP first (cf. itertools.accumulate)"),

    # groupby(key, seq): toolz puts the KEY function first — reverse of itertools.groupby / pandas.
    _task("effic_real_groupby", "rich", "toolz", _IT, "groupby",
          "by_parity(nums: list[int]) -> dict",
          "Group the ints into even/odd buckets keyed by a bool (True == even).",
          "return groupby(lambda n: n % 2 == 0, nums)",
          "return groupby(nums, lambda n: n % 2 == 0)",
          "from target import by_parity\n"
          "assert by_parity([1, 2, 3, 4, 5, 6]) == {False: [1, 3, 5], True: [2, 4, 6]}\n"
          "assert by_parity([]) == {}\n",
          "value",
          "idiomatic groupby(nums, keyfn) like itertools.groupby(iterable, key) (real: key, seq) "
          "-> key=list, treated as non-callable getter then seq=function not iterable -> runtime error",
          "groupby(key, seq)  # toolz: KEY first (cf. itertools.groupby/pandas)"),

    # nth(n, seq): index FIRST (a sequence indexed seq[n] reads naturally as seq-first).
    _task("effic_real_nth", "rich", "toolz", _IT, "nth",
          "kth(seq, k: int)",
          "Return the element at zero-based position k of seq.",
          "return nth(k, seq)",
          "return nth(seq, k)",
          "from target import kth\n"
          "assert kth(['a', 'b', 'c', 'd'], 2) == 'c'\n"
          "assert kth('hello', 1) == 'e'\n",
          "value",
          "idiomatic nth(seq, k) (real: n, seq) -> n=sequence passed to islice as a count -> "
          "runtime TypeError (pyrefly-blind)",
          "nth(n, seq)  # toolz: index n FIRST"),

    # take(n, seq): count FIRST.
    _task("effic_real_take", "rich", "toolz", _IT, "take",
          "prefix(seq, k: int) -> list",
          "Return the first k items of seq as a list.",
          "return list(take(k, seq))",
          "return list(take(seq, k))",
          "from target import prefix\n"
          "assert prefix([10, 20, 30, 40], 2) == [10, 20]\n"
          "assert prefix('abc', 5) == ['a', 'b', 'c']\n",
          "value",
          "idiomatic take(seq, k) (real: n, seq) -> islice(count=seq, ...) -> runtime TypeError",
          "take(n, seq)  # toolz: count n FIRST"),

    # drop(n, seq): count FIRST.
    _task("effic_real_drop", "rich", "toolz", _IT, "drop",
          "without_first(seq, k: int) -> list",
          "Return every item of seq except the first k, as a list.",
          "return list(drop(k, seq))",
          "return list(drop(seq, k))",
          "from target import without_first\n"
          "assert without_first([1, 2, 3, 4, 5], 2) == [3, 4, 5]\n"
          "assert without_first('abcd', 1) == ['b', 'c', 'd']\n",
          "value",
          "idiomatic drop(seq, k) (real: n, seq) -> islice(count=seq, ...) -> runtime TypeError",
          "drop(n, seq)  # toolz: count n FIRST"),

    # take_nth(n, seq): stride FIRST.
    _task("effic_real_take_nth", "rich", "toolz", _IT, "take_nth",
          "every_kth(seq, k: int) -> list",
          "Return every k-th item of seq starting at index 0 (the stride is k).",
          "return list(take_nth(k, seq))",
          "return list(take_nth(seq, k))",
          "from target import every_kth\n"
          "assert every_kth([0, 1, 2, 3, 4, 5, 6], 2) == [0, 2, 4, 6]\n"
          "assert every_kth('abcdef', 3) == ['a', 'd']\n",
          "value",
          "idiomatic take_nth(seq, k) (real: n, seq) -> islice(step=seq) -> runtime TypeError",
          "take_nth(n, seq)  # toolz: stride n FIRST"),

    # interpose(el, seq): the separator ELEMENT comes first, the sequence second.
    _task("effic_real_interpose", "rich", "toolz", _IT, "interpose",
          "space_out(items: list, sep) -> list",
          "Return a list with sep inserted between every pair of consecutive items.",
          "return list(interpose(sep, items))",
          "return list(interpose(items, sep))",
          "from target import space_out\n"
          "assert space_out([1, 2, 3], 0) == [1, 0, 2, 0, 3]\n"
          "assert space_out(['a'], '-') == ['a']\n",
          "value",
          "idiomatic interpose(items, sep) (real: el, seq) -> iterates seq=sep -> "
          "runtime TypeError / wrong output (pyrefly-blind)",
          "interpose(el, seq)  # toolz: separator ELEMENT first"),

    # cons(el, seq): prepend element; the element comes first, sequence second.
    _task("effic_real_cons", "rich", "toolz", _IT, "cons",
          "prepend(seq, el) -> list",
          "Return a new list with el placed before the items of seq.",
          "return list(cons(el, seq))",
          "return list(cons(seq, el))",
          "from target import prepend\n"
          "assert prepend([2, 3], 1) == [1, 2, 3]\n"
          "assert prepend([], 9) == [9]\n",
          "value",
          "idiomatic cons(seq, el) — Python convention puts the container first (real: el, seq) "
          "-> chains [seq] then iterates el -> runtime TypeError / wrong output",
          "cons(el, seq)  # toolz: element to prepend FIRST"),

    # ============================ RICH — more-itertools, arg-order, TYPED (type) =============
    # take(n, iterable): n FIRST; typed via recipes.pyi, so pyrefly catches the swap at the target.
    _task("effic_real_mi_take", "rich", "more_itertools", _RC, "take",
          "first_n(xs: list[int], k: int) -> list[int]",
          "Return the first k items of xs as a list.",
          "return take(k, xs)",
          "return take(xs, k)",
          "from target import first_n\n"
          "assert first_n([10, 20, 30, 40], 2) == [10, 20]\n"
          "assert first_n([5], 3) == [5]\n",
          "type",
          "idiomatic take(xs, k) (real: take(n: int, iterable)) -> list where int expected and int "
          "where Iterable expected -> pyrefly bad-argument-type at target.py",
          "take(n: int, iterable) -> list  # more-itertools: count n FIRST"),

    # tail(n, iterable): n FIRST; typed -> pyrefly catches the swap.
    _task("effic_real_mi_tail", "rich", "more_itertools", _RC, "tail",
          "last_n(xs: list[int], k: int) -> list[int]",
          "Return the last k items of xs as a list, in their original order.",
          "return list(tail(k, xs))",
          "return list(tail(xs, k))",
          "from target import last_n\n"
          "assert last_n([1, 2, 3, 4, 5], 2) == [4, 5]\n"
          "assert last_n([9], 3) == [9]\n",
          "type",
          "idiomatic tail(xs, k) (real: tail(n: int, iterable)) -> pyrefly bad-argument-type at target.py",
          "tail(n: int, iterable) -> Iterator  # more-itertools: count n FIRST"),

    # ============================ CONTROL — pyrefly-blind, type-clean, WRONG VALUE ===========
    # get(ind, seq, default): index FIRST; the swap is type-clean and silently returns the default.
    _task("effic_real_get", "control", "toolz", _IT, "get",
          "lookup(book: dict, key, fallback)",
          "Return the value stored under key in book, or fallback if key is absent.",
          "return get(key, book, fallback)",
          "return get(book, key, fallback)",
          "from target import lookup\n"
          "assert lookup({'a': 1, 'b': 2}, 'b', -1) == 2\n"
          "assert lookup({'a': 1}, 'z', -1) == -1\n",
          "value",
          "idiomatic get(book, key, fallback) — container first like dict.get (real: ind, seq, default) "
          "-> book[ ... ] fails, the default branch returns fallback for EVERY key -> type-clean WRONG VALUE",
          "get(ind, seq, default=no_default)  # toolz: INDEX first, seq second"),

    # get_in(keys, coll, default): the KEY PATH comes first; the swap silently returns the default.
    _task("effic_real_get_in", "control", "toolz", _DT, "get_in",
          "deep(data: dict, path: list, fallback)",
          "Follow the path of keys into the nested data and return the value found, "
          "or fallback if any key along the path is missing.",
          "return get_in(path, data, fallback)",
          "return get_in(data, path, fallback)",
          "from target import deep\n"
          "assert deep({'a': {'b': 5}}, ['a', 'b'], 0) == 5\n"
          "assert deep({'a': {'b': 5}}, ['a', 'x'], 0) == 0\n",
          "value",
          "idiomatic get_in(data, path, fallback) — container first (real: keys, coll, default) "
          "-> reduces over the dict's keys, getitem fails, returns the default always -> type-clean WRONG VALUE",
          "get_in(keys, coll, default=None)  # toolz: KEY PATH first, collection second"),

    # partition(pred, iterable) -> (false_items, true_items): the FALSE side is returned FIRST.
    _task("effic_real_mi_partition", "control", "more_itertools", _RC, "partition",
          "keep_negatives(xs: list[int]) -> list[int]",
          "Return only the negative numbers of xs, in their original order.",
          "lo, hi = partition(lambda v: v < 0, xs)\n    return list(hi)",
          "lo, hi = partition(lambda v: v < 0, xs)\n    return list(lo)",
          "from target import keep_negatives\n"
          "assert keep_negatives([-2, 3, -4, 5, -6]) == [-2, -4, -6]\n"
          "assert keep_negatives([1, 2, 3]) == []\n",
          "value",
          "non-obvious return order: partition returns (FALSE_items, TRUE_items); guessing (true, false) "
          "and taking element [0] yields the NON-matching items -> both are Iterators, type-clean WRONG VALUE",
          "partition(pred, iterable) -> (false_items, true_items)  # FALSE side FIRST"),
]


def _api_leak_tokens(t: dict) -> list[str]:
    """The real API surface that must NOT appear in the test: each real member ACCESS (`.name(`)
    and the call-name as used in the gold call, derived from the gold_target so we never hand-
    maintain a brittle list (same check as synth_tasks_effic.py)."""
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

    def _env(files, target, test):
        return MultiFileEnv(files, target, test)

    def passes(env):
        return env.run_tests()["resolved"]

    def target_errs(env, target):
        """UNCAPPED, TARGET-FILE-SCOPED pyrefly error count. The vendored libraries carry their own
        pre-existing pyrefly noise in their OWN files (and pyrefly_diagnostics() only shows the first
        10 workspace errors, which the library noise can fill); we run pyrefly directly and keep only
        errors whose basename == the target file, the model's actual concern."""
        try:
            r = subprocess.run([PYREFLY, "check", "--output-format", "json"], cwd=env.ws,
                               capture_output=True, text=True, timeout=90)
            errs = json.loads(r.stdout or "{}").get("errors", [])
        except Exception:
            return [f"<pyrefly invocation failed>"]
        return [e for e in errs if _os.path.basename(e.get("path", "") or "") == target]

    print(f"{'task':24} {'grp':8} {'R1':5} {'R2':5} {'R2err':6} {'R3(d*5<L,<15k)':18} "
          f"{'R4':6} {'kind':6} {'R5':6} {'defL':5}")
    allok = True
    for t in TASKS_EFFIC_REAL:
        tgt = t["target"]
        sym = t["symbol"]

        # R1: stub FAILS the test
        e1 = _env(t["files"], tgt, t["test"])
        r1 = not passes(e1)
        # R3 uses the REAL resolver the agent uses: go-to-definition gives (span, defining file).
        defn_span, defn_path = e1.goto_definition(sym)
        e1.close()
        gd_ok = defn_span is not None and defn_path == t["defn_file"]

        # R2: gold PASSES AND is pyrefly-clean SCOPED TO target.py
        gold_all = {**t["files"], tgt: t["gold_target"]}
        e2 = _env(gold_all, tgt, t["test"])
        r2_pass = passes(e2)
        gold_terrs = target_errs(e2, tgt)
        e2.close()
        r2_clean = len(gold_terrs) == 0

        # R3: defining real module big enough; defn materially cheaper; def within the read window
        defn_src = t["files"].get(defn_path, "") if defn_path else ""
        file_lines = len(defn_src.splitlines())
        defn_lines = len(defn_span.splitlines()) if defn_span else 10 ** 9
        start_char = defn_src.find(defn_span) if (defn_span and defn_span in defn_src) else 10 ** 9
        r3 = (gd_ok and file_lines >= 150 and defn_lines * 5 < file_lines and start_char < 15000)

        # R4: NON-GUESSABLE — splice the idiomatic-wrong guess into the gold; it must FAIL.
        kind = t["wrong_kind"]
        wrong_all = {**t["files"], tgt: t["wrong_guess"]}
        e4 = _env(wrong_all, tgt, t["test"])
        wrong_pass = passes(e4)
        wrong_terrs = target_errs(e4, tgt)
        e4.close()
        if kind == "type":
            r4 = len(wrong_terrs) > 0
        else:  # value
            r4 = (not wrong_pass)
        r4 = r4 and (t["wrong_guess"] != t["gold_target"])

        # R5: no-leak — real member-access / call-name text absent from the test
        leak_toks = [tok for tok in _api_leak_tokens(t) if tok in t["test"]]
        r5 = len(leak_toks) == 0

        ok = r1 and r2_pass and r2_clean and r3 and r4 and r5
        if not ok:
            allok = False
        print(f"{t['name']:24} {t['group']:8} "
              f"{'FAIL' if r1 else 'PASS!':5} "
              f"{'PASS' if r2_pass else 'FAIL!':5} "
              f"{len(gold_terrs):<6} "
              f"{str(defn_lines) + '*5<' + str(file_lines) + ',' + str(start_char) + ('=y' if r3 else '=N!'):18} "
              f"{'fails' if r4 else 'SOLVES!':6} {kind:6} "
              f"{'ok' if r5 else 'LEAK!':6} {defn_lines:<5}"
              f"{'' if ok else '  <-- PROBLEM'}")
        if not gd_ok:
            print(f"     ! go-to-def mismatch: resolved {defn_path!r}, expected {t['defn_file']!r}")
        if not r4:
            print(f"     ! R4 wrong-guess did NOT fail: kind={kind} wrong_terrs={len(wrong_terrs)} "
                  f"wrong_pass={wrong_pass}  ({t['wrong_note']})")
        if leak_toks:
            print(f"     ! R5 API surface leaked into test: {leak_toks}")
        if not r2_clean:
            print(f"     ! gold not target-clean: {[e.get('name') for e in gold_terrs][:3]}")
    print(f"ALL OK ({len(TASKS_EFFIC_REAL)} tasks)" if allok else "PROBLEMS — fix before review")
