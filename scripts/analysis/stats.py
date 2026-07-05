#!/usr/bin/env python3
"""Reproduce the whole-file-read efficiency-recipe statistics from committed result JSONs.

This is the canonical reproducer for the controlled efficiency-recipe part of REPORT.md. The result is:
training a 7B coding agent on-policy to prefer cheap go-to-definition (`<defn>`) over
expensive whole-file `<read>` makes goto a several-x token win at maintained-or-better success in that
baseline. Each block below is labelled with its REPORT.md section and prints, per
arm: use-defn% / use-read% / resolved n/N (Wilson 95% CI) / mean input tokens, plus the
token ratio and the paired test (exact McNemar on success, exact two-sided sign test on
the paired token comparison). The TOKEN-MEAN METHOD is named in each block: the §4
headline / relabel-only / real-LSP / 27B-all and GRPO use a PLAIN per-arm mean over all
rows; the pilot and the isolation control use a MATCHED-OUTCOME mean (input tokens
averaged only over (task,seed) pairs both arms resolve).

This reproduces the weak-model (7B) on-policy training numbers; the tool-value ablation
and frontier validation are reproduced by run_toolablation.sh / run_frontier.sh and
scripts/analysis/effic_real_stats.py.

What it prints (report section  <-  repo file):
  §4 training headline (defn-sufficient, real resolver, n=48)
        3086 -> 688 (4.5x), 0->100% defn, succ 0.65->1.00 (McNemar b=17/c=0)
        PRE  = reallsp_base.json  group=='rich'   (== powered_retest_base.json rich)
        POST = reallsp_sft.json   group=='rich'   (== powered_retest_sft.json  rich)
  §4 relabel-only retest (the method in isolation, n=48): 3086 -> 724 (4.3x), 0->100%
        PRE  = effic_retest_base.json     POST = relabel2_retest.json
  §4 teacher-forced pilot, MATCHED-OUTCOME (lead-<defn>, 12 seeds, n=84): 2108 -> 675 (3.1x)
        PRE  = powered_retest_base.json rich (seeds 0-3) + powered_retest_base_x.json (4-11)
        POST = powered_retest_sft.json  rich (seeds 0-3) + powered_retest_sft_x.json  (4-11)
        success McNemar over all 144 pairs: b=57/c=3
  §3 isolation control, MATCHED-OUTCOME (read-trained vs defn-trained, n=40): 3191 -> 684 (4.7x)
        read-trained = effic_readtrained_retest.json (== effic_retest_sft.json)
        defn-trained = powered_retest_sft.json group=='rich'
  §2 real-LSP validation (live pyrefly daemon, n=24): 2894 -> 689, 0->100%, 0.58->1.00
        PRE  = lsp_base.json      POST = lsp_sft.json
  §4 boundary / non-degeneracy (read-required subset, n=24): read stays ~100%, succ 0.54->0.83
        PRE  = reallsp_base.json group=='readreq'   POST = reallsp_sft.json group=='readreq'
  Appendix A GRPO cost-RL corroboration: clean retest 86% defn / 663 tok / 100% solved (n=36)
        grpo_retest.json ; harvest trajectory grpo_harvest_0..4.json ; under-trained grpo_retest_round1.json
  Appendix B 27B transfer (n=24): 4058 -> 726 (5.5x at matched success), 0->100%, 0.96->1.00
        PRE  = 27b_base.json      POST = 27b_retest.json

Run:  python3 scripts/analysis/stats.py   (from the repo root)
"""
import json, math, os, statistics

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
A = lambda p: os.path.join(ROOT, "runs", "agent", p)


def load(path):
    """Return the row list for condition 'A'. `rows` is dict-keyed-by-condition or a flat list."""
    r = json.load(open(path))["rows"]
    return r["A"] if isinstance(r, dict) else r


def group(rows, g):
    return [r for r in rows if r.get("group") == g]


def used_defn(r):
    return r["n_lsp"] > 0


def used_read(r):
    return r["n_reads"] > 0


def wilson(n, t, z=1.96):
    if t == 0:
        return 0.0, 0.0
    p = n / t
    d = 1 + z * z / t
    c = (p + z * z / (2 * t)) / d
    h = z * math.sqrt(p * (1 - p) / t + z * z / (4 * t * t)) / d
    return c - h, c + h


