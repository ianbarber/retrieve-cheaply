#!/usr/bin/env bash
# Frozen local confirmation. Run once after the pilot protocol is accepted.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
MODEL="${MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct}"
REVISION="${REVISION:-c03e6d358207e414f1eca0bb1891e29f1db0e242}"
for out in runs/confirmation/navigation_v2_core.json runs/confirmation/navigation_v2_deployment.json; do
  if [ -e "$out" ]; then
    echo "refusing to overwrite frozen confirmation output: $out" >&2
    exit 2
  fi
done
MODEL="$MODEL" REVISION="$REVISION" "$PY" - <<'PY'
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
positive = json.loads((root / "runs/pilot/navigation_v2_positive.json").read_text())
rows = positive.get("rows", [])
expected_tasks = {"nav_pilot_17011", "nav_pilot_17027"}
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
        or {row.get("task") for row in rows} != expected_tasks
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
span_control = json.loads((root / "runs/pilot/navigation_v2_span_control.json").read_text())
span_rows = span_control.get("rows", [])
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
        or {row.get("task") for row in span_rows} != expected_tasks
        or not all(row.get("arm") == "semantic_span_control" and row.get("variant") == "typed"
                   and row.get("semantic_payload_source") == "pristine_task_metadata"
                   and row.get("n_lsp") == 0 and row.get("server_latency_ms") == 0
                   and row.get("held_out_pass") for row in span_rows)):
    raise SystemExit("buggy-span actionability control is absent or below its 2/2 floor")
span_hashes = span_control.get("protocol_source_sha256", {})
if any(span_hashes.get(rel) != hashes[rel] for rel in behavior_sources):
    raise SystemExit("buggy-span control behavior source differs from the frozen protocol")
pilot = json.loads((root / "runs/pilot/navigation_v2_all.json").read_text())
pilot_rows = pilot.get("rows", [])
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
        or len(pilot_rows) != 12
        or {row.get("task") for row in pilot_rows} != expected_tasks):
    raise SystemExit("complete causal/deployment pilot artifact is absent")
pilot_hashes = pilot.get("protocol_source_sha256", {})
if any(pilot_hashes.get(rel) != hashes[rel] for rel in behavior_sources):
    raise SystemExit("causal pilot behavior source differs from the frozen protocol")
auto_payloads = {
    (row.get("task"), row.get("seed")): row.get("semantic_payload_sha256")
    for row in pilot_rows
    if row.get("variant") == "typed" and row.get("arm") == "semantic_auto"
}
span_payloads = {
    (row.get("task"), row.get("seed")): row.get("semantic_payload_sha256")
    for row in span_rows
}
if not auto_payloads or auto_payloads != span_payloads or any(
    payload is None for payload in auto_payloads.values()
):
    raise SystemExit("live automatic and metadata span-control payloads are not byte-identical")
core = [row for row in pilot_rows if row.get("arm") in {"baseline", "semantic_auto"}]
if not core or all(row.get("held_out_pass") for row in core) or not any(
    row.get("held_out_pass") for row in core
):
    raise SystemExit("pilot is uniformly ceilinged or floored; confirmation remains blocked")
print("frozen hashes and positive-control floor verified")
PY
"$PY" scripts/experiments/run_navigation.py runs/confirmation/navigation_v2_core.json \
  --model "$MODEL" --revision "$REVISION" --split confirmation --cells core --temperature 0.7 --seeds 3 --gpu-only
"$PY" scripts/experiments/run_navigation.py runs/confirmation/navigation_v2_deployment.json \
  --model "$MODEL" --revision "$REVISION" --split confirmation --cells deployment --temperature 0.7 --seeds 3 --gpu-only
