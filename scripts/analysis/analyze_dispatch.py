#!/usr/bin/env python3
"""Summarize the dispatch/goto experiments that support REPORT.md section 3.5.

The dispatch runs test whether a type-aware go-to-definition beats a realistic textual baseline
(`grep` plus reads) when a method name is overridden on many classes. The important quantity is the
paired token ratio on tasks both arms solve:

    ratio = mean(grep_base input tokens) / mean(defn arm input tokens)

A ratio above 1 means goto was cheaper; a ratio near 1 means neutral.

Run: python3 scripts/analysis/analyze_dispatch.py
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from statistics import mean


ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")

RUNS = [
    ("27B annotated", "runs/realbench/dispatch/local_Qwen3.6-27B.json"),
    ("27B stripped", "runs/realbench/dispatch/local_Qwen3.6-27B_stripped.json"),
    ("27B indirection", "runs/realbench/dispatch/local_Qwen3.6-27B_indirection.json"),
    ("7B annotated", "runs/realbench/dispatch/local_Qwen2.5-Coder-7B-Instruct.json"),
]
CONDS = ("grep_base", "defn_avail", "defn_prompt")


def load_rows(relpath: str) -> list[dict]:
    path = os.path.join(ROOT, relpath)
    data = json.load(open(path))
    return data.get("rows", data) if isinstance(data, dict) else data


def fmt(x: float, digits: int = 0) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    return f"{x:.{digits}f}"


def summarize(rows: list[dict], cond: str) -> dict:
    sub = [r for r in rows if r["cond"] == cond]
    solved = [r for r in sub if r["resolved"]]
    return {
        "n": len(sub),
        "resolved": len(solved),
        "mean_all": mean(r["in_toks"] for r in sub) if sub else math.nan,
        "mean_solved": mean(r["in_toks"] for r in solved) if solved else math.nan,
        "grep": mean(r["n_grep"] for r in sub) if sub else math.nan,
        "defn": mean(r["n_defn"] for r in sub) if sub else math.nan,
        "whole": mean(r["n_read_whole"] for r in sub) if sub else math.nan,
        "ranged": mean(r["n_read_ranged"] for r in sub) if sub else math.nan,
    }


def paired_ratio(rows: list[dict], other_cond: str) -> dict:
    by_cond = defaultdict(dict)
    for r in rows:
        by_cond[r["cond"]][(r["task"], r["seed"])] = r
    base = by_cond["grep_base"]
    other = by_cond[other_cond]
    keys = sorted(k for k in base if k in other and base[k]["resolved"] and other[k]["resolved"])
    if not keys:
        return {"n": 0, "base": math.nan, "other": math.nan, "ratio": math.nan}
    base_mean = mean(base[k]["in_toks"] for k in keys)
    other_mean = mean(other[k]["in_toks"] for k in keys)
    return {"n": len(keys), "base": base_mean, "other": other_mean, "ratio": base_mean / other_mean}


def main() -> None:
    print("=" * 88)
    print("DISPATCH / SEMANTIC-GOTO ANALYSIS")
    print("=" * 88)
    print("ratio = grep_base mean tokens / defn-arm mean tokens on tasks both arms solve")

    for label, relpath in RUNS:
        rows = load_rows(relpath)
        print("\n" + label)
        print("-" * len(label))
        print(
            f"{'condition':12} {'resolved':>9} {'mean_all':>9} {'mean_solved':>12} "
            f"{'grep':>6} {'defn':>6} {'whole':>7} {'ranged':>7}"
        )
        for cond in CONDS:
            s = summarize(rows, cond)
            print(
                f"{cond:12} {s['resolved']:>2}/{s['n']:<6} {fmt(s['mean_all']):>9} "
                f"{fmt(s['mean_solved']):>12} {fmt(s['grep'],1):>6} {fmt(s['defn'],1):>6} "
                f"{fmt(s['whole'],1):>7} {fmt(s['ranged'],1):>7}"
            )
        for cond in ("defn_avail", "defn_prompt"):
            p = paired_ratio(rows, cond)
            if p["n"]:
                print(
                    f"paired grep_base/{cond}: n={p['n']}  "
                    f"{fmt(p['base'])}->{fmt(p['other'])}  ratio={fmt(p['ratio'], 3)}"
                )
            else:
                print(f"paired grep_base/{cond}: n=0  no matched solved pairs")

    print("\nReport anchors:")
    print("- 27B annotated: 15/15 solved in grep_base and defn_prompt; ratio ~= 1.04.")
    print("- 27B stripped/indirection: grep_base solved-token means stay flat at about 1436, 1429, 1465.")
    print("- 7B annotated: sparse solved sets, no stable matched-success efficiency claim.")


if __name__ == "__main__":
    main()