def mcnemar(X, Y):
    """Exact two-sided McNemar on paired (task, seed) units (X=POST, Y=PRE convention here)."""
    ix = {(r["task"], r["seed"]): r["resolved"] for r in X}
    iy = {(r["task"], r["seed"]): r["resolved"] for r in Y}
    keys = [k for k in ix if k in iy]
    b = sum(1 for k in keys if ix[k] and not iy[k])
    c = sum(1 for k in keys if iy[k] and not ix[k])
    n = b + c
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)
    return b, c, p, len(keys)


def sign_test(pre_vals, post_vals):
    """Exact two-sided sign test on paired (pre, post) token values. Ties dropped.

    Returns (n_nonties, post_cheaper, post_worse, p). 'post_cheaper' = POST < PRE.
    """
    pairs = [(a, b) for a, b in zip(pre_vals, post_vals) if a != b]
    n = len(pairs)
    cheaper = sum(1 for a, b in pairs if b < a)  # POST strictly cheaper than PRE
    worse = n - cheaper
    k = min(cheaper, worse)
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return n, cheaper, worse, p


def arm(rows):
    n = len(rows)
    res = sum(r["resolved"] for r in rows)
    d = sum(1 for r in rows if used_defn(r))
    rd = sum(1 for r in rows if used_read(r))
    mt = statistics.mean(r["in_tokens"] for r in rows) if rows else 0.0
    return n, res, d, rd, mt


def print_arm(label, rows):
    n, res, d, rd, mt = arm(rows)
    lo, hi = wilson(res, n)
    print(f"  {label:14} defn {d/n:4.0%}  read {rd/n:4.0%}  "
          f"resolved {res:3}/{n} = {res/n:.3f} [{lo:.2f},{hi:.2f}]  mean_in_tok {mt:6.0f}")


def matched_outcome(PRE, POST):
    """Mean input tokens over (task,seed) pairs BOTH arms resolved. Returns dict of results."""
    ip = {(r["task"], r["seed"]): r for r in PRE}
    iq = {(r["task"], r["seed"]): r for r in POST}
    keys = [k for k in ip if k in iq and ip[k]["resolved"] and iq[k]["resolved"]]
    pre = [ip[k]["in_tokens"] for k in keys]
    post = [iq[k]["in_tokens"] for k in keys]
    a = statistics.mean(pre) if pre else 0.0
    b = statistics.mean(post) if post else 0.0
    nz, cheaper, worse, p = sign_test(pre, post)
    return dict(n=len(keys), pre=a, post=b, cheaper=cheaper, worse=worse, sign_p=p)


def paired_token_all(PRE, POST):
    """Paired sign test over ALL shared (task,seed) pairs (not outcome-conditioned)."""
    ip = {(r["task"], r["seed"]): r for r in PRE}
    iq = {(r["task"], r["seed"]): r for r in POST}
    keys = [k for k in ip if k in iq]
    pre = [ip[k]["in_tokens"] for k in keys]
    post = [iq[k]["in_tokens"] for k in keys]
    nz, cheaper, worse, p = sign_test(pre, post)
    return dict(n=len(keys), cheaper=cheaper, worse=worse, sign_p=p)


def check(label, got, paper, tol=2):
    flag = "MATCH" if abs(got - paper) <= tol else f"MISMATCH (got {got}, paper {paper})"
    print(f"      [{label}: {flag}]")


# ---------------------------------------------------------------------------
print("=" * 78)
print("STREAMS — WHOLE-FILE-READ EFFICIENCY RECIPE reproducer")
print("=" * 78)

# --- §4 HEADLINE: defn-sufficient, real AST resolver, plain per-arm token mean ---
print("\n== report §4 — training headline: defn-sufficient, real resolver (n=48) ==")
print("   token-mean method: PLAIN per-arm mean over all rows")
h_pre = group(load(A("reallsp_base.json")), "rich")
h_post = group(load(A("reallsp_sft.json")), "rich")
print_arm("PRE  (wild)", h_pre)
print_arm("POST (trained)", h_post)
_, _, _, _, mt_pre = arm(h_pre)
_, _, _, _, mt_post = arm(h_post)
print(f"  token ratio: {mt_pre/mt_post:.1f}x cheaper  ({mt_pre:.0f} -> {mt_post:.0f})")
pt = paired_token_all(h_pre, h_post)
print(f"  paired token sign test (all {pt['n']} pairs): POST cheaper {pt['cheaper']}/{pt['n']}, "
      f"worse {pt['worse']}, exact two-sided p={pt['sign_p']:.1e}")
b, c, p, n = mcnemar(h_post, h_pre)
print(f"  success McNemar (n={n} pairs): POST-only b={b}, PRE-only c={c}, exact p={p:.1e}")
check("tokens 3086->688", round(mt_pre), 3086); check("tokens 3086->688", round(mt_post), 688)
check("McNemar b=17/c=0", b, 17, tol=0)

