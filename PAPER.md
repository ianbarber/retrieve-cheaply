# Making a Language Server Pay Off for a Coding Agent: Redundant Information, Retrieval Efficiency That Must Be Elicited

## Abstract

We characterize when a language server helps a coding agent, separating the value of its
information from the value of its cheaper retrieval. A coding agent that can read files
resolves most type and reference questions itself, so what a language server adds — and
whether an agent will choose a cheaper action when an expensive one is available — is
unclear. We measure both questions across synthetic and real-repository tasks, a 7B and a
27B local model, and frontier models in a tool-calling loop, by toggling each
language-server capability at matched model capability. Language-server information —
diagnostics, references, completion, and type inference — never improves a self-retrieving
agent's success, while a go-to-definition *action* cuts input tokens 3.7–5.3× at matched
success whenever retrieval is required, the alternative is a whole-file read, and the agent
elects the cheap action. Election is free for capable models through prompt framing (a
frontier model uses the action on 100% of rollouts) but requires on-policy training for a 7B
(0% to 100% use, 4.5× fewer tokens) — which corrects the common assumption that such a
preference can only be trained.

## Contributions

- **Information is redundant.** Across six channels — correction, completeness, navigation,
  prevention, scale, and type inference — handing a self-retrieving agent the language
  server's information never raises pass@1. The agent reads the source and derives the fact
  itself.
- **Efficiency is real, under three conditions.** A go-to-definition action reduces input
  tokens 3.7–5.3× at matched success, and only when (1) retrieval is required, (2) the
  counterfactual is a whole-file read, and (3) the agent elects the cheap action.
- **Election is capability-gated.** Capable models elect the cheap action for free when the
  system prompt frames it as cheaper (a 27B uses it 88–95%, a frontier model 100%); a 7B
  requires on-policy training (0% to 100%). We give the training recipe and show why
  prompting and offline imitation fail for the weak model.

The result is a deployable recipe for when a language server pays off in an agentic loop, and
how to get the agent to use it. The evidence runs from synthetic tasks with a controlled cost
gap to frontier models in the tool-calling modality production agents use; the scope limits
are in §8.

---

## 1. Introduction

Coding agents spend most of their tokens retrieving context. A language server offers a
coding agent two distinct things: *information* (diagnostics, inferred types, reference
lists) and *cheaper retrieval* (a go-to-definition that returns one symbol instead of a
whole file). The two are usually bundled. We separate them and ask which one helps.

The question is sharp because a capable agent can read files on its own. Whatever a language
server computes — a type, a reference site, an error — it computes from source the agent can
also read, so its *information* may be redundant. Prior work treats language-server feedback
as a useful reward or context signal (Zhang et al., 2025); we find that, for a
self-retrieving agent, the information is redundant and the residual value is retrieval cost.
A second question is then a policy question, not an information one: an agent will not use a
cheaper action merely because it exists.

We separate information value from efficiency value by *toggling each capability at matched
model capability* — running the same model with and without a given language-server action,
rather than comparing a trained model to an untrained one. We do this across two synthetic
task families, real vendored library code, a 7B and a 27B open model, and three frontier
models driven through a tool-calling API.

**Contributions.**

1. We show that language-server *information* does not improve a self-retrieving agent's
   pass@1 on any of six channels, including type inference at frontier scale (§3).
2. We show that a go-to-definition *action* reduces input tokens 3.7–5.3× at matched success,
   and identify the three conditions under which the reduction holds (§4).
3. We show that *election* of the cheap action is capability-gated — free for capable models
   through prompt framing, trainable for weak ones — and give the on-policy recipe that works
   where prompting and offline imitation fail (§5).

On the synthetic efficiency suite a 7B agent moves from 0% to 100% go-to-definition use and
from 3086 to 688 input tokens (4.5×) after one on-policy training round; an untrained 27B
reaches 88–95% use from prompt framing alone; and a frontier model in a tool-calling loop
reaches 100% use and a 4.0× token reduction at matched success, for free.

---

## 2. Setup

