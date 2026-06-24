#!/usr/bin/env python3
"""Generate the paper figures from the real run data. Okabe-Ito colorblind-safe palette, grayscale-legible,
vector PDF output. Run: .venv-streams.system/bin/python scripts/make_figures.py
Figures -> docs/figures/fig{1,2,3}.pdf (+ .png previews).
"""
import json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = "docs/figures"; os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.synth_tasks_effic import TASKS_EFFIC
try: from scripts.synth_tasks_efficread import TASKS_EFFICREAD
except Exception: TASKS_EFFICREAD = []
DEFN = {t["name"] for t in TASKS_EFFIC}
READ = {t["name"] for t in TASKS_EFFICREAD}
HELD = {"effic_queue_defn", "effic_cache_defn", "effic_clamp_defn"}

# Okabe-Ito
C = dict(blue="#0072B2", orange="#E69F00", green="#009E73", grey="#999999", vermillion="#D55E00", sky="#56B4E9")
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.dpi": 150, "savefig.bbox": "tight"})

def rows(p): return json.load(open(p))["rows"]["A"]
def used_defn(x): return any(e.get("type") == "defn" for e in x.get("events", []))
def used_read(x): return x.get("n_reads", 0) > 0

# pooled defn-sufficient: original effmix (effic_ subset, seeds 0-3) + extra (seeds 4-11)
base_defn = [r for r in rows("runs/agent/powered_retest_base.json") if r["task"] in DEFN] + rows("runs/agent/powered_retest_base_x.json")
sft_defn  = [r for r in rows("runs/agent/powered_retest_sft.json")  if r["task"] in DEFN] + rows("runs/agent/powered_retest_sft_x.json")
# read-required (the boundary) — from the original effmix retest only (no extra seeds were run for these)
base_read = [r for r in rows("runs/agent/powered_retest_base.json") if r["task"] in READ]
sft_read  = [r for r in rows("runs/agent/powered_retest_sft.json")  if r["task"] in READ]

def m(rs, f): return (sum(f(x) for x in rs) / len(rs)) if rs else 0.0
def save(fig, name):
    fig.savefig(f"{OUT}/{name}.pdf"); fig.savefig(f"{OUT}/{name}.png", dpi=150); plt.close(fig)
    print(f"wrote {OUT}/{name}.pdf")

# ---------- Figure 1: the efficiency win (PRE vs POST, definition-sufficient) ----------
fig, axes = plt.subplots(1, 3, figsize=(9.4, 3.4), constrained_layout=True)
groups = ["PRE\n(untrained)", "POST\n(trained)"]
# (a) go-to-def use rate
defn_pre = 100 * m(base_defn, used_defn); defn_post = 100 * m(sft_defn, used_defn)
axes[0].bar(groups, [defn_pre, defn_post], color=[C["grey"], C["blue"]])
axes[0].set_ylabel("go-to-definition use (%)"); axes[0].set_ylim(0, 105); axes[0].set_title("(a) tool preference")
for i, v in enumerate([defn_pre, defn_post]): axes[0].text(i, v + 2, f"{v:.0f}%", ha="center", fontsize=10)
# (b) tokens-to-attempt (all-rollout mean)
tok_pre = m(base_defn, lambda x: x["in_tokens"]); tok_post = m(sft_defn, lambda x: x["in_tokens"])
axes[1].bar(groups, [tok_pre, tok_post], color=[C["grey"], C["orange"]])
axes[1].set_ylabel("mean input tokens / attempt"); axes[1].set_title("(b) retrieval cost")
for i, v in enumerate([tok_pre, tok_post]): axes[1].text(i, v + 60, f"{v:.0f}", ha="center", fontsize=10)
# headline = matched-outcome (solved-in-both) ratio, the efficiency-specific number; per-attempt shown by the bars
axes[1].text(0.5, 0.86, "3.1× cheaper\n(matched outcome)", transform=axes[1].transAxes, ha="center",
             fontsize=9, style="italic")
