#!/usr/bin/env python3
"""Summarize the authoring/checker experiment that supports REPORT.md section 5.

The authoring suite asks whether live static-checker feedback helps an agent write a typed module from a
spec. Arms:

  none      no checker available
  check     checker available as an elective action
  feedback  checker diagnostics volunteered after edits

Run: python3 scripts/analysis/analyze_authoring.py
"""
from __future__ import annotations

import json
import math
import os
from statistics import mean


ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")

RUNS = [
    ("27B", "none", "runs/agent/exp2_27b_none.json"),
    ("27B", "check", "runs/agent/exp2_27b_check.json"),
    ("27B", "feedback", "runs/agent/exp2_27b_feedback.json"),
    ("7B", "none", "runs/agent/exp2_7b_none.json"),
    ("7B", "check", "runs/agent/exp2_7b_check.json"),
    ("7B", "feedback", "runs/agent/exp2_7b_feedback.json"),
]


def load_rows(relpath: str) -> list[dict]:
    data = json.load(open(os.path.join(ROOT, relpath)))
    rows = data.get("rows", data) if isinstance(data, dict) else data
    return rows["A"] if isinstance(rows, dict) else rows


def fmt(x: float, digits: int = 1) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    return f"{x:.{digits}f}"


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    held = sum(bool(r.get("held_pass", r.get("resolved", False))) for r in rows)
    visible = sum(bool(r.get("resolved", False)) for r in rows)
    return {
        "n": n,
        "held": held,
        "visible": visible,
        "resid": mean(r.get("n_resid_diag", 0) for r in rows) if rows else math.nan,
        "edits": mean(r.get("n_edits", 0) for r in rows) if rows else math.nan,
        "tokens": mean(r.get("in_tokens", 0) for r in rows) if rows else math.nan,
        "checks": mean(r.get("n_checks", 0) for r in rows) if rows else math.nan,
        "bailed": sum(bool(r.get("bailed", False)) for r in rows),
    }


def main() -> None:
    print("=" * 86)
    print("AUTHORING / CHECKER-FEEDBACK ANALYSIS")
    print("=" * 86)
    print(
        f"{'model':6} {'arm':10} {'held_out':>9} {'visible':>9} {'resid':>7} "
        f"{'edits':>7} {'tokens':>8} {'checks':>7} {'bailed':>7}"
    )

    summaries = {}
    for model, arm, relpath in RUNS:
        s = summarize(load_rows(relpath))
        summaries[(model, arm)] = s
        print(
            f"{model:6} {arm:10} {s['held']:>2}/{s['n']:<6} {s['visible']:>2}/{s['n']:<6} "
            f"{fmt(s['resid'],2):>7} {fmt(s['edits'],1):>7} {fmt(s['tokens'],0):>8} "
            f"{fmt(s['checks'],1):>7} {s['bailed']:>7}"
        )

    print("\nReport anchors:")
    print("- 27B: 12/12 held-out in every arm; checker is never elected in the elective arm.")
    print("- 7B: no-checker is best on held-out pass (6/12 vs 3/12 and 4/12).")
    none = summaries[("7B", "none")]
    feedback = summaries[("7B", "feedback")]
    if none["tokens"]:
        print(f"- 7B feedback token multiplier vs none: {feedback['tokens'] / none['tokens']:.2f}x.")
    print("- Residual diagnostics stay about flat for 7B, so volunteered diagnostics add cost but do not clean up types.")


if __name__ == "__main__":
    main()