**Agent and actions.** The agent fixes a bug in a target file through a try-and-correct loop.
It has five actions: `<read path>` returns a full file; `<defn sym>` returns the definition
span of a symbol; `<findrefs sym>` returns reference sites; `<test>` runs the suite; and an
`<edit>` action applies a line-range change. We run the agent in two harnesses. A local
token-stream harness (`scaffold/stream_agent.py`) drives open-weight models
(Qwen2.5-Coder-7B-Instruct, Qwen3.6-27B) with logit access. A turn-based tool-calling harness
(`scripts/api_agent.py`) drives frontier models through the OpenRouter API, exposing the same
actions as function tools — the modality production agents use.

**`<defn>` is a real go-to-definition, not an oracle.** Given a symbol name the agent
requests, the tool AST-resolves that symbol's top-level definition against the live workspace
and returns its source span — what a language server's go-to-definition returns, derived from
the codebase with no privileged knowledge of which symbol or what the answer is, and
returning "(no definition found)" on an unresolvable name. We validated the static resolver
against a production language server: driving a live `pyrefly lsp` daemon (JSON-RPC
`textDocument/definition`) resolves all 12 evaluation symbols to the same definition as the
static resolver (12/12), and a full run with `<defn>` backed by the live daemon reproduces
the headline (use 0→100%, 2894→689 tokens, 58→100% success). We use the static resolver for
bulk runs and the live daemon to confirm server equivalence.

**Environments.** The synthetic *effic* suite buries one needed symbol in a ~370-line module;
`<read>` returns the whole file (~3500 tokens) while `<defn>` returns ~6 lines (~50 tokens).
Tasks are non-guessable — the idiomatic API guess fails — so retrieval is required. A
*read-required* boundary suite inverts this: the needed symbol is unknowable without reading,
so `<defn>` cannot solve it. Two real-code suites (`synth_tasks_effic_real`,
`synth_tasks_effic_real2`) replace the synthetic module with real vendored library source
(`toolz`, `more_itertools`); an inference suite (`synth_tasks_gapd`) requires a type the
type-checker infers (overload resolution, generics, union narrowing, `Protocol`,
`TypedDict`).

**Metrics.** We report go-to-definition use rate, whole-file read rate, input tokens to
solve, and pass@1. We test paired (task, seed) units with exact McNemar on success and an
exact sign test on tokens, and report the discordant counts.

---

## 3. Language-server information is redundant (C1)

We tested whether the information a language server provides — as opposed to a cheaper way to
retrieve it — improves a self-retrieving agent. It does not, on any channel we tested.

**Correction.** An oracle ladder replaces the language server's diagnostic with progressively
stronger feedback: no feedback, synchronous diagnostics, perfect error localization, and the
gold fix. For a 7B agent, perfect localization *harms* pass@1 (0.45 → 0.25, p<0.001), and the
gold fix does not beat no-feedback (0.39 vs 0.45, p=0.29 — a capability floor, not an
information gain). A 35B mixture-of-experts model ceilings the suite. The diagnostic adds
nothing the agent does not already read.

**Completeness and scale.** Varying repository size from 21 to 86 files at a fixed generous
read budget, success stays at 1.00 with roughly 6–8 reads, and find-references does not earn
its keep — reading does not become expensive at tractable scale. **Navigation** reduces to the
same: when name search fails on a re-exported symbol, the agent reads the call graph and
succeeds without find-references. **Prevention** fails its precondition: the agent reads the
library before calling an API and never emits the hallucinated member, so completion has
nothing to prevent.

**Inference.** The remaining channel is the one localization and enumeration never tested:
facts the type-checker *infers* that a model might not derive by reading. We built eight tasks
whose correct fix depends on a non-trivially inferred type, verified that the type-checker
produces a diagnostic naming the type that the runtime test failure does not (for example,
`Returned type int | None is not assignable to int`, or `Object of class Plain has no
attribute escape`). We then gave two frontier models a `check_types()` tool that surfaces
those diagnostics. The tool changes nothing: both `deepseek-chat-v3.1` and
`claude-sonnet-4.5` solve 16/16 with and without it, and `claude-sonnet-4.5` never calls it
(0/16 rollouts; `deepseek` 1/16). The models read the library (mean 0.9 and 1.7 reads) and
infer the types themselves.