# --- §4 relabel-only retest: the method in isolation ---
print("\n== report §4 — relabel-only retest (method in isolation, n=48) ==")
print("   token-mean method: PLAIN per-arm mean over all rows")
r_pre = load(A("effic_retest_base.json"))
r_post = load(A("relabel2_retest.json"))
print_arm("PRE  (wild)", r_pre)
print_arm("POST (relabel)", r_post)
_, _, _, _, rp = arm(r_pre)
_, _, _, _, rq = arm(r_post)
print(f"  token ratio: {rp/rq:.1f}x cheaper  ({rp:.0f} -> {rq:.0f})")
pt = paired_token_all(r_pre, r_post)
print(f"  paired token sign test (all {pt['n']} pairs): POST cheaper {pt['cheaper']}/{pt['n']}, "
      f"worse {pt['worse']}, exact two-sided p={pt['sign_p']:.1e}")
check("tokens 3086->724", round(rp), 3086); check("tokens 3086->724", round(rq), 724)

# --- §4 pilot, MATCHED-OUTCOME (teacher-forced lead-<defn>, 12 seeds) ---
print("\n== report §4 — teacher-forced pilot (lead-<defn>, 12 seeds), MATCHED-OUTCOME (n=84) ==")
print("   token-mean method: MATCHED-OUTCOME (mean input tokens over (task,seed) BOTH arms solve)")
p_pre = group(load(A("powered_retest_base.json")), "rich") + load(A("powered_retest_base_x.json"))
p_post = group(load(A("powered_retest_sft.json")), "rich") + load(A("powered_retest_sft_x.json"))
print_arm("PRE  (wild)", p_pre)
print_arm("POST (trained)", p_post)
mo = matched_outcome(p_pre, p_post)
print(f"  MATCHED-OUTCOME (n={mo['n']}): PRE {mo['pre']:.0f} -> POST {mo['post']:.0f} "
      f"= {mo['pre']/mo['post']:.1f}x cheaper; POST cheaper {mo['cheaper']}/{mo['n']}, "
      f"exact two-sided sign p={mo['sign_p']:.1e}")
b, c, p, n = mcnemar(p_post, p_pre)
print(f"  success McNemar (all {n} pairs): POST-only={b}, PRE-only={c}, exact p={p:.1e}  "
      f"(== the report's c=57/b=3, opposite POST/PRE label convention)")
check("matched 2108->675", round(mo['pre']), 2108); check("matched 2108->675", round(mo['post']), 675)
check("McNemar POST-only=57/PRE-only=3", b, 57, tol=0)

# --- §3 isolation control, MATCHED-OUTCOME (read-trained vs defn-trained) ---
print("\n== report §3 — isolation control: read-trained vs defn-trained, MATCHED-OUTCOME (n=40) ==")
print("   token-mean method: MATCHED-OUTCOME (over tasks BOTH trained models solve)")
read_trained = load(A("effic_readtrained_retest.json"))
defn_trained = group(load(A("powered_retest_sft.json")), "rich")
print_arm("read-trained", read_trained)
print_arm("defn-trained", defn_trained)
mo = matched_outcome(read_trained, defn_trained)
print(f"  MATCHED-OUTCOME (n={mo['n']}): read {mo['pre']:.0f} -> defn {mo['post']:.0f} "
      f"= {mo['pre']/mo['post']:.1f}x cheaper; defn cheaper {mo['cheaper']}/{mo['n']}, "
      f"exact two-sided sign p={mo['sign_p']:.1e}")
check("3191->684", round(mo['pre']), 3191); check("3191->684", round(mo['post']), 684)
check("sign p~6.8e-4", round(mo['sign_p'], 5), 0.00068, tol=0.0002)

# --- §5 / item-3 real-LSP headline: live pyrefly daemon ---
print("\n== report §2 — real-LSP validation (live pyrefly daemon, n=24) ==")
print("   token-mean method: PLAIN per-arm mean over all rows")
l_pre = load(A("lsp_base.json"))
l_post = load(A("lsp_sft.json"))
print_arm("PRE  (wild)", l_pre)
print_arm("POST (trained)", l_post)
_, lpres, _, _, lp = arm(l_pre)
_, lposts, _, _, lq = arm(l_post)
print(f"  token ratio: {lp/lq:.1f}x cheaper  ({lp:.0f} -> {lq:.0f})")
b, c, p, n = mcnemar(l_post, l_pre)
print(f"  success: {lpres}/{len(l_pre)} -> {lposts}/{len(l_post)}  "
      f"McNemar b={b}, c={c}, exact p={p:.1e}")
