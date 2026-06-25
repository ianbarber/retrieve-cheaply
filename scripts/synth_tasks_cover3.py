#!/usr/bin/env python3
"""COVERAGE-JUDGING suite v3 — a CONTROL suite that adds ONE adversarial variant to cover2 to rule out a
SHAPE/FORM-keying explanation of the read decision. cover3 = cover2's three variants (_suf, _f1ins, _f2ins)
PLUS a fourth `_sufx` variant per topic. Everything cover2 establishes (topics, constants, target.py, tests,
helpers, verifier gates) is copied wholesale and unchanged; only the new `_sufx` emitter + its gate are added.

WHY v3 (the loophole in cover2 this closes):
  In cover2 the two INSUFFICIENT variants both reference a NAME (`_REG["grade_cut"]`, `_CFG.grade_cut`) while
  the SUFFICIENT one (_suf) carries a BARE LITERAL (`53`) inline. So across cover2 the surface property
  "the returned <defn sym> span references a name" correlates PERFECTLY with "must read on":
      _suf   -> bare literal      -> no read
      _f1ins -> name reference    -> read
      _f2ins -> name reference    -> read
  A model could therefore read-when-needed by keying purely on that FORM ("the defn span contains a
  name-reference -> read") WITHOUT ever judging whether the needed value is actually present in the span it
  got back. cover2 cannot tell a CONTENT-judging model from a FORM-keying one.

THE FIX — the `_sufx` variant (coverage SUFFICIENT, but in REFERENCE FORM):
  `_sufx` is coverage-SUFFICIENT (the gold value IS inside the `<defn sym>` span) but written in REFERENCE
  FORM (the value is bound to a LOCAL and accessed by name), so the span LOOKS like an indirection. This
  BREAKS the cover2 correlation: now "name-reference in the span" no longer implies "must read".
    - a CONTENT-judging model does NOT read on _sufx — the value 53 is right there in the span it got;
    - a FORM-keying  model DOES   read on _sufx — it sees a name-reference and reads, UNNECESSARILY.
  read(_sufx) is thus the DISCRIMINATOR:
      ~read(_sufx)                  => the model is judging CONTENT (correct: it has what it needs);
      ~read(_f1ins) & ~read(_f2ins) => the model is keying on FORM  (wrong: it skipped a genuine read).

  For topic `grade` (gold const 53), biglib's `grade` for _sufx is:
      def grade(score):
          _c = 53                                # value PRESENT in the <defn grade> span (SUFFICIENT)...
          return "P" if score >= _c else "F"     # ...but accessed via a LOCAL name (reference FORM)
  `goto_definition("grade")` returns the whole FunctionDef span (lineno..end_lineno), which INCLUDES the
  `_c = 53` line — so the span CONTAINS 53 and the task is solvable from the defn alone, NO read needed,
  even though it reads like the _f1ins/_f2ins indirections. (_f1ins/_f2ins remain genuinely read-only:
  no single <defn> reveals the value — re-confirmed by R-defn-UNREACHABLE, exactly as in cover2.)

NAMING + SCHEMA: `cover3_<topic>_suf`, `_sufx`, `_f1ins`, `_f2ins` (4 variants x 6 topics = 24 tasks). The
`_sufx` meta is {"coverage":"sufficient","mechanism":"sufx"}, defn_sufficient=True, requires_read=False;
everything else mirrors cover2's schema. R-surface now spans FOUR variants per topic (all byte-identical
target.py + test + symbol). The KEY new gate is R-sufx-sufficient: goto_definition(sym) on _sufx CONTAINS
needed_value (genuinely defn-sufficient) even though its body references a local name.

Run (pyrefly runs SEQUENTIALLY; kill daemon first):
  pkill -9 -x pyrefly; \
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/mnt/nas/hf-cache \
  .venv-streams.system/bin/python scripts/synth_tasks_cover3.py
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# cover3 reuses cover2's topics, constants, target.py, tests, helpers and the two insufficient emitters
# VERBATIM — we import them rather than re-author them, so the two suites cannot drift. Only the new _sufx
# emitter and its gate are added here.
from scripts.synth_tasks_cover2 import (
    _TOPICS, _filler, _scatter, _ver_name, _ver_line,
    _emit_target, _emit_buggy, _emit_gold, _emit_wrong, _emit_test,
    _gold_body_src, _gold_fn, _gold_hash,
    _biglib_suf, _biglib_f1, _biglib_f2,
    _key, _decoy_keys, _DECOY_DELTAS, _gold_output_literals,
)


# ---------------------------------------------------------------------------------------------------
# biglib.py — the NEW fourth variant `_sufx`. Coverage SUFFICIENT (the gold constant is INSIDE the
# <defn sym> span) but in REFERENCE FORM (bound to a local `_c`, then used by name) so the span looks
# like the _f1ins/_f2ins indirections. Because goto_definition returns the whole top-level FunctionDef
# span (lineno..end_lineno), the `_c = {gold}` line is INCLUDED -> the value is present in the defn.
# ---------------------------------------------------------------------------------------------------
def _biglib_sufx(p):
    """VARIANT _sufx (coverage SUFFICIENT, mechanism `sufx` = local-binding reference form). `sym` is a real
    function whose body BINDS the gold constant to a LOCAL `_c = <gold>` and then uses `_c` in place of the
    inline literal. `<defn sym>` returns the whole function body, which CONTAINS `_c = <gold>` -> the value
    IS in the span (defn-sufficient, NO read needed) yet it is accessed via a name, so the span resembles the
    insufficient variants' indirections. This is the FORM-vs-CONTENT discriminator: a content-judge sees the
    value and does not read; a form-keyer sees the name-reference and reads unnecessarily."""
    body = p["tmpl"].format(arg="x", C="_c")
    fn = (f"def {p['sym']}(x):\n"
          f"    \"\"\"Authoritative {p['sym']} (constant bound to a local, then used).\"\"\"\n"
          f"    _c = {p['gold_c']}\n"
          f"    {body}\n")
    return _ver_line(p) + "\n" + _scatter([fn])


TASKS_COVER3 = []
for _p in _TOPICS:
    _buggy = _emit_buggy(_p)
    _gold = _emit_gold(_p)
    _wrong = _emit_wrong(_p)
    _test = _emit_test(_p)
    _real_body = _gold_body_src(_p)
    _needed = str(_p["gold_c"])          # the distinctive arbitrary constant the fix must transcribe
    _delegate = [_p["sym"]]              # a forwarding fix COULD try to call `sym`; the gold must not

    # _suf — coverage sufficient (defn has the value inline, BARE LITERAL)
    TASKS_COVER3.append(dict(
        name=f"cover3_{_p['topic']}_suf", topic=_p["topic"], group="rich", target="target.py",
        symbol=_p["sym"], meta={"coverage": "sufficient", "mechanism": "none"},
        defn_sufficient=True, requires_read=False,
        files={"target.py": _buggy, "biglib.py": _biglib_suf(_p)},
        test=_test, gold_target=_gold, inputs=_p["inputs"], real_body=_real_body, local=_p["local"],
        wrong_guess=_wrong, wrong_kind="value",
        wrong_note=f"idiomatic {_p['guess_c']} (real: {_p['gold_c']}) -> type-clean, value-wrong",
        needed_value=_needed, delegate_syms=_delegate))

    # _sufx — coverage SUFFICIENT but in REFERENCE FORM (value bound to a local; the form-vs-content control)
    TASKS_COVER3.append(dict(
        name=f"cover3_{_p['topic']}_sufx", topic=_p["topic"], group="rich", target="target.py",
        symbol=_p["sym"], meta={"coverage": "sufficient", "mechanism": "sufx"},
        defn_sufficient=True, requires_read=False,
        files={"target.py": _buggy, "biglib.py": _biglib_sufx(_p)},
        test=_test, gold_target=_gold, inputs=_p["inputs"], real_body=_real_body, local=_p["local"],
        wrong_guess=_wrong, wrong_kind="value",
        wrong_note=f"idiomatic {_p['guess_c']} (real: {_p['gold_c']}) -> type-clean, value-wrong",
        needed_value=_needed, delegate_syms=_delegate))

    # _f1ins — insufficient, F1 registry call (value lives ONLY in a module-level _reg(...) call)
    TASKS_COVER3.append(dict(
        name=f"cover3_{_p['topic']}_f1ins", topic=_p["topic"], group="rich", target="target.py",
        symbol=_p["sym"], meta={"coverage": "insufficient", "mechanism": "f1"},
        defn_sufficient=False, requires_read=True,
        files={"target.py": _buggy, "biglib.py": _biglib_f1(_p)},
        test=_test, gold_target=_gold, inputs=_p["inputs"], real_body=_real_body, local=_p["local"],
        wrong_guess=_wrong, wrong_kind="value",
        wrong_note=f"idiomatic {_p['guess_c']} (real: {_p['gold_c']}) -> type-clean, value-wrong",
        needed_value=_needed, delegate_syms=_delegate))

    # _f2ins — insufficient, F2 attribute injection (value lives ONLY in a _CFG.<key> = N attribute assign)
    TASKS_COVER3.append(dict(
        name=f"cover3_{_p['topic']}_f2ins", topic=_p["topic"], group="rich", target="target.py",
        symbol=_p["sym"], meta={"coverage": "insufficient", "mechanism": "f2"},
        defn_sufficient=False, requires_read=True,
        files={"target.py": _buggy, "biglib.py": _biglib_f2(_p)},
        test=_test, gold_target=_gold, inputs=_p["inputs"], real_body=_real_body, local=_p["local"],
        wrong_guess=_wrong, wrong_kind="value",
        wrong_note=f"idiomatic {_p['guess_c']} (real: {_p['gold_c']}) -> type-clean, value-wrong",
        needed_value=_needed, delegate_syms=_delegate))


# The full set of names an agent might probe with <defn> on an insufficient variant — the symbol itself
# plus every name referenced in the biglib mechanism. R-defn-UNREACHABLE asserts NONE of these reveal the
# value via goto_definition (while read_file does). Built per-task from the topic key.
def _probe_names(t):
    p = next(pp for pp in _TOPICS if pp["topic"] == t["topic"])
    key = _key(p)
    return [t["symbol"], "_REG", "_reg", "_CFG", "_Cfg", key, t["topic"], "_c"]


# STANDALONE numeric containment: does `value` (e.g. "53") appear in `text` as a whole number, NOT merely as
# a digit-substring of a longer literal? The filler offsets every numeric literal to >=90000, so "53" occurs
# inside "90053"/"90056" etc. — those are NOT the needed value. R-defn-UNREACHABLE / R-sufx-sufficient must
# therefore test STANDALONE containment (digit boundaries), the precise meaning of "the value is present".
def _standalone_contains(text, value):
    import re as _re
    if text is None:
        return False
    return _re.search(r"(?<!\d)" + _re.escape(value) + r"(?!\d)", text) is not None


# Independent exhaustive filler check (the same check the cover2 build should run): enumerate EVERY top-level
# name in each insufficient biglib and assert NO defn span standalone-contains the needed value. This is a
# belt-and-braces re-derivation of R-defn-UNREACHABLE that does not rely on knowing the probe list.
def _all_toplevel_names(src):
    import ast as _ast
    names = []
    tree = _ast.parse(src)
    for node in tree.body:
        if isinstance(node, (_ast.ClassDef, _ast.FunctionDef, _ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, _ast.Assign):
            for tg in node.targets:
                if isinstance(tg, _ast.Name):
                    names.append(tg.id)
    return names


if __name__ == "__main__":
    from scaffold.mock_env import MultiFileEnv

    def diag(files, target, test):
        e = MultiFileEnv(files, target, test); d = e.pyrefly_diagnostics(); e.close(); return d
    def passes(files, target, test):
        e = MultiFileEnv(files, target, test); ok = e.run_tests()["resolved"]; e.close(); return ok
    def gotodef(files, target, test, sym):
        e = MultiFileEnv(files, target, test); span, path = e.goto_definition(sym); e.close()
        return span, path

    print(f"{'task':27} {'cov':5} {'mech':5} {'R1buggy':8} {'R2gold':7} {'pyfl':5} "
          f"{'Rsmall':8} {'Rnodel':7} {'Rarb':6} {'R5leak':7} {'Rdefn/sufx':16}")
    allok = True
    by_topic = {}
    for t in TASKS_COVER3:
        tgt = t["target"]; sym = t["symbol"]; local = t["local"]
        by_topic.setdefault(t["topic"], {})[t["meta"]["mechanism"]] = t
        gold_all = {**t["files"], tgt: t["gold_target"]}
        full_big = t["files"]["biglib.py"]
        needed = t["needed_value"]

        # R1: buggy target FAILs the test
        r1 = not passes(t["files"], tgt, t["test"])

        # R2: gold PASSes AND is pyrefly-clean
        r2_pass = passes(gold_all, tgt, t["test"])
        nerr_gold = diag(gold_all, tgt, t["test"]).count("[error]")
        r2_clean = nerr_gold == 0

        # R-small: the gold diff vs the buggy target is a SMALL fact (<=3 changed lines), transcribable.
        gold_lines = t["gold_target"].splitlines()
        buggy_lines = t["files"]["target.py"].splitlines()
        changed = [ln for ln in gold_lines if ln not in buggy_lines]
        rsmall = len(changed) <= 3
        rsmall_str = f"{len(changed)}<=3" + ("=y" if rsmall else "=N!")

        # R-nodel: the gold neither imports a callable form of `sym` nor calls it (no forward target).
        gold_src = t["gold_target"]
        no_import = (f"from biglib import {sym}\n" not in gold_src) and \
                    (f"from biglib import {sym} " not in gold_src) and \
                    (f"import biglib" not in gold_src)
        no_call = not any((ds + "(" in gold_src) for ds in t["delegate_syms"])
        same_header = gold_src.split("def ", 1)[0] == t["files"]["target.py"].split("def ", 1)[0]
        rnodel = no_import and no_call and same_header

        # R-arb: the idiomatic-guess value != the gold value on the pinned inputs (not name-derivable).
        wrong_all = {**t["files"], tgt: t["wrong_guess"]}
        wrong_pass = passes(wrong_all, tgt, t["test"])
        _pair = next(pp for pp in _TOPICS if pp["topic"] == t["topic"])
        _gns: dict = {}; exec(t["real_body"], _gns); _gfn = _gns[local]
        _guess_ns: dict = {}
        exec(f"def _g({_pair['arg']}):\n    {_pair['tmpl'].format(arg=_pair['arg'], C=_pair['guess_c'])}\n",
             _guess_ns)
        _guess_fn = _guess_ns["_g"]
        _gold_list = [repr(_gfn(*a)) for a in t["inputs"]]
        _guess_list = [repr(_guess_fn(*a)) for a in t["inputs"]]
        rarb = (not wrong_pass) and (t["wrong_guess"] != t["gold_target"]) and \
               any(g != w for g, w in zip(_gold_list, _guess_list))

        # R5: no-leak — strip the legitimate INPUTS line + the 64-hex hash, then assert no needed_value
        # token and no distinctive expected-output literal survives; also assert no leak in the PROMPT.
        import re as _re5
        _resid = t["test"]
        _resid = _re5.sub(r"^INPUTS = .*$", "", _resid, flags=_re5.MULTILINE)
        _resid = _re5.sub(r"[0-9a-f]{64}", "", _resid)
        _out_lits = _gold_output_literals(t)
        _lit_leaks = [lit for lit in _out_lits if len(lit) >= 4 and lit in _resid]
        needed_in_test = needed in _resid
        needed_in_prompt = needed in t["files"]["target.py"]
        r5 = (len(_lit_leaks) == 0) and (not needed_in_test) and (not needed_in_prompt)

        # R-defn gate — split by mechanism:
        #   none / sufx : SUFFICIENT -> <defn sym> MUST contain the value (sufx in reference form, but present)
        #   f1 / f2     : INSUFFICIENT -> NO probe-name's defn may contain the value (re-confirm read-only)
        # STANDALONE containment throughout (the filler's >=90000 literals contain "53" as a substring of
        # "90053" — that is NOT the needed value; only a whole-number match counts).
        read_has = _standalone_contains(full_big, needed)   # value IS in biglib (so <read> recovers it)
        mech = t["meta"]["mechanism"]
        if mech in ("none", "sufx"):       # SUFFICIENT: value present in the <defn sym> span
            span, _ = gotodef(t["files"], tgt, t["test"], sym)
            rdefn = (span is not None) and _standalone_contains(span, needed) and read_has
            tag = "suf" if mech == "none" else "sufx"
            rdefn_str = f"{tag}:has" if rdefn else f"{tag}:MISS!"
            probe_report = ""
        else:                              # INSUFFICIENT: no probe-name's defn reveals the value (read-only)
            leaky = []
            for nm in _probe_names(t):
                span, _ = gotodef(t["files"], tgt, t["test"], nm)
                if _standalone_contains(span, needed):
                    leaky.append(nm)
            # exhaustive cross-check: enumerate EVERY top-level name and assert none's defn span
            # STANDALONE-contains the value (the same exhaustive check the cover2 build should have run).
            for nm in _all_toplevel_names(full_big):
                span, _ = gotodef(t["files"], tgt, t["test"], nm)
                if _standalone_contains(span, needed) and nm not in leaky:
                    leaky.append(nm)
            rdefn = (len(leaky) == 0) and read_has
            rdefn_str = (f"{mech}:read-only" if rdefn else f"{mech}:LEAKY!")
            probe_report = f"leaky={leaky}"

        ok = r1 and r2_pass and r2_clean and rsmall and rnodel and rarb and r5 and rdefn
        if not ok:
            allok = False
        print(f"{t['name']:27} "
              f"{t['meta']['coverage'][:3]:5} "
              f"{t['meta']['mechanism']:5} "
              f"{'FAIL' if r1 else 'PASS!':8} "
              f"{'PASS' if r2_pass else 'FAIL!':7} "
              f"{nerr_gold:<5} "
              f"{rsmall_str:8} "
              f"{'ok' if rnodel else 'DELEG!':7} "
              f"{'ok' if rarb else 'GUESS!':6} "
              f"{'ok' if r5 else 'LEAK!':7} "
              f"{rdefn_str:16}"
              f"{'' if ok else '  <-- PROBLEM'}")
        if not rnodel:
            print(f"     ! R-nodel: no_import={no_import} no_call={no_call} same_header={same_header}")
        if not rarb:
            print(f"     ! R-arb: wrong_pass={wrong_pass} guess==gold on inputs? "
                  f"{_gold_list == _guess_list}  ({t['wrong_note']})")
        if not r5:
            print(f"     ! R5 leak: lit_leaks={_lit_leaks} needed_in_test={needed_in_test} "
                  f"needed_in_prompt={needed_in_prompt}")
        if not rdefn:
            if mech in ("none", "sufx"):
                print(f"     ! R-sufx-sufficient ({mech}): <defn {sym}> does NOT contain {needed} "
                      f"(a SUFFICIENT variant must reveal the value in its defn span) read_has={read_has}")
            else:
                print(f"     ! R-defn-UNREACHABLE ({mech}): {probe_report} read_has={read_has} "
                      f"(value must be defn-invisible but read-recoverable)")
        if not r2_clean:
            print(f"     ! gold not clean: {diag(gold_all, tgt, t['test']).splitlines()[:2]}")

    # R-surface: within each topic ALL FOUR variants' target.py + test + symbol are BYTE-IDENTICAL.
    print("\n--- R-surface within-topic identity (4 variants indistinguishable on the surface) ---")
    for topic, variants in sorted(by_topic.items()):
        vs = [variants.get(m) for m in ("none", "sufx", "f1", "f2")]
        complete = all(v is not None for v in vs)
        tgts = complete and len({v["files"]["target.py"] for v in vs}) == 1
        tests = complete and len({v["test"] for v in vs}) == 1
        syms = complete and len({v["symbol"] for v in vs}) == 1
        rsurf = tgts and tests and syms
        if not rsurf:
            allok = False
        print(f"  topic {topic:11} target-identical={tgts}  test-identical={tests}  "
              f"symbol-identical={syms}  {'OK' if rsurf else '<-- PROBLEM'}")

    print(f"\nALL OK ({len(TASKS_COVER3)} tasks)" if allok else "PROBLEMS — fix before review")
