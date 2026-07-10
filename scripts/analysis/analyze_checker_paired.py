#!/usr/bin/env python3
"""Opportunity summaries and task-bootstrap contrasts for checker-paired-v1."""

from __future__ import annotations

import argparse
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

    tokens = [row["in_tokens"] + row["out_tokens"] for row in rows]
    accepted_defect = [bool(row["accepted"] and not row["type_clean"]) for row in rows]
    return {
        "n": len(rows), "held_pass": mean("held_pass"),
        "type_clean": mean("type_clean"), "semantic_clean": mean("semantic_clean"),
        "accepted_type_clean": mean("accepted_type_clean"),
        "accepted_latent_defect": statistics.mean(accepted_defect),
        "abstained_or_rejected": mean("abstained_or_rejected"),
        "edited_diagnosed_location": mean("edited_diagnosed_location"),
        "diagnostics_eliminated": mean("diagnostics_eliminated"),
        "diagnostics_retained": mean("diagnostics_retained"),
        "diagnostics_introduced": mean("diagnostics_introduced"),
        "tokens_mean": statistics.mean(tokens), "tokens_median": statistics.median(tokens),
        "turns_mean": mean("turns"), "checker_latency_ms_mean": mean("checker_latency_ms"),
        "wall_sec_mean": mean("wall_sec"),
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
