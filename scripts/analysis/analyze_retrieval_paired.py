#!/usr/bin/env python3
"""Task-level analysis for retrieval-paired-v1."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from statistics import mean, median


def _task_cells(rows: list[dict], arm: str) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["arm"] == arm:
            grouped[row["task"]].append(row)
    return {
        task: {
            "success": mean(float(row["resolved"]) for row in task_rows),
            "tokens": mean(row["total_tokens"] for row in task_rows),
        }
        for task, task_rows in grouped.items()
    }


def _paired(rows: list[dict], baseline: str, treatment: str, draws: int = 20000) -> dict:
    left, right = _task_cells(rows, baseline), _task_cells(rows, treatment)
    tasks = sorted(set(left) & set(right))
    matched = [task for task in tasks if left[task]["success"] > 0 and right[task]["success"] > 0]
    if not matched:
        return {"n_tasks": len(tasks), "n_matched_success": 0, "estimable": False}

    def ratio(sample: list[str]) -> float:
        return mean(left[task]["tokens"] for task in sample) / mean(
            right[task]["tokens"] for task in sample
        )

    rng = random.Random(1701)
    boot = sorted(ratio([rng.choice(matched) for _ in matched]) for _ in range(draws))
    lo = boot[int(0.025 * draws)]
    hi = boot[min(draws - 1, int(0.975 * draws))]
    return {
        "n_tasks": len(tasks), "n_matched_success": len(matched),
        "baseline_mean_tokens": mean(left[task]["tokens"] for task in matched),
        "treatment_mean_tokens": mean(right[task]["tokens"] for task in matched),
        "ratio_baseline_over_treatment": ratio(matched), "task_bootstrap_ci95": [lo, hi],
        "tasks_treatment_cheaper": sum(
            right[task]["tokens"] < left[task]["tokens"] for task in matched
        ),
    }


def _fmt(value: float) -> str:
    return "nan" if math.isnan(value) else f"{value:.1f}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result")
    args = parser.parse_args()
    payload = json.load(open(args.result))
    rows = payload["rows"]
    print("RETRIEVAL INTERFACE OUTCOMES")
    print(f"{'arm':12} {'pass':>8} {'tokens':>10} {'grep':>7} {'range':>7} "
          f"{'whole':>7} {'defn':>7} {'chars':>9} {'reread':>8}")
    for arm in ("whole", "text", "definition"):
        selected = [row for row in rows if row["arm"] == arm]
        if not selected:
            continue
        print(f"{arm:12} {sum(row['resolved'] for row in selected):>3}/{len(selected):<4} "
              f"{_fmt(mean(row['total_tokens'] for row in selected)):>10} "
              f"{mean(row['n_grep'] for row in selected):>7.1f} "
              f"{mean(row['n_ranged_read'] for row in selected):>7.1f} "
              f"{mean(row['n_whole_read'] for row in selected):>7.1f} "
              f"{mean(row['n_definition'] for row in selected):>7.1f} "
              f"{mean(row['retrieval_response_chars'] for row in selected):>9.0f} "
              f"{mean(row['definition_then_defining_file_read'] for row in selected):>8.2f}")
    print("\nPAIRED TASK-LEVEL MATCHED-SUCCESS CONTRASTS")
    for baseline in ("whole", "text"):
        result = _paired(rows, baseline, "definition")
        print(f"{baseline}/definition: {json.dumps(result, sort_keys=True)}")
    definition = [row for row in rows if row["arm"] == "definition"]
    if definition:
        print("\nDEFINITION SUBSTITUTION")
        print(json.dumps({
            "elected": sum(bool(row["n_definition"]) for row in definition),
            "rows": len(definition),
            "definition_then_defining_file_read": sum(
                row["definition_then_defining_file_read"] for row in definition
            ),
            "median_total_tokens": median(row["total_tokens"] for row in definition),
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
