#!/usr/bin/env python3
"""REAL-CODE efficiency suite #2 — UN-MEMORIZED obscure-tail symbols (sibling of effic_real).

Same machinery, schema, and R1-R5 verifier as scripts/synth_tasks_effic_real.py, and it REUSES
the same committed vendored snapshot under scripts/effic_real_vendor/ (toolz 1.1.0, more-itertools
11.1.0). The difference is the SYMBOL CHOICE.

WHY THIS SUITE EXISTS. The GPU eval of effic_real found that the BASE Qwen2.5-Coder-7B has
MEMORIZED the famous toolz / more-itertools APIs (nth/take/drop/groupby/accumulate/get/get_in/...,
more_itertools take/tail/partition): ~35/41 base successes were solved COLD (reads=0, defn=0 =
guessed from weights). When the base can guess the API, the task does not force retrieval and the
token-efficiency claim cannot land on it. A static wrong-guess check (R4) cannot detect this —
R4 only proves the *idiomatic-wrong* call fails, not that the *correct* call is un-guessable.

So this suite deliberately picks symbols from the OBSCURE TAIL of the same packages — functions a
7B is unlikely to have memorized — AND whose signature/behaviour is non-obvious, so a model must
READ or <defn>-retrieve to use them correctly. None of effic_real's 13 symbols are reused.

  toolz (UNTYPED -> pyrefly-blind unless the misuse is an arg-COUNT error):
    reduceby(key, binop, seq, init)   simultaneous groupby+reduce; KEY and BINOP come first, seq third
    interleave(seqs)                  takes ONE list-of-sequences, NOT *seqs (interleave([a, b]))
    merge_with(func, *dicts)          func is applied to the LIST of all values for a key, not pairwise
    itemmap(func, d)                  func receives and returns a (key, value) TUPLE, not a value
    valfilter(predicate, d)           predicate receives the VALUE; keeps entries, predicate FIRST
    update_in(d, keys, func, default) applies func to the value at a nested key PATH; default REQUIRED
                                      for a missing key (func(default)), else func gets None
    thread_first(val, *forms)         threads val as the FIRST arg; multi-arg steps are (func, arg) TUPLES
    merge_sorted(*seqs, key=)         merges already-sorted iterables; *seqs varargs (control)
  more-itertools (TYPED via .pyi stubs):
    iter_except(function, exception)  call-until-exception; arg 2 is an EXCEPTION TYPE, not a sentinel
                                      value (cf. builtin iter(callable, sentinel)) -> pyrefly type error
    roundrobin(*iterables)            visits iterables in a cycle until exhausted; *iterables (control)
    grouper(iterable, n, incomplete)  default incomplete='fill' PADS the last group with None; you must
                                      pass incomplete='ignore' to drop it (control)

Task schema and verifier are identical to synth_tasks_effic_real.py (R1 stub fails; R2 gold passes &
target-file-scoped pyrefly-clean — the libraries carry their own noise; R3 defining module >= 150L,
defn_lines*5 < module_lines, AND the def starts within 15000 chars because <read> truncates at 16000;
R4 idiomatic wrong guess fails; R5 the test does not leak the real call-name/member-access).

CRITICAL (read-truncation): every symbol's definition starts within the first ~15000 chars of its
module, verified by R3. Symbols whose def is past the cap were dropped (e.g. toolz.partition @16152,
juxt/complement/flip/excepts in functoolz are past 15000) — see this module's git history / report.
"""
import os
import ast

VENDOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "effic_real_vendor")


def _pkg_files(pkg: str) -> dict:
    """Walk the committed vendored snapshot of `pkg` and return {relpath: content} for every
    .py / .pyi / py.typed file (package-rooted relpaths so imports resolve in the workspace)."""
    out = {}
    root = os.path.join(VENDOR_DIR, pkg)
    for dirpath, _dirnames, filenames in os.walk(root):
        for f in sorted(filenames):
            if f.endswith((".py", ".pyi")) or f == "py.typed":
                ap = os.path.join(dirpath, f)
                with open(ap) as fh:
                    out[os.path.relpath(ap, VENDOR_DIR)] = fh.read()
    return out