**Mechanism.** A language server computes from the same source the agent can read. A capable
agent self-retrieves and self-infers, so the information is redundant across every channel,
and the agent does not even elect the type-checker when offered it. The residual value of a
language server is the *cost* of retrieval, not its content.

---

## 4. Retrieval efficiency is real, under three conditions (C2)

Because `<read X>` and `<defn X>` return the same symbol, the cheap action saves tokens
whenever the agent would otherwise read. We isolate this value with a **tool-value ablation**:
hold the model fixed and toggle the action, rather than compare trained to untrained.

On the obscure real-code suite, removing `<defn>` from a 27B (it can only read) raises its
mean input tokens from 1260 to 4644 — a **3.69× cost** for the same ceiling success (paired
sign test p=0.017, with-`defn` cheaper on 17/22 cells). The same ablation on frontier models
in the tool-calling modality is larger, because each turn re-sends the growing context: a
read-only `claude-sonnet-4.5` spends 23,811 prompt tokens versus 6,014 with `<defn>`
(**4.0×**), and `deepseek-chat-v3.1` spends 49,142 versus 9,325 (**5.3×**), both at 22/22
success. The cheap action is worth 4–5× its alternative, at matched outcome, in the modality
production agents use.

The reduction holds only under three conditions, each isolated by a control.

1. **Retrieval is required.** On a suite of *familiar* library functions, the base model
   guesses the API from memory (35 of 41 successes solved with no retrieval at all), so there
   is no read to replace and the saving disappears. Retrieval-required tasks are the ones
   where the idiomatic guess fails.
2. **The counterfactual is a whole-file read.** The saving is `tokens(read) − tokens(defn)`,
   realized only when the agent would otherwise read. A weak 7B *guesses* rather than reads
   even when it cannot (it thrashes on 18 of 20 failures without reading), so the per-call
   saving is absent for it; a 27B and a frontier model read, so the saving is present.
3. **The agent elects the cheap action.** Availability is not use (§5).

A separate control rules out that the saving merely reflects retrieval helping success: a
model trained to retrieve via `<read>` spends 3191 input tokens against a model trained to
retrieve via `<defn>` at 684, on tasks both solve (4.7× cheaper, sign test p=6.8e-4, n=40).
Both retrieve and solve; the only difference is the action, so the saving is the cost
preference itself.

---

## 5. Election is capability-gated (C3)

Conditions (1) and (2) are properties of the task and the model's reading habit. Condition (3)
— that the agent *elects* the cheap action — is where practitioners have a lever, and it
depends on model capability.

**A weak model needs training; prompting and offline imitation fail.** On the synthetic suite
the 7B uses `<defn>` 2% of the time by default, and a prompt instructing it to prefer `<defn>`
leaves use near 0%. Offline imitation of cheap `<defn>` trajectories also fails — `<defn>` use
stays near 0% and tokens do not fall — because the demonstrations never show the expensive
action available and the cheap one chosen, so the cloned policy is unconstrained exactly where
the preference must be expressed.

On-policy imitation fixes the distribution mismatch. We roll out the untrained agent with both
actions available; where it emits `<read>` for a non-editable file and the needed symbol is
resolvable, we drop that step and let the agent emit `<defn sym>` itself, keeping the rest of
its trajectory; we fine-tune a LoRA adapter on the relabeled trajectories (one DAgger round).
No gold action is injected — we relabel only the retrieval channel of the agent's own
behavior. The 7B then moves to 100% `<defn>` use, success 0.65→1.00, and input tokens
3086→688 (4.5×; McNemar success p=1.5e-5, b=17/c=0; sign test tokens p=2.2e-4, cheaper on
37/48). The preference generalizes to held-out task types (0.42→1.00 success, 5.2× tokens) and
preserves a read-when-needed boundary: on read-required tasks the trained agent still reads
100% of the time and success rises (0.54→0.83). A cost-reward GRPO objective reaches the same
operating point over four rounds (Appendix A), so an independent training signal instills the
same preference.

