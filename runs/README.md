# runs/ — committed result data

The efficiency-recipe result JSONs that back `REPORT.md`. Finalized JSONs have shape
`{"rows": {"A": [row, ...]}}`; each row carries `task`, `seed`, `resolved`,
`in_tokens`, `n_lsp` (>0 = used `<defn>`), `n_reads` (>0 = used `<read>`), and the
event trace. **Reproduce every headline number:** `python scripts/analysis/stats.py`
from the repo root (it reads exactly the files below and checks each against `REPORT.md`).

| file(s) | report section | what it shows |
|---|---|---|
| `agent/reallsp_base.json` / `reallsp_sft.json` | §5.1 headline | defn-sufficient PRE→POST: 0→100% `<defn>`, 3086→688 tokens (4.5×), success 0.65→1.00 |
| `agent/effic_retest_base.json` / `relabel2_retest.json` | §5.1 relabel-only | the relabel method in isolation: 0→100%, 3086→724 (4.3×) |
| `agent/powered_retest_base{,_x}.json` / `powered_retest_sft{,_x}.json` | §5.1 pilot | matched-outcome lead-`<defn>` pilot: 2108→675 (3.1×), success p=6.3e-14 |
| `agent/effic_readtrained_retest.json` vs `powered_retest_sft.json` | §5.1 isolation control | read-trained vs defn-trained at matched outcome: 3191→684 (4.7×), p=6.8e-4 |
| `agent/lsp_base.json` / `lsp_sft.json` | §3 (real-LSP validation) | real `pyrefly lsp` daemon driving `<defn>`: 0→100%, 2894→689, 0.58→1.00 |
| `agent/reallsp_*.json` (read-required subset) | §5.2 boundary | non-degeneracy: read-rate stays ~100%, success 0.54→0.83 |
| `agent/grpo_retest.json`, `grpo_harvest_0..4.json`, `grpo_retest_round1.json` | §5.3 GRPO | cost-RL corroboration: clean retest 86% defn / 663 tok / 100%; harvest 37→48→86% |
| `agent/27b_base.json` / `27b_retest.json` | §Limitations | Qwen3.6-27B transfer: 0→100%, 4058→726 (5.5×), 0.96→1.00 |

`sft/` holds the trained LoRA adapters (git-ignored binaries): `effic_lora_powered`
(headline), `effic_lora_relabel2` (relabel), `effic_lora_relabel2_27b` (27B),
`effic_lora_grpo` (GRPO), `effic_lora` (read-trained, for the isolation control).
Other `agent/*.json` are recipe-phase harvests and ablations referenced in `log.md`.