def _defn_span(defn_file: str, symbol: str) -> str:
    """Exact top-level source span of `symbol` in the vendored module `defn_file` — identical to what
    the env's AST `goto_definition` returns (extracted from the real source, never hand-pasted)."""
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


TOOLZ_FILES = _pkg_files("toolz")
MI_FILES = _pkg_files("more_itertools")
_PKG_FILES = {"toolz": TOOLZ_FILES, "more_itertools": MI_FILES}


def _task(name, group, pkg, defn_file, symbol, sig, doc, gold_body, wrong_body,
          test, wrong_kind, wrong_note, members):
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
_FT = "toolz/functoolz.py"
_RC = "more_itertools/recipes.py"


TASKS_EFFIC_REAL2 = [
    # ===================== RICH — obscure toolz/more-itertools, non-guessable call =====================

    # reduceby(key, binop, seq, init): a simultaneous groupby+reduce. OBSCURE (niche toolz function).
    # NON-GUESSABLE: the KEY function and the BINOP come first, the data third — the opposite of the
    # data-first shape a model would reach for ("reduce this list by ..."). Guessing data-first feeds a
    # non-callable key / a function as the sequence -> runtime failure.
    _task("effic_real2_reduceby", "rich", "toolz", _IT, "reduceby",
          "sum_by_parity(nums: list)",
          "Group the ints by even/odd (bool key) and sum each group; return the {bool: total} dict.",
          "return reduceby(lambda n: n % 2 == 0, lambda acc, n: acc + n, nums, 0)",
          "return reduceby(nums, lambda n: n % 2 == 0, lambda acc, n: acc + n, 0)",
          "from target import sum_by_parity\n"
          "assert sum_by_parity([1, 2, 3, 4, 5]) == {False: 9, True: 6}\n"
          "assert sum_by_parity([]) == {}\n",
          "value",
          "idiomatic data-first reduceby(nums, key, binop, 0) (real: key, binop, seq, init) "
          "-> key=list (non-callable) / seq=function (non-iterable) -> runtime error (toolz untyped)",
          "reduceby(key, binop, seq, init=no_default)  # KEY and BINOP first, sequence third"),

    # interleave(seqs): OBSCURE; NON-GUESSABLE because it takes ONE iterable-of-iterables, not *seqs.
    # The natural guess interleave(a, b) is an arg-COUNT error (def takes a single positional) -> pyrefly
    # flags it even though toolz is untyped.
    _task("effic_real2_interleave", "rich", "toolz", _IT, "interleave",
          "zip_flat(a: list, b: list) -> list",
          "Interleave a and b element by element: a[0], b[0], a[1], b[1], ... as a list.",
          "return list(interleave([a, b]))",
          "return list(interleave(a, b))",
          "from target import zip_flat\n"
          "assert zip_flat([1, 2, 3], [4, 5, 6]) == [1, 4, 2, 5, 3, 6]\n"
          "assert zip_flat([1], [2, 3]) == [1, 2, 3]\n",
          "type",
          "idiomatic interleave(a, b) (real: a single list-of-sequences interleave([a, b])) "
          "-> too many positional arguments -> pyrefly bad-argument-count at target.py",
          "interleave(seqs)  # ONE iterable-of-iterables, e.g. interleave([a, b]) (NOT *seqs)"),

    # merge_with(func, *dicts): OBSCURE. NON-GUESSABLE callback shape: func is handed the LIST of all
    # values mapped to a key (func([v1, v2, ...])), NOT a pairwise reducer. A binary-reducer guess is
    # called with one list argument -> arity error at runtime.
    _task("effic_real2_merge_with", "rich", "toolz", _DT, "merge_with",
          "combine(d1: dict, d2: dict) -> dict",
          "Merge two dicts; where a key is in both, the result holds the SUM of the two values.",
          "return merge_with(sum, d1, d2)",
          "return merge_with(lambda x, y: x + y, d1, d2)",
          "from target import combine\n"
          "assert combine({'a': 1, 'b': 2}, {'a': 10, 'c': 3}) == {'a': 11, 'b': 2, 'c': 3}\n"
          "assert combine({}, {'z': 9}) == {'z': 9}\n",
          "value",
          "idiomatic pairwise reducer merge_with(lambda x, y: x + y, ...) (real: func gets a LIST of "
          "values, e.g. sum) -> 2-arg lambda called with one list -> runtime TypeError",
          "merge_with(func, *dicts)  # func is applied to the LIST of values per key"),

    # itemmap(func, d): OBSCURE. NON-GUESSABLE callback shape: func receives a (key, value) TUPLE and
    # must return a (key, value) tuple. A value-only transform gets the whole tuple -> wrong/oversized
    # update tuple -> runtime error.
    _task("effic_real2_itemmap", "rich", "toolz", _DT, "itemmap",
          "double_values(d: dict) -> dict",
          "Return a new dict with every value doubled and keys unchanged.",
          "return itemmap(lambda kv: (kv[0], kv[1] * 2), d)",
          "return itemmap(lambda v: v * 2, d)",
          "from target import double_values\n"
          "assert double_values({'a': 1, 'b': 2}) == {'a': 2, 'b': 4}\n"
          "assert double_values({}) == {}\n",
          "value",
          "idiomatic value-transform itemmap(lambda v: v * 2, d) (real: func gets a (k, v) TUPLE and "
          "returns one) -> (k, v) * 2 makes a 4-tuple -> dict update ValueError at runtime",
          "itemmap(func, d)  # func maps a (key, value) TUPLE to a (key, value) tuple"),

    # valfilter(predicate, d): OBSCURE. NON-GUESSABLE: predicate comes FIRST and receives the VALUE
    # (filter-by-value; cf. keyfilter/itemfilter). A model that assumes the predicate gets the (k, v)
    # item indexes an int -> runtime error.
    _task("effic_real2_valfilter", "rich", "toolz", _DT, "valfilter",
          "big_values(d: dict) -> dict",
          "Return only the items of d whose VALUE is greater than 2.",
          "return valfilter(lambda v: v > 2, d)",
          "return valfilter(lambda kv: kv[1] > 2, d)",
          "from target import big_values\n"
          "assert big_values({'a': 1, 'b': 3, 'c': 5}) == {'b': 3, 'c': 5}\n"
          "assert big_values({'a': 0}) == {}\n",
          "value",
          "idiomatic item-predicate valfilter(lambda kv: kv[1] > 2, d) (real: predicate gets the VALUE) "
          "-> indexing an int kv[1] -> runtime TypeError",
          "valfilter(predicate, d)  # predicate FIRST, receives the VALUE"),

    # update_in(d, keys, func, default): OBSCURE. NON-GUESSABLE: the 3rd arg is a FUNCTION applied to the
    # value at the nested key PATH, and `default` is REQUIRED when the key is missing — the function is
    # then called as func(default). Omitting default makes func receive None -> runtime error on a miss.
    _task("effic_real2_update_in", "rich", "toolz", _DT, "update_in",
          "bump(d: dict, key)",
          "Return a copy of d with the integer counter at `key` incremented by one; a missing key "
          "starts from zero (so it becomes 1).",
          "return update_in(d, [key], lambda v: v + 1, 0)",
          "return update_in(d, [key], lambda v: v + 1)",
          "from target import bump\n"
          "assert bump({'x': 5}, 'x') == {'x': 6}\n"
          "assert bump({}, 'y') == {'y': 1}\n",
          "value",
          "idiomatic update_in(d, [key], inc) without a default (real: default is required for a missing "
          "key, func(default)) -> missing key -> func(None) -> None + 1 -> runtime TypeError",
          "update_in(d, keys, func, default=None)  # func applied at the key PATH; default for misses"),

    # thread_first(val, *forms): OBSCURE (toolz threading macro). NON-GUESSABLE: val is threaded as the
    # FIRST argument of each step, and any step needing extra args must be a (func, *args) TUPLE — a flat
    # func, arg, func, arg sequence is misread as bare callables -> wrong arity at runtime.
    _task("effic_real2_thread_first", "rich", "toolz", _FT, "thread_first",
          "calc(x: int)",
          "Thread x through: first add 3, then multiply by 2; return the result.",
          "return thread_first(x, (lambda v, k: v + k, 3), (lambda v, k: v * k, 2))",
          "return thread_first(x, lambda v, k: v + k, 3, lambda v, k: v * k, 2)",
          "from target import calc\n"
          "assert calc(5) == 16\n"
          "assert calc(0) == 6\n",
          "value",
          "idiomatic flat thread_first(x, f, 3, g, 2) (real: multi-arg steps are (func, arg) TUPLES) "
          "-> a 2-arg lambda is called as f(x) -> runtime TypeError",
          "thread_first(val, *forms)  # val threaded FIRST; multi-arg steps are (func, arg) tuples"),

    # iter_except(function, exception, first=None): OBSCURE. NON-GUESSABLE: arg 2 is an EXCEPTION TYPE
    # that ends the loop (the analogue of the builtin iter(callable, SENTINEL), but with an exception).
    # Passing a sentinel VALUE (e.g. None) where the exception type belongs is caught by pyrefly (the
    # stub types it `type[BaseException] | tuple[...]`).
    _task("effic_real2_iter_except", "rich", "more_itertools", _RC, "iter_except",
          "drain(items: list) -> list",
          "Pop every element off a copy of items and return them in pop order (last in, first out).",
          "stack = list(items)\n    return list(iter_except(stack.pop, IndexError))",
          "stack = list(items)\n    return list(iter_except(stack.pop, None))",
          "from target import drain\n"
          "assert drain([1, 2, 3]) == [3, 2, 1]\n"
          "assert drain([]) == []\n",
          "type",
          "idiomatic sentinel iter_except(stack.pop, None) like iter(callable, sentinel) (real: arg 2 is "
          "an EXCEPTION TYPE) -> None not assignable to type[BaseException] -> pyrefly type error at target",
          "iter_except(function, exception, first=None)  # arg 2 is an EXCEPTION TYPE, not a sentinel"),

    # ===================== CONTROL — pyrefly-blind, type-clean WRONG VALUE (no crash) =================

    # roundrobin(*iterables): control. Forgetting the splat (passing the list-of-lists as ONE iterable)
    # is type-clean and silently yields the sublists instead of the round-robined elements.
    _task("effic_real2_roundrobin", "control", "more_itertools", _RC, "roundrobin",
          "weave(groups: list) -> list",
          "Round-robin the given groups: take one item from each in turn until all are exhausted.",
          "return list(roundrobin(*groups))",
          "return list(roundrobin(groups))",
          "from target import weave\n"
          "assert weave([[1, 2, 3], [4, 5]]) == [1, 4, 2, 5, 3]\n"
          "assert weave([[1], [2], [3]]) == [1, 2, 3]\n",
          "value",
          "idiomatic roundrobin(groups) without the splat (real: *iterables) -> treats the list-of-lists "
          "as one iterable and yields the sublists -> type-clean WRONG VALUE",
          "roundrobin(*iterables)  # splat the groups: roundrobin(*groups)"),

    # grouper(iterable, n, incomplete='fill', ...): control. The default incomplete='fill' PADS the last
    # short group with None; you must pass incomplete='ignore' to drop it. Omitting it is type-clean and
    # returns an extra None-padded tuple.
    _task("effic_real2_grouper", "control", "more_itertools", _RC, "grouper",
          "chunks(xs: list, n: int) -> list",
          "Split xs into consecutive groups of length n, DROPPING any leftover items that do not fill "
          "a whole group.",
          "return list(grouper(xs, n, incomplete='ignore'))",
          "return list(grouper(xs, n))",
          "from target import chunks\n"
          "assert chunks([1, 2, 3, 4, 5, 6, 7], 3) == [(1, 2, 3), (4, 5, 6)]\n"
          "assert chunks([1, 2], 3) == []\n",
          "value",
          "idiomatic grouper(xs, n) using the default (real: default incomplete='fill' pads with None; "
          "need incomplete='ignore') -> a trailing (7, None, None) tuple -> type-clean WRONG VALUE",
          "grouper(iterable, n, incomplete='fill', fillvalue=None)  # pass incomplete='ignore' to drop the tail"),

    # merge_sorted(*seqs, key=None): control. Forgetting the splat (passing [a, b] as one arg) is
    # type-clean and yields the two sub-lists instead of the merged stream.
    _task("effic_real2_merge_sorted", "control", "toolz", _IT, "merge_sorted",
          "merge_two(a: list, b: list) -> list",
          "Merge two already-sorted lists into one sorted list.",
          "return list(merge_sorted(a, b))",
          "return list(merge_sorted([a, b]))",
          "from target import merge_two\n"
          "assert merge_two([1, 3, 5], [2, 4, 6]) == [1, 2, 3, 4, 5, 6]\n"
          "assert merge_two([], [1, 2]) == [1, 2]\n",
          "value",
          "idiomatic merge_sorted([a, b]) without the splat (real: *seqs) -> a single iterable, so it "
          "yields the two sub-lists unchanged -> type-clean WRONG VALUE",
          "merge_sorted(*seqs, key=None)  # splat the lists: merge_sorted(a, b)"),
]


