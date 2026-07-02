# LSPs for LLMs

Code, result data, and reproduction scripts for the in-progress tech report
[REPORT.md](./REPORT.md), *When Does a Language Server Help a Coding Agent? Work-in-Progress Findings*.

**Status: work in progress.** We are exploring when a language server (LSP) actually helps an LLM
coding agent, by separating the two things it offers, **information** (diagnostics, types, references)
and **cheaper retrieval** (go-to-definition instead of a whole-file read), and toggling each at fixed
model capability.

## Current findings (work in progress)

- **Information is redundant when it is readable in budget.** Wherever the agent can read the source and
  derive the fact, handing over the language server's information does not raise pass@1, on every channel
  we tested (correction, completeness, navigation, prevention, scale, type inference) and, as a boundary
  check, on runtime behavior. Both frontier models solve the held-out-scored inference test 18/18 with
  zero latent bugs, with a `check_types()` tool and without it. (Untested: a codebase too large or tangled
  to read in budget.)
- **Election is capability-gated.** A 7B uses `<defn>` 2% of the time by default and ignores a prompt
  telling it to prefer the action; one on-policy training round takes it to 100% use and 4.5× fewer
  tokens. A capable model needs only framing: presenting `<defn>` as cheaper than a read moves an
  untrained 27B to 88 to 93% use and a frontier model to 100%.
- **Efficiency is a win only against a whole-file read.** Toggling the action on the same model, `<defn>`
  cuts input tokens 3.5 to 4.7× at equal success:

  | model | tokens with `<defn>` | tokens read-only | factor |
  |---|---|---|---|
  | 27B (real obscure suite) | 1302 | 4563 | 3.5× |
  | claude-sonnet-4.5 (tool-calling) | 6018 | 21985 | 3.7× |
  | deepseek-chat-v3.1 (tool-calling) | 7705 | 36192 | 4.7× |

  But that baseline is a *forced whole-file read*. An in-the-wild probe with a real bash agent
  (mini-swe-agent on SWE-bench Verified) finds a capable agent retrieves just as cheaply with `grep` plus
  ranged `sed`, uses go-to-definition little even when prompted, and reads the file anyway when it does
  (additive, not substitutive). So the efficiency edge does not clearly transfer past the whole-file
  baseline. See REPORT.md §3.4 and `docs/real_repo_progress.md`.
- **Open question (next).** `grep` is textual; a language server is semantic. Where does semantic
  resolution (receiver-type and overload disambiguation, re-exports and aliases, precise references)
  supply something a text search cannot, and does that precision change a capable agent's *outcome*, not
  just its path? That is the experiment we are setting up.

## The recipe (for the efficiency win, scoped to a whole-file-read baseline)

1. Expose go-to-definition as an action, not diagnostics as context. The information in
   diagnostics, references, and completion is redundant for a self-retrieving agent.
2. Frame it in the system prompt as cheaper than a read. Capable models then use it without training.
3. If the model is weak enough to ignore the framing, train the preference on-policy: roll out the
   agent, rewrite its `<read>` of a resolvable symbol to `<defn sym>`, and fine-tune on the relabeled
   trajectories (one DAgger round).
4. Mix in tasks that genuinely need a full read, so the agent learns when the cheap action suffices.

## Reproduce

```bash
pip install -e .                       # add '.[api]' for the frontier tool-calling path
python scripts/analysis/stats.py       # recompute the 7B training numbers from committed JSONs
```

`stats.py` recomputes every weak-model training number from the committed `runs/agent/*.json` and
checks each against `REPORT.md` (`[MATCH]` lines). `effic_real_stats.py` does the paired stats for the
real-code and tool-ablation runs. The `scripts/run_*.sh` drivers regenerate the JSONs:

