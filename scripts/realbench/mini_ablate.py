#!/usr/bin/env python3
"""Two-arm LSP ablation on a SWE-bench task, driven by mini-swe-agent.

The agent is the stock mini-swe-agent (bash-only, tool-calling) running inside the task's
SWE-bench Docker container. We ablate ONE thing:

  off : stock mini-swe-agent. It reads code with cat/sed, edits, runs pytest.
  on  : identical, PLUS a `codenav` CLI injected into the container and advertised in the
        prompt as the cheap way to retrieve a definition/references instead of reading a
        whole file. (codenav = scripts/realbench/codenav.py, base64-injected via the
        env_startup_command hook; see scripts/realbench/swe_loader.py for the task source.)

Per arm we record: exit_status, whether the agent actually CALLED codenav, input tokens
(sum of prompt_tokens over model calls) and peak context, model calls, and the submitted
patch. Patches are written to <out>/preds_<arm>.json in swebench format for scoring with
scripts/realbench/score.py. Model text vs behaviour is our efficiency signal: at matched
success, the `on` arm should retrieve the cross-file symbol for far fewer input tokens.

  python scripts/realbench/mini_ablate.py --instance django__django-11138 \
      --model openrouter/anthropic/claude-sonnet-4.5 --arms off,on --step-limit 40

Local (Qwen via an OpenAI-compatible endpoint): pass --model openrouter/... OR set
--model-class litellm_textbased with a base_url in model kwargs; see docs/real_repo_progress.md.
"""
import os
import sys
import json
import copy
import time
import base64
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Emulate x86 SWE-bench images on this ARM64 host (validated in docs/real_repo_progress.md).
os.environ.setdefault("DOCKER_DEFAULT_PLATFORM", "linux/amd64")
os.environ.setdefault("MSWEA_COST_TRACKING", "ignore_errors")  # OpenRouter has no litellm price map
os.environ.setdefault("MSWEA_SILENT_STARTUP", "1")

CODENAV_SRC = (ROOT / "scripts/realbench/codenav.py").read_text()
CODENAV_B64 = base64.b64encode(CODENAV_SRC.encode()).decode()

# Written into the container once, before the agent starts. Pure stdlib; uses the testbed python.
INJECT_CMD = (
    "mkdir -p /opt && printf '%s' " + CODENAV_B64 + " | base64 -d > /opt/codenav.py && "
    "printf '#!/usr/bin/env bash\\nexec \"${CODENAV_PY:-python}\" /opt/codenav.py \"$@\"\\n' "
    "> /usr/local/bin/codenav && chmod +x /usr/local/bin/codenav && codenav --selfcheck"
)

CODENAV_PARA = """

    ## Retrieval tool (available in this environment)

    A `codenav` command is installed. It is the CHEAP way to inspect a symbol defined in
    another file, returning only the relevant lines instead of the whole file:

    - `codenav defn SYMBOL` - go-to-definition: prints the definition span (a function,
      `Class`, or `Class.method`) with its file and line. Prefer this over `cat`-ing a large
      file just to see one definition.
    - `codenav refs SYMBOL` - find-references: lists where a symbol is used across the repo.

    When you need a cross-file definition or the call sites of a symbol, use `codenav`; it is
    cheaper than reading the file. Read whole files only when you actually need broad context.
"""


def _sum_tokens(messages):
    """Sum prompt_tokens over model responses (total input processed = what you pay), and
    the peak single-call prompt_tokens (final context size)."""
    total_in = total_out = peak_in = 0
    for m in messages:
        usage = (((m.get("extra") or {}).get("response") or {}).get("usage")) or {}
        pin = usage.get("prompt_tokens") or 0
        pout = usage.get("completion_tokens") or 0
        total_in += pin
        total_out += pout
        peak_in = max(peak_in, pin)
    return total_in, total_out, peak_in


def _codenav_calls(messages):
    """Count executed bash actions that invoked codenav (behavioural election signal)."""
    n_defn = n_refs = n_calls = 0
    for m in messages:
        for a in (m.get("extra") or {}).get("actions", []) or []:
            cmd = a.get("command", "") if isinstance(a, dict) else ""
            if "codenav" in cmd:
                n_calls += 1
                if "codenav defn" in cmd:
                    n_defn += 1
                if "codenav refs" in cmd:
                    n_refs += 1
    return {"codenav_calls": n_calls, "codenav_defn": n_defn, "codenav_refs": n_refs}