def _api_leak_tokens(t: dict) -> list[str]:
    """The real API surface that must NOT appear in the test: each real member ACCESS (`.name(`) and the
    call-name as used in the gold call, derived from the gold_target (same check as synth_tasks_effic.py)."""
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
        """UNCAPPED, TARGET-FILE-SCOPED pyrefly error count (vendored libs carry their own noise; the
        capped pyrefly_diagnostics() can be filled by it, so we run pyrefly directly and basename-filter)."""
        try:
            r = subprocess.run([PYREFLY, "check", "--output-format", "json"], cwd=env.ws,
                               capture_output=True, text=True, timeout=90)
            errs = json.loads(r.stdout or "{}").get("errors", [])
        except Exception:
            return ["<pyrefly invocation failed>"]
        return [e for e in errs if _os.path.basename(e.get("path", "") or "") == target]

    print(f"{'task':26} {'grp':8} {'R1':5} {'R2':5} {'R2err':6} {'R3(d*5<L,<15k)':18} "
          f"{'R4':6} {'kind':6} {'R5':6} {'defL':5}")
    allok = True
    for t in TASKS_EFFIC_REAL2:
        tgt = t["target"]
        sym = t["symbol"]

        e1 = MultiFileEnv(t["files"], tgt, t["test"])
        r1 = not passes(e1)
        defn_span, defn_path = e1.goto_definition(sym)
        e1.close()
        gd_ok = defn_span is not None and defn_path == t["defn_file"]

        gold_all = {**t["files"], tgt: t["gold_target"]}
        e2 = MultiFileEnv(gold_all, tgt, t["test"])
        r2_pass = passes(e2)
        gold_terrs = target_errs(e2, tgt)
        e2.close()
        r2_clean = len(gold_terrs) == 0

        defn_src = t["files"].get(defn_path, "") if defn_path else ""
        file_lines = len(defn_src.splitlines())
        defn_lines = len(defn_span.splitlines()) if defn_span else 10 ** 9
        start_char = defn_src.find(defn_span) if (defn_span and defn_span in defn_src) else 10 ** 9
        r3 = (gd_ok and file_lines >= 150 and defn_lines * 5 < file_lines and start_char < 15000)

        kind = t["wrong_kind"]
        wrong_all = {**t["files"], tgt: t["wrong_guess"]}
        e4 = MultiFileEnv(wrong_all, tgt, t["test"])
        wrong_pass = passes(e4)
        wrong_terrs = target_errs(e4, tgt)
        e4.close()
        if kind == "type":
            r4 = len(wrong_terrs) > 0
        else:
            r4 = (not wrong_pass)
        r4 = r4 and (t["wrong_guess"] != t["gold_target"])

        leak_toks = [tok for tok in _api_leak_tokens(t) if tok in t["test"]]
        r5 = len(leak_toks) == 0

        ok = r1 and r2_pass and r2_clean and r3 and r4 and r5
        if not ok:
            allok = False
        print(f"{t['name']:26} {t['group']:8} "
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
    print(f"ALL OK ({len(TASKS_EFFIC_REAL2)} tasks)" if allok else "PROBLEMS — fix before review")
