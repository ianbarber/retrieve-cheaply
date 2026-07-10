#!/usr/bin/env python3
"""Combine checker draft-calibration artifacts without rewriting their raw provenance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("drafts", nargs="+")
    parser.add_argument("--minimum", type=float, default=0.2)
    parser.add_argument("--maximum", type=float, default=0.7)
    parser.add_argument("--min-coherent", type=int, default=2)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    all_drafts = []
    models = set()
    for path in args.drafts:
        payload = json.loads(Path(path).read_text())
        models.add(payload.get("model"))
        drafts = payload["drafts"]
        all_drafts.extend(drafts)
        print(f"{path}: drafts={len(drafts)} submitted={sum(bool(d.get('draft_submitted')) for d in drafts)} "
              f"coherent={sum(bool(d.get('coherent')) for d in drafts)}")
    if len(models) != 1:
        raise ValueError(f"calibration artifacts use different models: {sorted(models)}")

    coherent = [draft for draft in all_drafts
                if draft.get("draft_submitted") and draft.get("coherent")]
    opportunities = [draft for draft in coherent if any(
        item["classification"] == "semantic" for item in draft["draft_diagnostics"]
    )]
    rate = len(opportunities) / len(coherent) if coherent else 0.0
    passed = len(coherent) >= args.min_coherent and args.minimum <= rate <= args.maximum
    print(f"combined model={models.pop()} drafts={len(all_drafts)} coherent={len(coherent)} "
          f"semantic-opportunity={len(opportunities)} rate={rate:.3f} gate_passed={passed}")
    return 0 if passed or not args.enforce else 2


if __name__ == "__main__":
    raise SystemExit(main())
