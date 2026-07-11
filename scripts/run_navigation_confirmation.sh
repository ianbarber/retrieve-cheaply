#!/usr/bin/env bash
# Frozen local confirmation. Run once after the pilot protocol is accepted.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
MODEL="${MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct}"
REVISION="${REVISION:-c03e6d358207e414f1eca0bb1891e29f1db0e242}"
PILOT_RUN_ID="${PILOT_RUN_ID:?set PILOT_RUN_ID to the run tag of the accepted pilot}"
RUN_ID="${RUN_ID:-${PILOT_RUN_ID}}"
for value in "$PILOT_RUN_ID" "$RUN_ID"; do
  if [[ ! "$value" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "run IDs may contain only letters, digits, dot, underscore, and hyphen" >&2
    exit 64
  fi
done
PILOT_PREFIX="runs/pilot/navigation_v2_${PILOT_RUN_ID}"
OUT_PREFIX="runs/confirmation/navigation_v2_${RUN_ID}"
for out in "${OUT_PREFIX}_core.json" "${OUT_PREFIX}_deployment.json"; do
  if [ -e "$out" ]; then
    echo "refusing to overwrite frozen confirmation output: $out" >&2
    exit 2
  fi
done
MODEL="$MODEL" REVISION="$REVISION" PILOT_PREFIX="$PILOT_PREFIX" "$PY" - <<'PY'
from collections import Counter
import hashlib, json, os, pathlib, subprocess
from scaffold.tooling import find_pyrefly
root = pathlib.Path.cwd()
validation = json.loads((root / "runs/protocol/navigation_v2_confirmation_validation.json").read_text())
if not validation.get("passed") or validation.get("protocol") != "navigation-v2":
    raise SystemExit("frozen confirmation validation is absent or failed")
if (validation.get("split") != "confirmation" or len(validation.get("rows", [])) != 12
        or not all(row.get("passed") for row in validation.get("rows", []))):
    raise SystemExit("frozen confirmation task set is incomplete")
hashes = validation.get("protocol_source_sha256")
required = {
    "scripts/experiments/navigation_tasks.py", "scripts/experiments/run_navigation.py",
    "scripts/analysis/analyze_navigation.py", "scripts/run_navigation_pilot.sh",
    "scripts/run_navigation_confirmation.sh",
    "scaffold/stream_agent.py", "scaffold/real_env.py", "scaffold/tooling.py",
    "scripts/validate_pyrefly_lsp.py", "evidence/protocols.md",
}
if not hashes or not required.issubset(hashes):
    raise SystemExit("frozen confirmation artifact lacks complete protocol hashes")
for rel, expected in hashes.items():
    actual = hashlib.sha256((root / rel).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"frozen protocol hash mismatch: {rel}")
current_version = subprocess.run(
    [find_pyrefly(), "--version"], capture_output=True, text=True, check=True
).stdout.strip()
if current_version != validation.get("pyrefly", {}).get("version"):
    raise SystemExit("Pyrefly version differs from frozen manipulation check")
pilot_prefix = os.environ["PILOT_PREFIX"]
positive = json.loads((root / f"{pilot_prefix}_positive.json").read_text())
rows = positive.get("rows", [])
expected_tasks = {"nav_pilot_17011", "nav_pilot_17027"}
expected_positive_grid = Counter(
    (task, 0, "typed", "positive_control") for task in expected_tasks
)
positive_grid = Counter(
    (row.get("task"), row.get("seed"), row.get("variant"), row.get("arm")) for row in rows
)
if (positive.get("protocol") != "navigation-v2" or positive.get("model") != os.environ["MODEL"]
        or positive.get("config", {}).get("split") != "pilot"
        or positive.get("config", {}).get("cells") != "positive"
        or positive.get("config", {}).get("revision") != os.environ["REVISION"]
        or positive.get("config", {}).get("max_new") != 400
        or positive.get("config", {}).get("temperature") != 0
        or positive.get("config", {}).get("seeds") != 1
        or positive.get("config", {}).get("seed_start") != 0
        or positive.get("config", {}).get("max_turns") != 12
        or positive.get("config", {}).get("max_reads") != 12
        or positive.get("pyrefly", {}).get("version") != current_version
        or positive_grid != expected_positive_grid
        or not all(row.get("arm") == "positive_control" and row.get("variant") == "typed"
                   and row.get("held_out_pass") for row in rows)):
    raise SystemExit("positive-control artifact is absent or below the edit-competence floor")
behavior_sources = {
    "scripts/experiments/navigation_tasks.py", "scripts/experiments/run_navigation.py",
    "scaffold/stream_agent.py", "scaffold/real_env.py", "scaffold/tooling.py",
}
positive_hashes = positive.get("protocol_source_sha256", {})
if any(positive_hashes.get(rel) != hashes[rel] for rel in behavior_sources):
    raise SystemExit("positive-control behavior source differs from the frozen protocol")
span_control = json.loads((root / f"{pilot_prefix}_span_control.json").read_text())
span_rows = span_control.get("rows", [])
expected_span_grid = Counter(
    (task, 0, "typed", "semantic_span_control") for task in expected_tasks
)
span_grid = Counter(
    (row.get("task"), row.get("seed"), row.get("variant"), row.get("arm"))
    for row in span_rows
)
if (span_control.get("protocol") != "navigation-v2"
        or span_control.get("model") != os.environ["MODEL"]
        or span_control.get("config", {}).get("split") != "pilot"
        or span_control.get("config", {}).get("cells") != "span-control"
        or span_control.get("config", {}).get("revision") != os.environ["REVISION"]
        or span_control.get("config", {}).get("max_new") != 1000
        or span_control.get("config", {}).get("temperature") != 0
        or span_control.get("config", {}).get("seeds") != 1
        or span_control.get("config", {}).get("seed_start") != 0
        or span_control.get("config", {}).get("max_turns") != 12
        or span_control.get("config", {}).get("max_reads") != 12
        or span_control.get("pyrefly", {}).get("version") != current_version
        or span_grid != expected_span_grid
        or not all(row.get("arm") == "semantic_span_control" and row.get("variant") == "typed"
                   and row.get("semantic_payload_source") == "pristine_task_metadata"
                   and row.get("n_lsp") == 0 and row.get("server_latency_ms") == 0
                   and not row.get("server_errors")
                   and row.get("held_out_pass") for row in span_rows)):
    raise SystemExit("buggy-span actionability control is absent or below its 2/2 floor")
span_hashes = span_control.get("protocol_source_sha256", {})
if any(span_hashes.get(rel) != hashes[rel] for rel in behavior_sources):
    raise SystemExit("buggy-span control behavior source differs from the frozen protocol")
pilot = json.loads((root / f"{pilot_prefix}_all.json").read_text())
pilot_rows = pilot.get("rows", [])
expected_pilot_cells = {
    ("typed", "baseline"), ("typed", "semantic_auto"),
    ("erased", "baseline"), ("erased", "semantic_auto"),
    ("typed", "semantic_avail"), ("typed", "semantic_framed"),
}
expected_pilot_grid = Counter(
    (task, 0, variant, arm)
    for task in expected_tasks for variant, arm in expected_pilot_cells
)
pilot_grid = Counter(
    (row.get("task"), row.get("seed"), row.get("variant"), row.get("arm"))
    for row in pilot_rows
)
if (pilot.get("protocol") != "navigation-v2" or pilot.get("model") != os.environ["MODEL"]
        or pilot.get("config", {}).get("split") != "pilot"
        or pilot.get("config", {}).get("cells") != "all"
        or pilot.get("config", {}).get("revision") != os.environ["REVISION"]
        or pilot.get("config", {}).get("max_new") != 1000
        or pilot.get("config", {}).get("temperature") != 0
        or pilot.get("config", {}).get("seeds") != 1
        or pilot.get("config", {}).get("seed_start") != 0
        or pilot.get("config", {}).get("max_turns") != 12
        or pilot.get("config", {}).get("max_reads") != 12
        or pilot.get("pyrefly", {}).get("version") != current_version
        or pilot_grid != expected_pilot_grid):
    raise SystemExit("complete causal/deployment pilot artifact is absent")
pilot_hashes = pilot.get("protocol_source_sha256", {})
if any(pilot_hashes.get(rel) != hashes[rel] for rel in behavior_sources):
    raise SystemExit("causal pilot behavior source differs from the frozen protocol")
auto_payloads = {
    (row.get("task"), row.get("seed")): (
        row.get("semantic_payload_sha256"), row.get("semantic_supplied_path")
    )
    for row in pilot_rows
    if row.get("variant") == "typed" and row.get("arm") == "semantic_auto"
}
span_payloads = {
    (row.get("task"), row.get("seed")): (
        row.get("semantic_payload_sha256"), row.get("semantic_supplied_path")
    )
    for row in span_rows
}
if not auto_payloads or auto_payloads != span_payloads or any(
    payload_hash is None or path is None for payload_hash, path in auto_payloads.values()
):
    raise SystemExit("live automatic and metadata span-control payloads are not byte-identical")
core = [row for row in pilot_rows if row.get("arm") in {"baseline", "semantic_auto"}]
if not core or all(row.get("held_out_pass") for row in core) or not any(
    row.get("held_out_pass") for row in core
):
    raise SystemExit("pilot is uniformly ceilinged or floored; confirmation remains blocked")
print("frozen hashes and positive-control floor verified")
PY
"$PY" scripts/experiments/run_navigation.py "${OUT_PREFIX}_core.json" \
  --model "$MODEL" --revision "$REVISION" --split confirmation --cells core --temperature 0.7 --seeds 3 --gpu-only
"$PY" scripts/experiments/run_navigation.py "${OUT_PREFIX}_deployment.json" \
  --model "$MODEL" --revision "$REVISION" --split confirmation --cells deployment --temperature 0.7 --seeds 3 --gpu-only
