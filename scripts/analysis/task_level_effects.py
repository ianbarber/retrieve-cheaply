#!/usr/bin/env python3
"""Task-level effects with rollout seeds treated as nested repetitions."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from pathlib import Path


def load(path: str) -> list[dict]:
    payload = json.loads(Path(path).read_text())
    rows = payload.get("rows", payload)
    return rows["A"] if isinstance(rows, dict) else rows


def tokens(row: dict) -> float:
    return float(row.get("in_tokens", row.get("prompt_tokens", row.get("in_toks", 0))))


def task_rows(rows: list[dict]) -> dict[str, list[dict]]:
    out = {}
    for row in rows:
        out.setdefault(row["task"], []).append(row)
    return out


def quantile(values: list[float], p: float) -> float:
    values = sorted(values)
    if not values:
        return math.nan
    index = (len(values) - 1) * p
    low, high = math.floor(index), math.ceil(index)
    if low == high:
        return values[low]
    return values[low] * (high - index) + values[high] * (index - low)


def metrics(base: dict[str, list[dict]], treatment: dict[str, list[dict]], tasks: list[str]) -> dict:
    def arm(grouped, task, field):
        rows = grouped[task]
        if field == "success":
            return statistics.mean(bool(row["resolved"]) for row in rows)
        if field == "tokens":
            return statistics.mean(tokens(row) for row in rows)
        successes = sum(bool(row["resolved"]) for row in rows)
        return sum(tokens(row) for row in rows) / successes if successes else math.inf

    success_delta = statistics.mean(arm(treatment, task, "success") - arm(base, task, "success")
                                    for task in tasks)
    base_tokens = statistics.mean(arm(base, task, "tokens") for task in tasks)
    treatment_tokens = statistics.mean(arm(treatment, task, "tokens") for task in tasks)
    ratios = [arm(base, task, "tokens") / max(arm(treatment, task, "tokens"), 1) for task in tasks]
    finite_base = [arm(base, task, "cost_success") for task in tasks
                   if math.isfinite(arm(base, task, "cost_success"))]
    finite_treatment = [arm(treatment, task, "cost_success") for task in tasks
                        if math.isfinite(arm(treatment, task, "cost_success"))]
    return {
        "success_delta": success_delta,
        "base_mean_tokens": base_tokens,
        "treatment_mean_tokens": treatment_tokens,
        "mean_task_token_ratio": statistics.mean(ratios),
        "median_task_token_ratio": statistics.median(ratios),
        "base_mean_cost_per_success": statistics.mean(finite_base) if finite_base else math.inf,
        "treatment_mean_cost_per_success": statistics.mean(finite_treatment) if finite_treatment else math.inf,
        "tasks_treatment_cheaper": sum(ratio > 1 for ratio in ratios),
        "n_tasks": len(tasks),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--treatment", required=True)
    parser.add_argument("--label", default="paired arms")
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260710)
    args = parser.parse_args()
    base, treatment = task_rows(load(args.base)), task_rows(load(args.treatment))
    tasks = sorted(set(base) & set(treatment))
    observed = metrics(base, treatment, tasks)
    rng = random.Random(args.seed)
    samples = [metrics(base, treatment, [rng.choice(tasks) for _ in tasks])
               for _ in range(args.bootstrap)]
    for key in ("success_delta", "mean_task_token_ratio"):
        values = [sample[key] for sample in samples]
        observed[key + "_ci95"] = [quantile(values, 0.025), quantile(values, 0.975)]
    print(args.label)
    print(json.dumps(observed, indent=2, allow_nan=True))


if __name__ == "__main__":
    main()
