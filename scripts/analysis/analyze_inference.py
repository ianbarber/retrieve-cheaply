#!/usr/bin/env python3
"""Describe the historical gapd2 checker ceiling without interpreting it as equivalence."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARMS = {
    "nocheck": "hinted/no-checker",
    "realistic": "unhinted/no-checker",
    "withcheck": "hinted/elective-checker",
}
RUNS = [
    (model, label, ROOT / f"runs/agent/gd2_{model}_{suffix}.json")
    for model in ("deepseek", "sonnet45")
    for suffix, label in ARMS.items()
]


def main() -> None:
    print("HISTORICAL HELD-OUT INFERENCE CHECKER ARMS")
    for model, arm, path in RUNS:
        payload = json.loads(path.read_text())
        rows = payload["rows"]
        rich = [row for row in rows if row.get("group") == "rich"]
        solved = sum(bool(row["resolved"]) for row in rich)
        checks = sum(row.get("n_check", row.get("n_checks", 0)) for row in rich)
        print(f"{model:10} {arm:26}: {solved}/{len(rich)} held-out; checker calls={checks}")
    print("All cells are at behavioral ceiling; natural-draft checker opportunity was not measured.")


if __name__ == "__main__":
    main()