| Driver | Reproduces |
|---|---|
| `run_relabel2.sh` | 7B on-policy training (harvest, SFT, retest), report §4 |
| `run_toolablation.sh` | tool-value ablation, with `<defn>` vs read-only, report §3 |
| `run_frontier.sh` | frontier election and efficiency via OpenRouter, report §3 to §4 |
| `run_gapd_frontier.sh` | the type-inference information channel, report §5 |
| `run_gapd2_frontier.sh` | the held-out-scored fair inference test, report §5 |
| `run_runtime_frontier.sh` | the execution-feedback boundary test (no-run / run / handed-over), report §5 |
| `run_relabel2_27b.sh` | 27B cross-scale transfer, Appendix B |
| `run_grpo.sh` | cost-reward RL corroboration, Appendix A |

The in-the-wild probe (report §3.4) is exploratory: `scripts/realbench/mini_ablate.py` runs
mini-swe-agent on a SWE-bench Verified task under three arms (bash-only / `codenav` advertised / strongly
framed) in the task's Docker container. Findings and per-arm logs: `docs/real_repo_progress.md`.

## Test a different model or approach

`scripts/api_agent.py` is a model-agnostic tool-calling harness. Set `OPENROUTER_API_KEY` (or place
the key in a `.orkey` file at the repo root, gitignored) and point it at any OpenRouter model to
measure election and the tool-value ablation, with a hard spend cap:

```bash
# election and efficiency on the obscure real-code suite:
python scripts/api_agent.py out.json --model anthropic/claude-sonnet-4.5 \
    --suite effic_real2 --seeds 2 --budget-usd 5
# the read-only counterfactual (same, with <defn> removed):
python scripts/api_agent.py out_ro.json --model anthropic/claude-sonnet-4.5 \
    --suite effic_real2 --no-defn --seeds 2 --budget-usd 12
```

Other suites swap `--suite`: `gapd --with-check` (the type-inference information channel) and `runtime
--no-hint --no-test` (the execution-feedback boundary; drop `--no-test` for elect-to-run, add
`--auto-feedback` for handed-over). The local harness (`scripts/synth_mf.py`) does the same for
open-weight models, with `--no-defn` (tool ablation) and `--adapter` (a trained policy).

## Code layout

| Path | What it is |
|---|---|
| `scaffold/stream_agent.py` | local token-stream coding agent (`<read>`/`<defn>`/`<findrefs>`/`<test>`/`<edit>`, `--no-defn` ablation) |
| `scaffold/mock_env.py` | in-memory workspace with real Pyrefly and the `<defn>` resolver |
| `scripts/api_agent.py` | OpenRouter tool-calling harness (test any frontier model) |
| `scripts/synth_tasks_effic.py` | synthetic definition-sufficient efficiency suite |
| `scripts/synth_tasks_efficread.py` | read-required boundary suite |
| `scripts/synth_tasks_effic_real{,2}.py` | real vendored-library suites (`effic_real_vendor/`) |
| `scripts/synth_tasks_gapd.py`, `scripts/synth_tasks_gapd2.py` | type-inference suite (gapd2 adds held-out scoring) |
| `scripts/synth_tasks_runtime.py` | execution-feedback boundary suite (structural, easy, and semantic-trap tiers) |
| `scripts/synth_mf.py` | local condition runner |
| `scripts/sft_lora.py` | on-policy LoRA-SFT trainer |
| `scripts/validate_pyrefly_lsp.py` | validates `<defn>` against a live `pyrefly lsp` daemon |
| `scripts/grpo_cost.py` | cost-reward GRPO corroboration (optional) |
| `scripts/realbench/mini_ablate.py`, `codenav.py` | in-the-wild probe: mini-swe-agent + language-server-as-CLI (§3.4) |

## Layout and environment

`runs/agent/` holds committed result JSONs; `runs/sft/` trained LoRA adapters (gitignored); `log.md` is
the chronological lab log; `docs/` has figures and the bibliography. Static analyzer: Pyrefly
(`.venv-streams/bin/pyrefly`, override `STREAMS_PYREFLY`). Local runs: one NVIDIA DGX Spark (GB10, 128 GB).
