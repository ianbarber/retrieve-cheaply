# Streams — when a language server pays off for a coding agent

Code, result data, and reproduction scripts for the tech report [PAPER.md](./PAPER.md):

> *Making a Language Server Pay Off for a Coding Agent: Redundant Information, Retrieval
> Efficiency That Must Be Elicited*

A coding agent that can read files does not need a language server for **information** — it
reads the source and derives types and references itself. The residual value is **retrieval
efficiency**: a go-to-definition *action* returns one symbol instead of a whole file. That
saving is real (3.7–5.3× fewer input tokens at matched success), but only under three
conditions, and getting the agent to use the cheap action is free for capable models and
trainable for weak ones.

## The result

1. **Information is redundant.** Across correction, completeness, navigation, prevention,
   scale, and type inference, handing a self-retrieving agent the language server's
   information never raises pass@1. At the frontier a `check_types()` tool is solved 16/16
   with and without it, and `claude-sonnet-4.5` never calls it.

2. **Efficiency is real, under three conditions.** A `<defn>` action cuts input tokens
   3.7–5.3× at matched success, iff **(1)** retrieval is required (the API cannot be guessed),
   **(2)** the counterfactual is a whole-file read, and **(3)** the agent elects the cheap
   action. The tool-value ablation (same model, toggle the tool) isolates this: removing
   `<defn>` from a 27B raises mean input tokens 1260→4644 at the same ceiling success; in the
   tool-calling modality `claude-sonnet-4.5` goes 6,014→23,811 (4.0×) and
   `deepseek-chat-v3.1` 9,325→49,142 (5.3×).

3. **Election is capability-gated.** A 7B uses `<defn>` 2% by default and ignores a prompt
   telling it to prefer the action; one round of on-policy training takes it to 100% use and
   4.5× fewer tokens. A capable model needs no training — framing `<defn>` in the system
   prompt as cheaper than a read moves an untrained 27B to 88–95% use and a frontier model to
   100%.

## The recipe

To make a language server pay off in an agentic loop:

1. **Expose go-to-definition as an action**, not diagnostics as context. The information in
   diagnostics, references, and completion is redundant for a self-retrieving agent.
2. **Frame it as cheaper than a read** in the system prompt. Capable models then elect it for
   free.
3. **If the model is weak enough to ignore the framing, train the preference on-policy:** roll
   out the agent, rewrite its `<read>` of a resolvable symbol to `<defn sym>`, and fine-tune on
   the relabeled trajectories (one DAgger round). Prompting and offline cloning do not work for
   the weak model; on-policy training does.
4. **Mix in tasks that genuinely need a full read**, so the agent learns when the cheap action
   suffices. The trained agent still reads 100% on read-required tasks.

## Reproduce

```bash
pip install -e .                       # or: pip install -r requirements.txt
python scripts/analysis/stats.py       # recompute the 7B training numbers from committed JSONs
python scripts/analysis/effic_real_stats.py \
    --base runs/agent/er2_27b_base.json --trained runs/agent/er2_27b_readonly.json
```

`stats.py` recomputes every headline number for the weak-model training result from the
committed `runs/agent/*.json` and checks each against `PAPER.md` (`[MATCH]` lines). The
`scripts/run_*.sh` drivers regenerate the JSONs from scratch:

| Driver | Reproduces |
|---|---|
| `run_relabel2.sh` | 7B on-policy training headline (harvest → SFT → retest), PAPER §5 |
| `run_toolablation.sh` | tool-value ablation (with-`defn` vs read-only), PAPER §4 |
| `run_frontier.sh` | frontier election + efficiency via OpenRouter, PAPER §4–5 |
| `run_gapd_frontier.sh` | the type-inference information channel, PAPER §3 |
| `run_relabel2_27b.sh` | 27B cross-scale transfer, PAPER Appendix B |
| `run_grpo.sh` | cost-reward RL corroboration, PAPER Appendix A |

## Test a different model or approach

`scripts/api_agent.py` is a model-agnostic tool-calling harness. Point it at any OpenRouter
model to measure election and the tool-value ablation in the deployment modality, with a hard
spend cap:

```bash
export OPENROUTER_API_KEY=...           # or place the key in a .orkey file the script reads
# election + efficiency on the obscure real-code suite:
python scripts/api_agent.py out.json --model anthropic/claude-sonnet-4.5 \
    --suite effic_real2 --seeds 2 --budget-usd 5
# read-only counterfactual (the same, with <defn> disabled):
python scripts/api_agent.py out_ro.json --model anthropic/claude-sonnet-4.5 \
    --suite effic_real2 --no-defn --seeds 2 --budget-usd 12
# the information channel (a check_types() tool available vs not):
python scripts/api_agent.py out_gd.json --model anthropic/claude-sonnet-4.5 \
    --suite gapd --with-check --seeds 2 --budget-usd 6
```

The local harness (`scripts/synth_mf.py`) does the same for open-weight models with
`--no-defn` (tool ablation) and `--adapter` (a trained policy).

## Code layout

- `scaffold/stream_agent.py` — the local token-stream coding agent (`<read>`/`<defn>`/
  `<findrefs>`/`<test>`/`<edit>`; `--no-defn` ablation).
- `scaffold/mock_env.py` — in-memory workspace with real Pyrefly and the `<defn>` resolver.
- `scaffold/real_env.py` — `RealRepoEnv` over a checked-out git repository, with qualified
  `module.Class.method` resolution.
- `scripts/api_agent.py` — the OpenRouter tool-calling harness (test any frontier model).
- `scripts/synth_tasks_effic.py` — synthetic definition-sufficient efficiency suite.
- `scripts/synth_tasks_efficread.py` — read-required boundary suite.
- `scripts/synth_tasks_effic_real{,2}.py` — real vendored-library suites (`effic_real_vendor/`).
- `scripts/synth_tasks_gapd.py` — type-inference (information-channel) suite.
- `scripts/synth_mf.py` / `scripts/real_mf.py` — local condition runners.
- `scripts/sft_lora.py` — the on-policy LoRA-SFT trainer.
- `scripts/validate_pyrefly_lsp.py` — validates `<defn>` against a live `pyrefly lsp` daemon.
- `scripts/{real_repo_loader,resolver_coverage_audit}.py` — RefactorBench loader + audit
  (see PAPER §6 for why off-the-shelf refactoring benchmarks do not isolate the cost gap).
- `scripts/grpo_cost.py` — cost-reward GRPO corroboration (optional; SFT relabel is the recipe).

## Layout & environment

- `runs/agent/` — committed result JSONs backing `PAPER.md`.
- `runs/sft/` — trained LoRA adapters (git-ignored binaries).
- `log.md` — complete chronological lab log: every run, decision, audit, and retraction.
- `docs/` — figures and the efficiency bibliography; `bibliography.md` is human-readable.

Pyrefly is the static analyzer; the default path is `.venv-streams/bin/pyrefly`, overridable
with `STREAMS_PYREFLY`. `HF_HOME` defaults to `~/.cache/huggingface`. Hardware for the local
runs: a single NVIDIA DGX Spark (GB10, 128 GB unified memory).
