#!/usr/bin/env python3
"""Analysis for the effic-real ZERO-SHOT TRANSFER eval.

Question: does the synthetic-trained cheap-<defn> preference (effic_lora_powered) generalize to
REAL library code? Compares a BASE run vs a TRAINED run on the effic_real suite, paired by
(task, seed). Reports:
  - per-arm: success (overall + by group), %used-<defn>, %used-<read>, %retrieved, mean in_tokens
  - matched-outcome token reduction on (task,seed) pairs BOTH arms solve (paired sign test)
  - paired exact McNemar on success
  - NON-GUESSABILITY: among BASE successes, how many retrieved (read/defn) vs solved cold (guessed)

Exact tests only (binomial), no scipy dependency.

Usage:
  python scripts/analysis/effic_real_stats.py --base runs/agent/er_base.json --trained runs/agent/er_trained.json
"""
import argparse
import json
import statistics
from math import comb


def binom_two_sided(k, n, p=0.5):
    """Exact two-sided binomial p-value for k successes in n (point-null p)."""
    if n == 0:
        return 1.0
    pmf = [comb(n, i) * p**i * (1 - p)**(n - i) for i in range(n + 1)]
    obs = pmf[k]
    return min(1.0, sum(x for x in pmf if x <= obs + 1e-12))


def used_defn(row):
    if row.get("n_defn", 0) > 0:
        return True
    return any((e.get("type") == "defn" or e.get("t") == "defn") and e.get("found")
               for e in row.get("events", row.get("trace", [])))


def used_findrefs(row):
    if row.get("n_findrefs", 0) > 0:
        return True
    return any((e.get("type") == "findrefs" or e.get("t") == "findrefs")
               and (e.get("hits") or 0) > 0 for e in row.get("events", row.get("trace", [])))


def retrieved(row):
    return row.get("n_reads", row.get("n_read", 0)) > 0 or used_defn(row) or used_findrefs(row)


def input_tokens(row):
    return row.get("in_tokens", row.get("prompt_tokens", 0))


def load(path):
    d = json.load(open(path))
    rows = d.get("rows", {})
    rows = rows["A"] if isinstance(rows, dict) else rows
    return {(r["task"], r["seed"]): r for r in rows}, rows


