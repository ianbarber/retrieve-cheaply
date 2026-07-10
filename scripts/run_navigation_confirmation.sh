#!/usr/bin/env bash
# Frozen local confirmation. Run once after the pilot protocol is accepted.
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
MODEL="${MODEL:-Qwen/Qwen2.5-Coder-7B-Instruct}"
for out in runs/confirmation/navigation_core.json runs/confirmation/navigation_deployment.json; do
  if [ -e "$out" ]; then
    echo "refusing to overwrite frozen confirmation output: $out" >&2
    exit 2
  fi
done
MODEL="$MODEL" "$PY" - <<'PY'
import hashlib, json, os, pathlib, subprocess
from scaffold.tooling import find_pyrefly
root = pathlib.Path.cwd()
validation = json.loads((root / "runs/protocol/navigation_confirmation_validation.json").read_text())
if not validation.get("passed") or validation.get("protocol") != "navigation-v1":
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
    "scripts/validate_pyrefly_lsp.py",
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
positive = json.loads((root / "runs/pilot/navigation_positive.json").read_text())
rows = positive.get("rows", [])
expected_tasks = {"nav_pilot_17011", "nav_pilot_17027"}
if (positive.get("protocol") != "navigation-v1" or positive.get("model") != os.environ["MODEL"]
        or positive.get("config", {}).get("split") != "pilot"
        or positive.get("config", {}).get("cells") != "positive"
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
pilot = json.loads((root / "runs/pilot/navigation_all.json").read_text())
pilot_rows = pilot.get("rows", [])
if (pilot.get("protocol") != "navigation-v1" or pilot.get("model") != os.environ["MODEL"]
        or pilot.get("config", {}).get("split") != "pilot"
        or pilot.get("config", {}).get("cells") != "all"
        or len(pilot_rows) != 12
        or {row.get("task") for row in pilot_rows} != expected_tasks):
    raise SystemExit("complete causal/deployment pilot artifact is absent")
core = [row for row in pilot_rows if row.get("arm") in {"baseline", "semantic_auto"}]
if not core or all(row.get("held_out_pass") for row in core) or not any(
    row.get("held_out_pass") for row in core
):
    raise SystemExit("pilot is uniformly ceilinged or floored; confirmation remains blocked")
print("frozen hashes and positive-control floor verified")
PY
"$PY" scripts/experiments/run_navigation.py runs/confirmation/navigation_core.json \
  --model "$MODEL" --split confirmation --cells core --temperature 0.7 --seeds 3 --gpu-only
"$PY" scripts/experiments/run_navigation.py runs/confirmation/navigation_deployment.json \
  --model "$MODEL" --split confirmation --cells deployment --temperature 0.7 --seeds 3 --gpu-only
