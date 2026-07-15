#!/usr/bin/env python3
"""Combine disjoint retrieval-paired-v1 shards and report task-level effects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, median
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analysis.analyze_retrieval_paired import _paired


IDENTITY_CONFIG = (
    "model", "revision", "temperature", "seeds", "seed_start",
    "max_new", "max_turns", "max_reads", "live_lsp",
)


def load_suite(paths: list[Path]) -> tuple[list[dict], dict]:
    payloads = [json.loads(path.read_text()) for path in paths]
    if not payloads:
        raise ValueError("at least one retrieval result is required")
    reference = payloads[0]
    for path, payload in zip(paths[1:], payloads[1:]):
        if payload.get("protocol") != "retrieval-paired-v1":
            raise ValueError(f"unexpected protocol in {path}")
        if payload.get("model") != reference.get("model"):
            raise ValueError(f"model mismatch in {path}")
        for field in IDENTITY_CONFIG:
            if payload.get("config", {}).get(field) != reference.get("config", {}).get(field):
                raise ValueError(f"config mismatch for {field} in {path}")

    rows = [row for payload in payloads for row in payload["rows"]]
    cells = [(row["task"], row["arm"], row["seed"]) for row in rows]
    if len(cells) != len(set(cells)):
        raise ValueError("retrieval shards contain duplicate task/arm/seed cells")
    return rows, reference


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", nargs="+", type=Path)
    args = parser.parse_args()
    rows, reference = load_suite(args.results)

    print("RETRIEVAL-PAIRED SUITE")
    print(json.dumps({
        "protocol": reference["protocol"], "model": reference["model"],
        "revision": reference["config"].get("revision"),
        "artifacts": [str(path) for path in args.results],
        "tasks": len({row["task"] for row in rows}), "cells": len(rows),
    }, indent=2))
    for arm in ("whole", "text", "definition"):
        selected = [row for row in rows if row["arm"] == arm]
        if not selected:
            continue
        print(f"{arm}: " + json.dumps({
            "pass": f"{sum(row['resolved'] for row in selected)}/{len(selected)}",
            "mean_total_tokens": mean(row["total_tokens"] for row in selected),
            "median_total_tokens": median(row["total_tokens"] for row in selected),
            "mean_retrieval_response_chars": mean(
                row["retrieval_response_chars"] for row in selected
            ),
            "whole_reads": sum(row["n_whole_read"] for row in selected),
            "ranged_reads": sum(row["n_ranged_read"] for row in selected),
            "definition_calls": sum(row["n_definition"] for row in selected),
            "definition_then_defining_file_read": sum(
                row["definition_then_defining_file_read"] for row in selected
            ),
        }))
    print("text/definition: " + json.dumps(_paired(rows, "text", "definition")))
    print("whole/definition: " + json.dumps(_paired(rows, "whole", "definition")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