check("tokens 2894->689", round(lp), 2894); check("tokens 2894->689", round(lq), 689)

# --- §4 boundary / non-degeneracy: read-required subset ---
print("\n== report §4 — boundary / non-degeneracy (read-required subset, n=24) ==")
print("   read rate STAYS ~100%; success RISES; tokens go UP (correctly pays the read cost)")
b_pre = group(load(A("reallsp_base.json")), "readreq")
b_post = group(load(A("reallsp_sft.json")), "readreq")
print_arm("PRE  (wild)", b_pre)
print_arm("POST (trained)", b_post)
_, bps, _, _, bpt = arm(b_pre)
_, bqs, _, _, bqt = arm(b_post)
print(f"  success {bps}/{len(b_pre)}={bps/len(b_pre):.2f} -> {bqs}/{len(b_post)}={bqs/len(b_post):.2f}; "
      f"tokens {bpt:.0f} -> {bqt:.0f} (UP, as it should be)")
check("succ 0.54->0.83", round(bps/len(b_pre), 2), 0.54, tol=0.02)
check("succ 0.54->0.83", round(bqs/len(b_post), 2), 0.83, tol=0.02)

# --- Appendix A GRPO cost-RL corroboration ---
print("\n== report Appendix A — GRPO cost-RL corroboration ==")
print("   independent objective (token-cost reward) reaches the SFT operating point")
g = load(A("grpo_retest.json"))
ng, resg, dg, rdg, mtg = arm(g)
print(f"  clean retest (n={ng}): use-defn {dg}/{ng}={dg/ng:.0%}  resolved {resg}/{ng}={resg/ng:.0%}  "
      f"mean_in_tok {mtg:.0f}")
check("86% defn", round(dg / ng, 2), 0.86, tol=0.01)
check("663 tok", round(mtg), 663)
check("100% solved", resg, ng, tol=0)
print("  harvest trajectory (--force-lsp --relabel, n=72/round; defn% over solved rows):")
for i, lab in [(0, "round0/1 (wild) "), (2, "round2 (r1)     "),
               (3, "round3 (r1+2)   "), (4, "round4 (r1+2+3) ")]:
    h = load(A(f"grpo_harvest_{i}.json"))
    res = sum(r["resolved"] for r in h)
    d = sum(1 for r in h if r["resolved"] and used_defn(r))
    mt = statistics.mean(r["in_tokens"] for r in h)
    print(f"    {lab} resolved {res}/{len(h)}  defn-of-solved {d}/{res}={d/res:.0%}  mean_in_tok {mt:.0f}")
g1 = load(A("grpo_retest_round1.json"))
n1, r1res, d1, _, mt1 = arm(g1)
print(f"  under-trained 1-round retest (n={n1}): use-defn {d1}/{n1}={d1/n1:.0%} (regressed), "
      f"resolved {r1res}/{n1}, mean_in_tok {mt1:.0f}")

# --- §Limitations 27B transfer ---
print("\n== report Appendix B — 27B transfer (Qwen3.6-27B, n=24) ==")
print("   token-mean method: ALL-rows for PRE; MATCHED-SUCCESS for the 5.5x ratio")
q_pre = load(A("27b_base.json"))
q_post = load(A("27b_retest.json"))
print_arm("PRE  (wild 27B)", q_pre)
print_arm("POST (relabel)", q_post)
_, qps, _, _, qp = arm(q_pre)
_, qqs, _, _, qq = arm(q_post)
mo = matched_outcome(q_pre, q_post)
print(f"  all-rows tokens {qp:.0f} -> {qq:.0f}; MATCHED-SUCCESS (n={mo['n']}): "
      f"{mo['pre']:.0f} -> {mo['post']:.0f} = {mo['pre']/mo['post']:.1f}x cheaper")
print(f"  success {qps}/{len(q_pre)}={qps/len(q_pre):.2f} -> {qqs}/{len(q_post)}={qqs/len(q_post):.2f}")
check("tokens 4058->726", round(qp), 4058); check("tokens 4058->726", round(qq), 726)
check("matched 5.5x", round(mo['pre'] / mo['post'], 1), 5.5, tol=0.2)

print("\n" + "=" * 78)
print("Done. Every [MATCH] above confirms the printed number equals REPORT.md (within rounding).")
print("=" * 78)