**A capable model needs only framing.** The same prompt that leaves the 7B at 2% moves an
untrained 27B to 88% use. The driver is the *system-prompt framing of the action as cheaper
than a read*, not the repository, and not a trained preference. We confirm this with a
prompt-versus-structure control: on the identical synthetic 2-file suite, the older prompt
(which advertised `<defn>` only in the task message) yielded 0% use and 4058 tokens, while the
current prompt (which presents `<defn>` as the cheaper alternative beside the read
instruction) yields 88% use and 1237 tokens. Frontier models go further — `claude-sonnet-4.5`
elects `<defn>` on 100% of rollouts and `deepseek-chat-v3.1` on 95%, with no training (§4).

**The correction.** A cheap-retrieval preference is not "only learnable by training." That
holds for a weak model, where prompting and offline cloning fail and on-policy training
succeeds. For a capable model the preference is elicited for free by framing the tool as the
cheaper option. Training is the lever for weak models; framing is the lever for strong ones.

---

## 6. Real repositories and deployment

**The preference transfers to real code.** The synthetic-trained 7B adapter, run unchanged on
real `toolz`/`more_itertools` code, uses `<defn>` on 100% of rollouts and writes correct
non-idiomatic calls from the retrieved signature. On obscure real symbols it Pareto-improves
the untrained 7B — higher success (0.75 vs 0.55) and lower mean tokens — because the untrained
model guesses and thrashes while the trained one retrieves and solves.

**A measurement caveat for familiar APIs.** On *familiar* library functions the base 7B
guesses the API from memory, so the clean per-call token saving does not appear there (§4,
condition 1); the gain on familiar code is reliability, not tokens. The clean saving requires
either an unfamiliar symbol or a model that reads rather than guesses — which is why the 27B
and frontier ablations (§4) recover the full 3.7–5.3×.

**Deployment.** The frontier tool-calling validation (§4–5) is the deployment-relevant result:
in the exact modality of production coding agents, a frontier model elects the cheap action
from prompt framing and saves 4–5× tokens at matched success, for a total API spend of ~$3.40.

**What does not work: off-the-shelf refactoring benchmarks.** We evaluated RefactorBench
(Gautam et al., 2025) for a non-constructed real-code test and found it structurally unsuited
to the cost-gap question. Its tasks edit the symbol's *own* large file, so the agent must load
that file to edit it regardless of `<defn>`; the rename variants exercise find-references, the
channel §3 finds redundant; and three of four candidate symbols sit past the editable-view
truncation. We report this as a finding — off-the-shelf refactoring benchmarks do not
naturally create a read-versus-definition cost decision — rather than force a fit.

---

## 7. Related work

Our method is on-policy imitation under distribution shift. GKD (Agarwal et al., ICLR 2024)
distills a teacher under the student's own distribution; DAgger (Ross, Gordon & Bagnell,
AISTATS 2011) and cost-aware AggreVaTe (Ross & Bagnell, 2014) ground rolling out a learned
policy and relabeling with an expert; Revisiting DAgger for LLM agents (Li et al., 2025)
applies the idea to tool-using language models. STaR (Zelikman et al., 2022) bootstraps
reasoning from the model's own rationales; we bootstrap a cost preference from the model's own
trajectories. The expert here is a deterministic read→defn relabel, not a model.

Cost-aware tool use through RL is the alternative we corroborate but do not require. OTC-PO
(Wang et al., 2025) and IKEA (Huang et al., 2025) reward fewer or cheaper tool calls; their
results motivate that a token-cost reward learns the same preference we obtain by on-policy
imitation, which our GRPO corroboration confirms (Appendix A).

The closest prior work on language servers is RLCSF (Zhang et al., 2025), which rewards
compiler and language-server diagnostics during RL. RLCSF treats the diagnostic as a useful
signal; we find its information redundant for a self-retrieving agent and locate the residual
value in retrieval cost.

---

## 8. Limitations