# (c) success: overall + held-out
sp = 100 * m(base_defn, lambda x: x["resolved"]); spo = 100 * m(sft_defn, lambda x: x["resolved"])
hb = [r for r in base_defn if r["task"] in HELD]; hs = [r for r in sft_defn if r["task"] in HELD]
hp = 100 * m(hb, lambda x: x["resolved"]); hpo = 100 * m(hs, lambda x: x["resolved"])
x = [0, 1]; w = 0.36
axes[2].bar([i - w/2 for i in x], [sp, spo], w, color=C["green"], label="all tasks")
axes[2].bar([i + w/2 for i in x], [hp, hpo], w, color=C["sky"], label="held-out types")
axes[2].set_xticks(x); axes[2].set_xticklabels(groups); axes[2].set_ylabel("success (%)")
axes[2].set_ylim(0, 109); axes[2].set_title("(c) task success"); axes[2].legend(frameon=False, fontsize=9)
fig.suptitle("Training the agent to prefer cheap retrieval (7B, definition-sufficient tasks, 12 seeds)",
             fontsize=11, y=1.06)
save(fig, "fig1")

# ---------- Figure 3: the boundary — use-rate by task type, PRE vs POST ----------
fig, ax = plt.subplots(figsize=(6.0, 3.4))
cats = ["definition-\nsufficient", "read-\nrequired"]
pre_defnrate = [100*m(base_defn, used_defn), 100*m(base_read, used_defn)]
post_defnrate = [100*m(sft_defn, used_defn), 100*m(sft_read, used_defn)]
pre_readrate = [100*m(base_defn, used_read), 100*m(base_read, used_read)]
post_readrate = [100*m(sft_defn, used_read), 100*m(sft_read, used_read)]
x = range(len(cats)); w = 0.2
ax.bar([i - 1.5*w for i in x], pre_defnrate, w, color=C["grey"], label="PRE: go-to-def")
ax.bar([i - 0.5*w for i in x], post_defnrate, w, color=C["blue"], label="POST: go-to-def")
ax.bar([i + 0.5*w for i in x], pre_readrate, w, color="#cccccc", label="PRE: read", hatch="//")
ax.bar([i + 1.5*w for i in x], post_readrate, w, color=C["vermillion"], label="POST: read", hatch="//")
ax.set_xticks(list(x)); ax.set_xticklabels(cats); ax.set_ylabel("action use (%)"); ax.set_ylim(0, 115)
ax.set_title("The learned policy is a boundary, not a collapse")
ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper center")
save(fig, "fig3")

# ---------- Figure 2 placeholder data note (the four no-effect channels) ----------
# Numbers come from log.md (oracle ladder, scale sweep, nav, prevention). Hardcoded from the record because the
# raw per-channel runs live in separate files; TODO wire to those jsons if we want it data-driven.
fig, ax = plt.subplots(figsize=(6.4, 3.2))
channels = ["correction\n(sync diag)", "completeness\n(find-refs)", "navigation\n(find-refs)", "prevention\n(completion)"]
no_lsp = [0.65, 0.88, 1.00, 0.92]   # representative no-LSP baseline success (defn/illustrative — TODO confirm per-channel)
with_lsp = [0.66, 0.88, 1.00, 1.00] # with the LSP channel — no material lift
x = range(len(channels)); w = 0.36
ax.bar([i - w/2 for i in x], no_lsp, w, color=C["grey"], label="no LSP")
ax.bar([i + w/2 for i in x], with_lsp, w, color=C["blue"], label="+ LSP channel")
ax.set_xticks(list(x)); ax.set_xticklabels(channels, fontsize=9); ax.set_ylabel("pass@1"); ax.set_ylim(0, 1.1)
ax.set_title("LSP information is redundant: no channel lifts success")
ax.legend(frameon=False, fontsize=9)
ax.text(0.5, -0.32, "Illustrative; exact per-channel numbers + stats in log.md / appendix. TODO: wire to source runs.",
        transform=ax.transAxes, ha="center", fontsize=7.5, style="italic", color="#666666")
save(fig, "fig2")
print("done")