def arm_summary(rows, label):
    n = len(rows)
    res = sum(bool(r["resolved"]) for r in rows)
    d = sum(used_defn(r) for r in rows)
    rd = sum(r.get("n_reads", r.get("n_read", 0)) > 0 for r in rows)
    ret = sum(retrieved(r) for r in rows)
    tokens = [input_tokens(r) for r in rows]
    intok = sum(tokens) / max(n, 1)
    bygrp = {}
    for g in ("rich", "plain", "control"):
        sub = [r for r in rows if r["group"] == g]
        if sub:
            bygrp[g] = f"{sum(bool(r['resolved']) for r in sub)}/{len(sub)}"
    print(f"\n[{label}] n={n}")
    print(f"  success      {res}/{n} = {res/max(n,1):.3f}   by_group={bygrp}")
    print(f"  %used <defn> {d}/{n} = {d/max(n,1):.3f}")
    print(f"  %used <read> {rd}/{n} = {rd/max(n,1):.3f}")
    print(f"  %retrieved   {ret}/{n} = {ret/max(n,1):.3f}")
    print(f"  mean in_tok  {intok:.0f}")
    print(f"  median in_tok {statistics.median(tokens):.0f}" if tokens else "  median in_tok -")
    return dict(n=n, success=res, mean_in=intok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--trained", required=True)
    ap.add_argument("--label", default="paired retrieval arms")
    A = ap.parse_args()
    base, base_rows = load(A.base)
    trained, trained_rows = load(A.trained)

    print("=" * 70)
    print(f"effic-real paired analysis: {A.label}")
    print("=" * 70)
    arm_summary(base_rows, "BASE")
    arm_summary(trained_rows, "TRAINED")

    keys = sorted(set(base) & set(trained))
    print(f"\n--- paired on {len(keys)} (task,seed) cells ---")

    # McNemar on success
    b = sum(1 for k in keys if base[k]["resolved"] and not trained[k]["resolved"])  # base only
    c = sum(1 for k in keys if trained[k]["resolved"] and not base[k]["resolved"])  # trained only
    both = sum(1 for k in keys if base[k]["resolved"] and trained[k]["resolved"])
    neither = sum(1 for k in keys if not base[k]["resolved"] and not trained[k]["resolved"])
    p_mcn = binom_two_sided(min(b, c), b + c)
    print(f"\nMcNemar success:  both={both} neither={neither} base_only(b)={b} trained_only(c)={c}")
    print(f"  exact two-sided p = {p_mcn:.4g}   ({'trained>base' if c>b else 'base>trained' if b>c else 'tie'})")

    # Matched-outcome token reduction on pairs BOTH solve
    matched = [k for k in keys if base[k]["resolved"] and trained[k]["resolved"]]
    if matched:
        bt = sum(input_tokens(base[k]) for k in matched) / len(matched)
        tt = sum(input_tokens(trained[k]) for k in matched) / len(matched)
        non_ties = [k for k in matched if input_tokens(trained[k]) != input_tokens(base[k])]
        cheaper = sum(1 for k in non_ties if input_tokens(trained[k]) < input_tokens(base[k]))
        p_sign = binom_two_sided(cheaper, len(non_ties))
        print(f"\nMatched-outcome tokens (n={len(matched)} both-solve cells):")
        print(f"  base mean in_tok    {bt:.0f}")
        print(f"  trained mean in_tok {tt:.0f}")
        print(f"  reduction           {bt/max(tt,1):.2f}x")
        print(f"  trained cheaper in  {cheaper}/{len(non_ties)} non-tied cells "
              f"({len(matched)-len(non_ties)} ties)   sign-test p = {p_sign:.4g}")

        # Seeds are nested repetitions: average within task before describing
        # the direction across the task generalization units.
        tasks = sorted({task for task, _seed in matched})
        task_deltas = []
        for task in tasks:
            task_keys = [k for k in matched if k[0] == task]
            bmean = statistics.mean(input_tokens(base[k]) for k in task_keys)
            tmean = statistics.mean(input_tokens(trained[k]) for k in task_keys)
            task_deltas.append(bmean - tmean)
        task_non_ties = [value for value in task_deltas if value != 0]
        task_better = sum(value > 0 for value in task_non_ties)
        task_p = binom_two_sided(task_better, len(task_non_ties))
        print(f"  task-level direction {task_better}/{len(task_non_ties)} non-tied tasks "
              f"favor trained; exact sign p={task_p:.4g}")
    else:
        print("\nNo (task,seed) cells solved by BOTH arms — cannot do matched-outcome tokens.")

    # Non-guessability: among BASE successes, did they retrieve or guess cold?
    base_succ = [r for r in base_rows if r["resolved"]]
    cold = [r for r in base_succ if not retrieved(r)]
    print(f"\nNon-guessability (BASE successes): {len(base_succ)} solved; "
          f"{len(base_succ)-len(cold)} retrieved, {len(cold)} solved COLD (no read/defn = guessed)")
    if cold:
        from collections import Counter
        cc = Counter(r["task"] for r in cold)
        print(f"  guessable tasks (base solved cold): {dict(cc)}")

    # Per-task transfer table
    print("\n--- per-task (trained %defn / success ; base %read / success) ---")
    tasks = sorted(set(r["task"] for r in base_rows) | set(r["task"] for r in trained_rows))
    for t in tasks:
        tr = [r for r in trained_rows if r["task"] == t]
        ba = [r for r in base_rows if r["task"] == t]
        def pct(rows, f): return f"{sum(f(r) for r in rows)}/{len(rows)}" if rows else "-"
        grp = (tr or ba)[0]["group"]
        print(f"  {t:26} [{grp:7}]  TRAINED defn {pct(tr,used_defn):5} succ {pct(tr,lambda r:r['resolved']):5}"
              f"   |  BASE read {pct(ba,lambda r:r.get('n_reads',r.get('n_read',0))>0):5} "
              f"succ {pct(ba,lambda r:r['resolved']):5}")


if __name__ == "__main__":
    main()
