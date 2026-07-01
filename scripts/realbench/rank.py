#!/usr/bin/env python3
"""Merge the per-repo selection scans (runs/realbench/scan/*.json) into one ranked candidate pool for
hand-auditing. Admissible tasks (S1 & S2 & S3) are ranked by score, with the strongest cross-file
dependency shown per task.

  python scripts/realbench/rank.py [--out runs/realbench/candidates.json]
"""
import os
import sys
import glob
import json
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-dir", default="runs/realbench/scan")
    ap.add_argument("--out", default="runs/realbench/candidates.json")
    args = ap.parse_args()

    rows = []
    for f in sorted(glob.glob(os.path.join(ROOT, args.scan_dir, "*.json"))):
        rows += json.load(open(f)).get("rows", [])
    # de-dup by instance_id (a task could be scanned twice)
    by_id = {r["instance_id"]: r for r in rows if "instance_id" in r}
    rows = list(by_id.values())

    adm = [r for r in rows if r.get("admissible")]
    adm.sort(key=lambda r: (-r["score"], r["instance_id"]))
    from collections import Counter
    per_repo = Counter(r["repo"] for r in adm)
    errs = [r for r in rows if "error" in r]

    out = {"scanned": len(rows), "n_admissible": len(adm), "n_errors": len(errs),
           "admissible_per_repo": dict(per_repo), "candidates": adm}
    outp = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    json.dump(out, open(outp, "w"), indent=2)

    print(f"scanned={len(rows)}  admissible={len(adm)}  errors={len(errs)}")
    print("admissible per repo:", dict(per_repo))
    print(f"\ntop candidates (hand-audit from here):")
    print(f"  {'score':>5}  {'instance_id':34}  cross-file symbol -> def file [lines]")
    for r in adm[:25]:
        x = r["xdeps"][0] if r["xdeps"] else {}
        edited = r["edited_files"][0] if r["edited_files"] else ""
        print(f"  {r['score']:>5}  {r['instance_id']:34}  "
              f"{x.get('symbol','')}({x.get('hint_kind','')}) -> {x.get('def_file','')} "
              f"[{x.get('def_lines')}L], edits {edited} (F2P={r['n_f2p']})")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
