#!/usr/bin/env python3
"""Opportunity summaries and task-bootstrap contrasts for checker-paired-v1."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import random
import statistics
from pathlib import Path


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def summarize_rows(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}

    def mean(field: str) -> float:
        return statistics.mean(float(row[field]) for row in rows)

    tokens = [
        row.get("draft_in_tokens", 0) + row.get("draft_out_tokens", 0)
        + row["in_tokens"] + row["out_tokens"]
        for row in rows
    ]
    revision_tokens = [row["in_tokens"] + row["out_tokens"] for row in rows]
    accepted_defect = [bool(row["accepted"] and not row["type_clean"]) for row in rows]
    accepted_correct = [bool(row["accepted"] and row["held_pass"]) for row in rows]
    accepted_clean_correct = [
        bool(row["accepted"] and row["held_pass"] and row["type_clean"]) for row in rows
    ]
    return {
        "n": len(rows), "held_pass": mean("held_pass"),
        "type_clean": mean("type_clean"), "semantic_clean": mean("semantic_clean"),
        "accepted_type_clean": mean("accepted_type_clean"),
        "accepted_latent_defect": statistics.mean(accepted_defect),
        "accepted_correct": statistics.mean(accepted_correct),
        "accepted_type_clean_correct": statistics.mean(accepted_clean_correct),
        "abstained_or_rejected": mean("abstained_or_rejected"),
        "edited_diagnosed_location": mean("edited_diagnosed_location"),
        "diagnostics_eliminated": mean("diagnostics_eliminated"),
        "diagnostics_retained": mean("diagnostics_retained"),
        "diagnostics_introduced": mean("diagnostics_introduced"),
        "draft_plus_revision_tokens_mean": statistics.mean(tokens),
        "draft_plus_revision_tokens_median": statistics.median(tokens),
        "revision_tokens_mean": statistics.mean(revision_tokens),
        "revision_tokens_median": statistics.median(revision_tokens),
        "turns_mean": mean("turns"), "checker_latency_ms_mean": mean("checker_latency_ms"),
        "wall_sec_mean": mean("wall_sec"),
    }


def expected_cost_per_accepted_correct(
    drafts: list[dict], rows: list[dict], arm: str, opportunity_only: bool,
    bootstrap: int, seed: int, require_type_clean: bool = False,
) -> dict:
    selected = [draft for draft in drafts if not opportunity_only or (
        draft["coherent"] and any(
            item["classification"] == "semantic" for item in draft["draft_diagnostics"]
        )
    )]
    if not selected:
        return {"n_tasks": 0, "estimable": False, "reason": "no selected natural drafts"}
    by_draft: dict[str, list[dict]] = {}
    for row in rows:
        if row["arm"] == arm:
            by_draft.setdefault(row["draft_id"], []).append(row)
    missing = [
        draft["draft_id"] for draft in selected
        if draft["coherent"] and not by_draft.get(draft["draft_id"])
    ]
    if missing:
        return {
            "n_tasks": len({draft["task"] for draft in selected}),
            "estimable": False,
            "reason": "missing revision trajectories for coherent drafts",
            "missing_draft_ids": missing,
        }

    attempts: dict[str, list[tuple[float, float]]] = {}
    n_revisions = 0
    for draft in selected:
        draft_cost = float(draft.get("in_tokens", 0) + draft.get("out_tokens", 0))
        revisions = by_draft.get(draft["draft_id"], [])
        if not revisions:
            attempts.setdefault(draft["task"], []).append((draft_cost, 0.0))
            continue
        for row in revisions:
            n_revisions += 1
            success = bool(row["accepted"] and row["held_pass"])
            if require_type_clean:
                success = success and bool(row["type_clean"])
            cost = draft_cost + float(row["in_tokens"] + row["out_tokens"])
            attempts.setdefault(draft["task"], []).append((cost, float(success)))

    tasks = sorted(attempts)

    def estimate(sample: list[str]) -> tuple[float, float, float]:
        task_costs = [statistics.mean(cost for cost, _ in attempts[task]) for task in sample]
        task_success = [statistics.mean(success for _, success in attempts[task]) for task in sample]
        mean_cost = statistics.mean(task_costs)
        success_rate = statistics.mean(task_success)
        return mean_cost, success_rate, mean_cost / success_rate if success_rate else math.inf

    mean_cost, success_rate, expected = estimate(tasks)
    rng = random.Random(seed)
    samples = [estimate([rng.choice(tasks) for _ in tasks])[2] for _ in range(bootstrap)]
    return {
        "n_tasks": len(tasks), "n_natural_drafts": len(selected),
        "n_revision_trajectories": n_revisions, "estimable": True,
        "mean_draft_plus_revision_tokens": mean_cost,
        "accepted_correct_rate": success_rate,
        "expected_tokens_per_accepted_correct_patch": expected,
        "ci95": [quantile(samples, 0.025), quantile(samples, 0.975)],
        "success_requires_type_clean": require_type_clean,
    }


def paired_contrast(
    rows: list[dict], arm: str, field: str, opportunity_only: bool,
    bootstrap: int, seed: int,
) -> dict:
    selected = [row for row in rows if not opportunity_only or row["opportunity"]]
    by_arm: dict[str, dict[str, list[dict]]] = {}
    for row in selected:
        by_arm.setdefault(row["arm"], {}).setdefault(row["task"], []).append(row)
    if "control" not in by_arm or arm not in by_arm:
        return {"n_tasks": 0}
    control_grid = Counter(
        (row["draft_id"], row.get("seed")) for row in selected if row["arm"] == "control"
    )
    treatment_grid = Counter(
        (row["draft_id"], row.get("seed")) for row in selected if row["arm"] == arm
    )
    if control_grid != treatment_grid:
        return {
            "n_tasks": 0, "estimable": False,
            "reason": "incomplete paired draft/seed grid",
        }
    tasks = sorted(set(by_arm["control"]) & set(by_arm[arm]))
    if not tasks:
        return {"n_tasks": 0}

    def task_mean(which: str, task: str) -> float:
        return statistics.mean(float(row[field]) for row in by_arm[which][task])

    def effect(sample: list[str]) -> float:
        return statistics.mean(task_mean(arm, task) - task_mean("control", task) for task in sample)

    rng = random.Random(seed)
    samples = [effect([rng.choice(tasks) for _ in tasks]) for _ in range(bootstrap)]
    return {
        "n_tasks": len(tasks), "mean_delta": effect(tasks),
        "ci95": [quantile(samples, 0.025), quantile(samples, 0.975)],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drafts", required=True)
    parser.add_argument("--revisions")
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260710)
    args = parser.parse_args()
    payload = json.loads(Path(args.drafts).read_text())
    drafts = payload["drafts"]
    coherent = [draft for draft in drafts if draft["coherent"]]
    submitted = [draft for draft in drafts if draft.get("draft_submitted")]
    opportunities = [draft for draft in coherent if any(
        item["classification"] == "semantic" for item in draft["draft_diagnostics"]
    )]

    print(f"CHECKER DRAFT AUDIT: {payload.get('kind', 'unknown')}")
    print(f"drafts={len(drafts)} submitted={len(submitted)} coherent={len(coherent)} "
          f"semantic-opportunity={len(opportunities)}")
    print(f"unconditional opportunity rate={len(opportunities)/len(drafts):.3f}")
    if coherent:
        print(f"opportunity rate among coherent={len(opportunities)/len(coherent):.3f}")
    for draft in drafts:
        semantic = sum(item["classification"] == "semantic"
                       for item in draft["draft_diagnostics"])
        partial = len(draft["draft_diagnostics"]) - semantic
        print(f"  {draft['task']}: submitted={draft.get('draft_submitted')} "
              f"coherent={draft['coherent']} visible={draft['visible_pass']} "
              f"held={draft['held_pass']} semantic={semantic} syntax/partial={partial}")
    if not args.revisions:
        return

    rows = json.loads(Path(args.revisions).read_text())["rows"]
    print("\nPAIRED REVISIONS")
    for opportunity_only, subset in ((False, "unconditional"), (True, "checker-positive")):
        selected = [row for row in rows if not opportunity_only or row["opportunity"]]
        print(subset)
        for arm in sorted({row["arm"] for row in selected}):
            print(f"  {arm}: {json.dumps(summarize_rows([row for row in selected if row['arm'] == arm]), allow_nan=True)}")
            print("    deployment_cost: " + json.dumps(
                expected_cost_per_accepted_correct(
                    drafts, rows, arm, opportunity_only, args.bootstrap, args.seed
                ), allow_nan=True,
            ))
            print("    type_clean_deployment_cost: " + json.dumps(
                expected_cost_per_accepted_correct(
                    drafts, rows, arm, opportunity_only, args.bootstrap, args.seed,
                    require_type_clean=True,
                ), allow_nan=True,
            ))
        contrasts = {}
        for arm in sorted({row["arm"] for row in selected} - {"control"}):
            for field in ("held_pass", "accepted_type_clean"):
                contrasts[f"{arm}_minus_control_{field}"] = paired_contrast(
                    rows, arm, field, opportunity_only, args.bootstrap, args.seed
                )
        print(json.dumps(contrasts, indent=2, allow_nan=True))
    print("A null is not equivalence unless its task-bootstrap pass CI lies inside +/-0.10.")


if __name__ == "__main__":
    main()
