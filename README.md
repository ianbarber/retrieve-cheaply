# Streams — making a language server pay off for a coding agent

**A language server's *information* is redundant for a capable, self-retrieving
coding agent — but its *retrieval efficiency* is a trainable preference.** This repo
is the complete evidence base and reproducible recipe for the tech report:

> **[PAPER.md](./PAPER.md)** — *Making a Language Server Pay Off for a Coding Agent:
> Train It to Retrieve Cheaply*

**The result in one breath (Qwen2.5-Coder-7B + real Pyrefly):** a coding agent will
not, on its own, prefer a language server's cheap go-to-definition (`<defn>`, ~tens of
tokens) over an expensive whole-file `<read>` (~thousands). Default use is ~2%;
explicitly *telling* it to prefer the LSP leaves it at ~0%; offline imitation does not
move it. But **on-policy** supervised fine-tuning of the preference works: use climbs
from ~0% to ~100% go-to-definition and the agent spends **~4.5× fewer input tokens at
matched success** (headline 3086→688 tokens on definition-sufficient tasks; success
0.65→1.00 on the mixed boundary suite, McNemar p=1.5e-5). The cheap action is *real* —
validated 12/12 against a live `pyrefly lsp` daemon — and the agent learns the
**boundary**: it still `<read>`s when a definition is genuinely insufficient. The method
transfers to a ~4× larger model (Qwen3.6-27B: 0→100% use, 5.5× fewer tokens).

## The recipe (for practitioners)

1. **Attach the LSP for efficiency, not information.** Give the agent a real
   go-to-definition action, not diagnostics — a capable agent already reads what
   diagnostics would tell it; the cost saving is what's left on the table.
2. **Train the preference; don't prompt it.** Asking ("prefer the LSP") does ~nothing.
3. **Train it on-policy.** Offline demonstrations never show "the expensive action was
   available and I chose the cheap one." Relabel the agent's *own* reads into
   go-to-definitions and fine-tune on that (on-policy SFT / DAgger round-0).
4. **Preserve the boundary.** Mix in tasks that genuinely need a full read, so the
   agent learns *when* the cheap action suffices instead of blindly always-`<defn>`.

See §2 of `PAPER.md` for the full method, caveats, and scope.

## Start here

| | |
|---|---|
| `PAPER.md` | the tech report — method, results, the recipe, and what doesn't work |
| `log.md` | the complete chronological lab log — every run, decision, audit, retraction, unedited |
| `scripts/run_relabel2.sh` | reproduce the headline on-policy relabel experiment (harvest → SFT → retest) |
| `scripts/analysis/stats.py` | **reproduce every headline number** from the committed `runs/`: `python scripts/analysis/stats.py` (checks each figure against `PAPER.md`) |

`analysis/stats.py` recomputes the full recipe table — headline 3086→688 (4.5×), the
relabel-only and matched-outcome controls, the real-LSP run, the read-required
boundary, the GRPO corroboration, and the 27B transfer — straight from the result
JSONs, and the `run_*.sh` drivers in `scripts/` re-run the experiments that produce them.

## Core code

- `scaffold/` — the non-blocking continuous-stream coding agent (`stream_agent.py`,
  every retrieval action as a flag) and the task environment with real Pyrefly
  (`mock_env.py`, including the `<defn>` go-to-definition resolver).
- `scripts/synth_tasks_effic.py` — the definition-sufficient task suite;
  `scripts/synth_tasks_efficread.py` — the read-required boundary tasks.
- `scripts/synth_mf.py` — the condition runner (rollouts, harvest, retest).
- `scripts/sft_lora.py` — the on-policy LoRA-SFT trainer (the key training step).
- `scripts/validate_pyrefly_lsp.py` — validates `<defn>` against a live pyrefly LSP daemon.
- `scripts/grpo_cost.py` + `run_grpo.sh` — the cost-reward GRPO alternative (scoped/optional;
  the SFT relabel is the headline).

## Layout

- `runs/agent/` — the committed efficiency-recipe result JSONs (the PRE/POST retests
  reproduced by `analysis/stats.py`); `runs/sft/` holds the trained LoRA adapters
  (git-ignored binaries). Some earlier-phase data still lives under `runs/` as legacy.
- `docs/` — paper figures and the efficiency bibliography.
- `bibliography.md` — BibTeX for the paper.

Hardware: single NVIDIA DGX Spark (GB10, 128GB unified), everything local.