def run_arm(arm, instance, base_cfg, model_name, model_class, out_dir, step_limit, wall_seconds):
    from minisweagent.models import get_model
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.run.benchmarks.swebench import get_sb_environment

    iid = instance["instance_id"]
    cfg = copy.deepcopy(base_cfg)
    cfg.setdefault("agent", {})
    cfg.setdefault("model", {})
    cfg.setdefault("environment", {})
    cfg["agent"]["step_limit"] = step_limit
    cfg["agent"]["cost_limit"] = 0.0                 # cost is untracked on OpenRouter; bound by steps/time
    cfg["agent"]["wall_time_limit_seconds"] = wall_seconds
    cfg["agent"]["output_path"] = str(out_dir / f"{iid}.{arm}.traj.json")
    cfg["model"]["model_name"] = model_name
    if model_class:
        cfg["model"]["model_class"] = model_class
    cfg["model"].setdefault("model_kwargs", {})
    cfg["model"]["model_kwargs"].setdefault("temperature", 0.0)
    cfg["model"]["cost_tracking"] = "ignore_errors"

    if arm == "on":
        cfg.setdefault("run", {})["env_startup_command"] = INJECT_CMD
        cfg["agent"]["instance_template"] = cfg["agent"]["instance_template"] + CODENAV_PARA

    t0 = time.time()
    env = get_sb_environment(cfg, instance)           # starts container, runs the inject on 'on'
    model = get_model(config=cfg["model"])
    agent = DefaultAgent(model, env, **cfg["agent"])
    exit_status, patch = "", ""
    try:
        info = agent.run(instance["problem_statement"])
        exit_status = info.get("exit_status", "")
        patch = info.get("submission", "") or ""
    except Exception as e:
        exit_status = f"driver_error:{type(e).__name__}"
        sys.stderr.write(f"[{arm}] error: {e}\n")
    finally:
        try:
            env.cleanup()
        except Exception:
            pass

    tin, tout, peak = _sum_tokens(agent.messages)
    rec = {"arm": arm, "instance_id": iid, "exit_status": exit_status,
           "input_tokens": tin, "output_tokens": tout, "peak_context": peak,
           "model_calls": agent.n_calls, "wall_s": round(time.time() - t0, 1),
           "patch_bytes": len(patch), **_codenav_calls(agent.messages)}
    # swebench-format predictions for scoring
    preds = {iid: {"model_name_or_path": f"mini-{arm}", "instance_id": iid, "model_patch": patch}}
    (out_dir / f"preds_{arm}.json").write_text(json.dumps(preds, indent=2))
    (out_dir / f"summary_{arm}.json").write_text(json.dumps(rec, indent=2))
    print(f"[{arm}] exit={exit_status} calls={rec['model_calls']} in_tok={tin} peak={peak} "
          f"codenav={rec['codenav_calls']}(defn={rec['codenav_defn']}) patch={rec['patch_bytes']}B "
          f"wall={rec['wall_s']}s", flush=True)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True, help="SWE-bench Verified instance_id")
    ap.add_argument("--model", default="openrouter/anthropic/claude-sonnet-4.5")
    ap.add_argument("--model-class", default=None, help="mini-swe model class (e.g. litellm_textbased)")
    ap.add_argument("--arms", default="off,on")
    ap.add_argument("--step-limit", type=int, default=40)
    ap.add_argument("--wall-seconds", type=int, default=1800)
    ap.add_argument("--out", default=None, help="output dir (default runs/realbench/ablate/<iid>)")
    args = ap.parse_args()

    # OpenRouter key (same source as scripts/api_agent.py): .orkey or env.
    if "openrouter/" in args.model and not os.environ.get("OPENROUTER_API_KEY"):
        for p in (ROOT / ".orkey", Path(".orkey")):
            if p.is_file():
                os.environ["OPENROUTER_API_KEY"] = p.read_text().strip()
                break

    from datasets import load_dataset
    from minisweagent.config import builtin_config_dir, get_config_from_spec
    from minisweagent.run.benchmarks.swebench import get_swebench_docker_image_name

    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    inst = {r["instance_id"]: r for r in ds}.get(args.instance)
    if inst is None:
        raise SystemExit(f"instance {args.instance} not in SWE-bench Verified")

    out_dir = Path(args.out) if args.out else ROOT / "runs/realbench/ablate" / args.instance
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pre-pull the image with a generous timeout so container start (pull_timeout=120s) never races.
    image = get_swebench_docker_image_name(inst)
    print(f"[pull] {image}", flush=True)
    subprocess.run(["docker", "pull", image], timeout=1800,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    base_cfg = get_config_from_spec(str(builtin_config_dir / "benchmarks" / "swebench.yaml"))

    recs = []
    for arm in [a.strip() for a in args.arms.split(",") if a.strip()]:
        recs.append(run_arm(arm, inst, base_cfg, args.model, args.model_class,
                            out_dir, args.step_limit, args.wall_seconds))

    (out_dir / "ablate_summary.json").write_text(json.dumps({"instance_id": args.instance,
                                                             "model": args.model, "arms": recs}, indent=2))
    print("\n=== ablation summary (score preds_*.json with scripts/realbench/score.py) ===")
    for r in recs:
        print(f"  {r['arm']:3} in_tok={r['input_tokens']:>8} peak={r['peak_context']:>7} "
              f"calls={r['model_calls']:>3} codenav_defn={r['codenav_defn']} "
              f"exit={r['exit_status']} patch={r['patch_bytes']}B")
    if len(recs) == 2 and recs[0]["input_tokens"] and recs[1]["input_tokens"]:
        off = next(r for r in recs if r["arm"] == "off")
        on = next(r for r in recs if r["arm"] == "on")
        if on["input_tokens"]:
            print(f"  input-token ratio off/on = {off['input_tokens']/on['input_tokens']:.2f}x")


if __name__ == "__main__":
    main()
