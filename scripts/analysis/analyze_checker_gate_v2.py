#!/usr/bin/env python3
"""Audit v6 repair/resubmit efficacy and matched-clean false rejection."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analysis.analyze_checker_paired import gate_pairing_audit


def analyze(drafts_payload: dict, revisions_payload: dict) -> dict:
    drafts = drafts_payload["drafts"]
    rows = revisions_payload["rows"]
    if drafts_payload.get("benchmark") != "checker-gate-v2":
        raise ValueError("checker-gate-v2 draft cohort required")
    if revisions_payload.get("protocol") != "checker-paired-v6":
        raise ValueError("checker-paired-v6 revisions required")
    expected = len(drafts) * 2
    if len(rows) != expected or {row["arm"] for row in rows} != {"control", "gate"}:
        raise ValueError(f"complete control/gate grid required: expected {expected} rows")
    if not all(row.get("first_done_model_generated") for row in rows):
        raise ValueError("every trajectory must have a verified model-generated completion")
    pairing = gate_pairing_audit(rows)
    if not pairing["valid"]:
        raise ValueError(f"invalid pre-gate pairing: {pairing['invalid_pairs']}")

    by_cell = {(row["draft_id"], row["arm"]): row for row in rows}
    defects = [draft for draft in drafts if draft.get("cohort") == "hidden_defect"]
    clean = [draft for draft in drafts if draft.get("cohort") == "clean_negative_control"]
    if not defects or len(defects) != len(clean):
        raise ValueError("matched non-empty defect and clean cohorts required")

    defect_pairs = [(by_cell[(draft["draft_id"], "control")],
                     by_cell[(draft["draft_id"], "gate")]) for draft in defects]
    clean_pairs = [(by_cell[(draft["draft_id"], "control")],
                    by_cell[(draft["draft_id"], "gate")]) for draft in clean]
    reached_bad = [
        (control, gate) for control, gate in defect_pairs
        if control["accepted"] and (not control["type_clean"] or not control["held_pass"])
    ]
    recovered = [
        (control, gate) for control, gate in reached_bad
        if gate["gate_rejections"]
        and gate["gate_acceptances"]
        and gate["done_attempts"] >= 2
        and gate["post_rejection_edits"] >= 1
        and gate["accepted_type_clean_correct"]
    ]

    def rate(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    def mean_tokens(pairs: list[tuple[dict, dict]], index: int) -> float:
        return statistics.mean(pair[index]["in_tokens"] + pair[index]["out_tokens"] for pair in pairs)

    return {
        "protocol": revisions_payload["protocol"],
        "model": revisions_payload.get("model"),
        "model_revision": revisions_payload.get("config", {}).get("revision"),
        "temperature": revisions_payload.get("config", {}).get("temperature"),
        "gate_pairing": pairing,
        "all_completions_model_generated": True,
        "defect_cohort": {
            "n": len(defect_pairs),
            "control_spontaneous_repair_before_submission": sum(
                control["accepted_type_clean_correct"] for control, _ in defect_pairs
            ),
            "bad_completion_opportunities_reached": len(reached_bad),
            "control_bad_completions_accepted": len(reached_bad),
            "gate_bad_completions_rejected": sum(
                bool(gate["gate_rejections"]) for _, gate in reached_bad
            ),
            "bad_completion_rejection_sensitivity": rate(
                sum(bool(gate["gate_rejections"]) for _, gate in reached_bad), len(reached_bad)
            ),
            "rejected_repaired_resubmitted_and_accepted_clean_correct": len(recovered),
            "conditional_accepted_recovery_rate": rate(len(recovered), len(reached_bad)),
            "control_accepted_type_clean_correct": sum(
                control["accepted_type_clean_correct"] for control, _ in defect_pairs
            ),
            "gate_accepted_type_clean_correct": sum(
                gate["accepted_type_clean_correct"] for _, gate in defect_pairs
            ),
            "control_revision_tokens_mean": mean_tokens(defect_pairs, 0),
            "gate_revision_tokens_mean": mean_tokens(defect_pairs, 1),
        },
        "clean_cohort": {
            "n": len(clean_pairs),
            "false_rejections": sum(bool(gate["gate_rejections"]) for _, gate in clean_pairs),
            "false_rejection_rate": rate(
                sum(bool(gate["gate_rejections"]) for _, gate in clean_pairs), len(clean_pairs)
            ),
            "first_submission_accepted": sum(
                bool(gate["gate_acceptances"] and not gate["gate_rejections"])
                for _, gate in clean_pairs
            ),
            "gate_accepted_type_clean_correct": sum(
                gate["accepted_type_clean_correct"] for _, gate in clean_pairs
            ),
            "control_revision_tokens_mean": mean_tokens(clean_pairs, 0),
            "gate_revision_tokens_mean": mean_tokens(clean_pairs, 1),
        },
        "all_workspaces": {
            "n": len(defect_pairs) + len(clean_pairs),
            "control_accepted_type_clean_correct": sum(
                control["accepted_type_clean_correct"]
                for control, _ in defect_pairs + clean_pairs
            ),
            "gate_accepted_type_clean_correct": sum(
                gate["accepted_type_clean_correct"]
                for _, gate in defect_pairs + clean_pairs
            ),
            "control_revision_tokens_mean": mean_tokens(defect_pairs + clean_pairs, 0),
            "gate_revision_tokens_mean": mean_tokens(defect_pairs + clean_pairs, 1),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drafts", default="runs/protocol/checker_gate_v2_pilot3.json")
    parser.add_argument("--revisions", default="runs/pilot/checker_gate_qwen35_27b_pilot3.json")
    args = parser.parse_args()
    result = analyze(
        json.loads(Path(args.drafts).read_text()),
        json.loads(Path(args.revisions).read_text()),
    )
    print("CHECKER GATE V2 MODEL-ORIGIN AND COHORT AUDIT")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