- **Synthetic cost gap.** The headline cost gap and the non-guessability of tasks are
  engineered. We address external validity with real vendored code (§6) and frontier
  tool-calling runs (§4), but the read-required boundary covers two reasons a read is needed
  (name-hidden, many-symbol), not all.
- **Redundancy is scoped to our suites.** We show language-server information is redundant
  across six channels for a self-retrieving agent; we do not prove it is redundant on
  arbitrary repositories. The mechanism — the server computes from readable source — predicts
  the result generalizes, but does not guarantee it for non-readable runtime facts.
- **Weak-model capability floor.** Some 7B failures are execution, not retrieval: the trained
  agent retrieves the correct definition and still cannot apply it. We report this as a floor,
  not a result, and use the 27B and frontier runs to separate capability from the channel.
- **Light seeds at scale.** The 27B and frontier runs use 2 seeds per cell against the 7B's
  4–12. The effects are large (3.7–5.3×) and the success ceilings are clean, but these are
  validations, not fully-powered headlines.
- **Static resolver.** `<defn>` is an AST resolver over the live workspace, validated against
  a live `pyrefly lsp` daemon (12/12, §2), not a production language-server client at scale.
- **Tool-calling token accounting.** The API harness re-sends context each turn, so its
  absolute token counts are not comparable to the local harness; we report within-harness
  ratios at matched success.

---

## 9. Conclusion

A language server does not help a coding agent by providing information the agent cannot
already read; across correction, completeness, navigation, prevention, scale, and type
inference, the information is redundant for a self-retrieving agent. Its residual value is a
cheaper retrieval action, which cuts input tokens 3.7–5.3× at matched success — but only when
retrieval is required, the alternative is a whole-file read, and the agent elects the cheap
action. Election is the practitioner's lever: a capable model elects the cheap action for free
when the prompt frames it as cheaper, and a weak model learns to through one round of
on-policy imitation, where prompting and offline cloning fail.

**The recipe.** To make a language server pay off in an agentic loop: (1) expose
go-to-definition as an *action*, not diagnostics as context; (2) frame it in the system prompt
as cheaper than a whole-file read; (3) if the model is weak enough to ignore the framing, train
the preference on-policy by relabeling its own reads to definitions; (4) mix in tasks that
genuinely need a full read, so the agent learns when the cheap action suffices. The broader
lesson, where an agent has two actions returning the same information at different cost, is
that the cheaper one is used by default only when the model is capable enough to recognize it,
and otherwise must be trained.

---

## Appendix A — Cost-reward RL corroboration

A GRPO objective (reward: solve at minimum tokens, group-normalized advantage over the model's
own action tokens) reaches the same cheap-retrieval operating point as the on-policy relabel,
over four rounds. A single round under-trains (use 38%→6%, tokens 2048→3041); after four rounds
the policy converges to 86% use and 790 mean tokens, and a clean held-out retest lands at 86%
use, 663 tokens, 100% solved. GRPO corroborates that a token-cost objective instills the same
preference; the SFT relabel remains the headline recipe because it needs one round.

## Appendix B — Cross-scale transfer of the training recipe

The same relabel pipeline run on Qwen3.6-27B (a different generation and a reasoning model)
moves the model from 0% use / 96% read / 4058 tokens to 100% use / 0% read / 726 tokens —
5.5× cheaper at matched success (n=24). The training recipe is not a small-model artifact and
transfers across a ~4× scale jump and a model-family change.

## Appendix C — Reproduction

All result JSONs are committed under `runs/agent/`. The `scripts/run_*.sh` drivers regenerate
them: `run_relabel2.sh` (the 7B on-policy headline), `run_toolablation.sh` (the tool-value
ablation), `run_frontier.sh` and `run_gapd_frontier.sh` (the frontier validation and the
inference channel). `scripts/api_agent.py` is model-agnostic: pass `--model <openrouter-id>`
to test a new model in the tool-calling modality, with a hard `--budget-usd` cap.
`scripts/analysis/effic_real_stats.py` and `scripts/analysis/stats.py` recompute the result
tables from the committed JSONs. Hardware for the local runs: a single NVIDIA DGX Spark (GB10,
128 GB unified memory).
