# Tech Report — Making a Language Server Pay Off for a Coding Agent: Train It to Retrieve Cheaply

*Tech report (per Ian: a tech report, not an academic paper — more honest, same results-focused orientation). Direct
and engineering-flavored: what we did, what we found, the recipe, and what doesn't work. All `<defn>` results use a
REAL go-to-definition resolver over the live workspace — the AST resolver answers every evaluation query and no oracle
is consulted in the eval loop (see Setup). Draft v0.4, 2026-06-21. Numbers from log.md; TODO markers flag figures and
pending runs.*

---

## Summary
A language server gives a capable coding agent no *information* it cannot already read — across correction,
completeness, navigation, and prevention, the diagnostic/find-references/completion channels did not improve task
success on our suites for an agent that self-retrieves. Its one real benefit is **cheaper retrieval**: a go-to-definition
returns one symbol's definition at a fraction of a whole-file read's token cost. But the agent does not take the cheap
action on its own — not by default (~2% use), not under explicit instruction (a 35B stays at 0% even when told to
prefer it), and not from offline imitation of the cheap action. We get the win by **training the preference on-policy**:
a 7B agent goes to 100% go-to-definition use and spends several× fewer input tokens at maintained-or-better success
(headline 3086→688, 4.5×; the *read-trained-vs-defn-trained isolation control* at matched outcome gives 3191→684, 4.7×,
defn cheaper on 31/40, p=6.8e-4 — see §5.1 for which number isolates what). It also
learns the **boundary** — on tasks that genuinely need a full read it still reads 100% of the time — so it is
"definition when sufficient, read when needed," not a degenerate always-defn.

## The recipe (what a practitioner takes away)
1. **Use the LSP for efficiency, not information.** Give the agent a real go-to-definition *action* (`<defn sym>`), not
   diagnostics-as-context — the information is redundant for a self-retriever; the cost saving is not.
2. **Train the preference; do not prompt for it.** Default and explicit instruction leave use at ~0%.
3. **Train it on-policy.** Offline imitation of the cheap action teaches "retrieve," not "prefer the cheap retrieval,"
   because the demonstrations never contain "the expensive action was available and I chose the cheap one." We isolate
   this directly: a model trained to retrieve-via-read and our trained model both retrieve and solve, but ours is 4.7×
   cheaper at matched outcome — the saving is the action choice, not retrieval-vs-guess.
4. **Preserve the boundary.** Mix in tasks that genuinely need a full read so the agent learns *when* the cheap action
   suffices. Result: a real LSP that saves several× the tokens at maintained-or-better success. **Caveat to be honest
   about:** the read→definition relabel is only valid where go-to-definition actually covers the needed symbol, and in
   this study that coverage is *known* (the suite labels each task definition-sufficient or read-required, and the
   training mix uses that label). The method instills the preference *given* a coverage signal; it does not yet
   demonstrate the agent learning to *judge* coverage from scratch. A practitioner applying this needs a way to label or
   detect defn-sufficiency (e.g. "did the definition resolve and contain the symbol I needed?").

---

## Key results
- **C1 (the value-add).** Applying the recipe makes a *real* go-to-definition (resolved from the codebase, not an
  oracle) a genuine win: a 7B agent goes from 0→100% use on definition-sufficient tasks and, at matched outcome (tasks
  both the untrained and trained agents solve), spends 3.1× fewer input tokens (2108→675, paired p=2.7e-4, n=84) with
  success rising 0.60→0.98 (McNemar p=6.2e-14, n=144). Re-running the full headline end-to-end with the **real
  resolver** (no oracle in the loop) reproduces it: definition-sufficient use 0→100%, mean input tokens 3086→688 (4.5×,
  paired sign p=2.2e-4, cheaper on 37/48), success 0.65→1.00 (McNemar p=1.5e-5, b=17/c=0). [Scope: the cost gap is
  task-controlled; the efficiency claim is isolated from "retrieval helps success" by the matched-outcome token test and
  the read-trained baseline (§5.3).]
- **C2 (non-degeneracy).** The trained policy is a *boundary*, not a collapse: on tasks where go-to-definition is
  insufficient and a full read is required, the agent still reads in 100% of rollouts and its success *rises*
  (0.58→0.79; real-resolver headline 0.54→0.83). (It reads on every read-required rollout; on name-hidden tasks it may
  *also* emit a go-to-definition first and then read, while on many-symbol tasks it reads once instead of issuing
  several calls — so go-to-definition use on the boundary is ~50%, but always backed by a read.) On those tasks its
  token count goes *up* (real-resolver 2632→4844), because it correctly pays the read cost to actually solve genuinely
  read-required work — the efficiency win is on definition-sufficient tasks, not bought by under-reading the ones that
  need a read. It learned "definition when sufficient, read when needed."
- **C3 (what fails, and why).** The preference is not adopted by default (2% use on the definition-only suite, 0% on
  the mixed headline suite; 0% for a 35B even when explicitly instructed to prefer it) and is not instilled by offline
  rejection-sampling on demonstrations of the cheap action
  (use stays ~0, tokens unchanged) — a predictable off-policy failure: the demonstrations never show the cheap action
  chosen over an available expensive one.
- **C4 (scoped motivation — why we study efficiency).** *On our task suites*, a language server's information channels
  (diagnostics, find-references, completion) do not improve pass@1 over a no-tool baseline for a self-retrieving agent,
  because the agent already reads the files those features summarize. We do **not** claim universal redundancy: our
  strong model ceilings these tasks (no headroom) and our weak model has a capability floor (cannot act on any
  feedback, gold-fix included), and we did not test regimes with genuinely non-readable facts or ambiguous navigation.
  C4 motivates why we isolate *efficiency*; it is not itself a headline result.

---

## Section plan

### 1. Introduction
- **Hook:** coding agents spend most of their tokens retrieving context. The same information is often available two
  ways — a targeted language-server query (go-to-definition, ~50 tokens) or a whole-file read (~3500 tokens). A capable
  agent does not choose the cheap path on its own.
- **The gap:** this is a *policy* problem, not an information one. We show the cheap-retrieval preference is not
  reachable by prompting or by offline imitation of the cheap action, for a precise reason (off-policy distribution
  mismatch), and that it *is* reachable on-policy.
- **The method in one line:** relabel the agent's own reads to the cost-dominant go-to-definition and fine-tune on
  those on-policy trajectories.
- Contribution bullets C1–C4.
- **Results preview:** 2→100% use, ~4.5× tokens, 0.65→1.00 success, held-out generalization, boundary preserved.

### 2. Why efficiency is the only lever (brief motivation — C4)
*Keep tight: one page max. This is motivation, not the contribution.*
- A language server's information is redundant for an agent that reads its own context. We summarize the evidence
  compactly (full protocol in appendix):
  - **Correction:** an oracle ladder (no feedback / synchronous diagnostics / perfect localization / gold fix) shows
    localization *harms* (p<0.001) and gold-fix does not beat no-feedback for a 7B; a 35B MoE ceilings the suite. The
    diagnostic adds nothing the model does not read.
  - **Completeness & scale:** varying repository size 21→86 files at a fixed generous read budget, success stays 1.00 at
    a flat ~6–8 reads — find-references does not earn its keep because reading does not become expensive at tractable
    scale.
  - **Navigation & prevention:** find-references is redundant on success (the agent reads the call graph when name
    search fails); prevention fails its precondition — the agent reads the library and never emits the hallucinated
    symbol, so there is nothing to prevent.
- **Scope (do not overclaim).** These nulls are consistent with redundancy but also with a ceiling/floor sandwich (the
  35B saturates; the 7B cannot act on any feedback), and they are measured on synthetic suites with oracle channels,
  never a real repo with ambiguous navigation. We therefore treat C4 as *motivation* — "on these suites the
  information channel does not help, so we ask what does" — not as a proven universal. The rest of the paper is about
  the one lever that remains: the *cost* of retrieval.
- TODO: a compact appendix table summarizing the four no-effect channels (demote from a main figure — it is the
  weakest claim and only motivation).

### 3. Setup
- Agent: 7B coding model (Qwen2.5-Coder-7B-Instruct) in a try-and-correct loop with `<read>`, `<defn>` (go-to-def),
  `<test>`, `<edit>` actions; real `pyrefly` type-checker; non-blocking stream harness. TODO: substrate + pyrefly cite.
- **`<defn>` is a real go-to-definition, not an oracle.** Given a symbol name the agent requests, the tool AST-resolves
  that symbol's top-level definition against the *live* workspace and returns its source span — exactly what an LSP
  go-to-def does, derived from the codebase with no privileged knowledge of which symbol or what the answer is; it
  returns "(no definition found)" on an unresolvable name (a real miss). **We validated this against a production
  language server:** driving a live `pyrefly lsp` daemon (JSON-RPC `textDocument/definition`) resolves all 12 effic
  symbols to the *same* definition as the static resolver (12/12, `scripts/validate_pyrefly_lsp.py`), and a proper run
  with `<defn>` backed by the live daemon (`--lsp-defn`) reproduces the headline (POST 0→100% use, 2894→689 tokens,
  58→100% success, ~4.2×). So the cheap action is a real go-to-definition — equal to pyrefly's, not a static-resolver
  artefact. (We use the static resolver for bulk runs — hermetic, validated-equal — and `--lsp-defn` to confirm
  live-server equivalence; the daemon is sequential-only.)
- The cost gap and tasks: the needed symbol's definition is buried in a ~370-line module; `<read>` returns the whole
  file (~3500 tokens), `<defn>` returns ~6 lines (~50 tokens) — same information, derived honestly, at a fraction of the
  cost. Tasks are non-guessable (idiomatic API guesses fail) so retrieval is genuinely required. The read-required
  family inverts this: the needed symbol is unknowable without reading, so `<defn>` cannot solve it (the boundary
  control).
- Metrics: go-to-definition use rate, tokens-to-solve, pass@1; paired exact McNemar on success and a paired token test;
  seen vs held-out task types.

### 4. Method: on-policy cost-aware imitation
- **The dominance argument.** Because `<read X>` and `<defn X>` return the same information, the minimum-cost action is
  always `<defn X>` when `<defn>` suffices — an AggreVaTe-style cost-to-go dominance. The "expert" is therefore a free
  deterministic read→defn relabel, not a model. **Scope of the oracle:** that dominance holds *only where `<defn>`
  covers the needed symbol*, and the relabel is applied exactly on the suite's definition-sufficient tasks — i.e. the
  coverage decision is supplied by the task labels, not learned. So the expert is "free" given coverage; discovering
  coverage in an unlabelled repo is out of scope here (see Limitations and the open items).
- **The on-policy round (DAgger round-0 — relabel the agent's own action).** Roll the *wild* agent out under the
  *deployment* prompt (both actions available). When it reaches for the expensive `<read>` of a non-editable file, the
  rule oracle redirects it; the agent then **picks `<defn>` itself** — its own symbol choice — and continues on-policy.
  We drop the read-attempt + redirect prefix from the trajectory and keep the agent's own definition-first continuation,
  so the trained first action from the clean deployment prompt is the agent's *own* go-to-definition. Mixed with
  read-first trajectories on the read-required tasks so the boundary is represented. LoRA fine-tune. This is genuine
  on-policy cost-aware imitation: no gold action is injected — we relabel only the *retrieval channel* of the agent's
  own behaviour. (An earlier pilot that teacher-forced `<defn>` as a lead token reached the same place; the relabel
  result below confirms the effect survives when the action is the agent's own, which is what earns the DAgger framing.)
- **Why on-policy is necessary** (the C3 mechanism, stated formally): offline cloning trains on the teacher's state
  distribution; the deployment distribution (expensive action available) is off-support, so the cloned policy is
  unconstrained exactly where the preference must be expressed. Ross & Bagnell compounding error; the cost-preference is
  a choice the offline data never demonstrates.

### 5. Results
- **5.1 The efficiency win (C1).** *Headline* (full mixed suite, real go-to-definition resolver, PRE untrained vs POST
  trained), definition-sufficient tasks, **n=48**: go-to-definition use **0→100%**, `<read>` use **42%→0%**, success
  **0.65→1.00** (McNemar p=1.5e-5, b=17/c=0), **mean tokens 3086→688 (4.5×), paired sign p=2.2e-4** (POST cheaper on
  37/48). The method is a genuine on-policy relabel of the agent's *own* retrieval — no gold action is injected. Two
  corroborating estimates of the same effect, labelled so they are not confused with the headline: (i) the *relabel-only
  retest* (the method in isolation) reproduces it — use 0→100%, tokens 3086→724 (4.3×), p=2.2e-4, n=48; (ii) a
  *teacher-forced lead-`<defn>` pilot* (12 seeds) reaches the same place — matched-outcome tokens 2108→675 (3.1×,
  p=2.7e-4, n=84), success 0.60→0.98 (McNemar p=6.2e-14, n=144). The pilot agreeing with the genuine relabel is how we
  know the effect is the *retrieval preference*, not an artefact of which action was forced. (The Summary's 3191→684,
  4.7× is a *third*, distinct number — the read-trained-vs-defn-trained isolation control at matched success, n=40 — not
  the headline.) Figure 1; one results table collecting all four numbers with their n and what each isolates.
- **5.1b Generalization (held-out).** The three definition-sufficient tasks never seen in the SFT harvest (queue, cache,
  clamp; n=12) behave like the trained ones: use 0→100%, success 0.42→1.00, tokens 3775→722 (5.2×). *Caveat (the honest
  scope):* these held-out tasks are the *same mechanism* as training (member/signature on a buried symbol), differing
  only in surface content — so this shows surface-transfer, not that the agent learned to *judge coverage*. A
  mechanism-distinct, surface-decoupled held-out test (where definition-sufficiency is not predictable from task shape)
  is the open item that would upgrade this claim (see open items).
- **5.1c Surface-decoupled test — attempted, RETRACTED (honest negative).** We built byte-identical-prompt pairs where
  `<defn target>` resolves to a full definition (A) or an uninformative stub (B), intending to test whether the agent
  *judges coverage from the return*. After hardening the suite to be non-guessable (arbitrary, non-inferable gold) and
  test-loop-proof (hash-only tests that give zero gradient on a miss), inspection showed the experiment **does not
  isolate coverage-judging**: the gold fix is to *delegate to the helper* — `return combine(args)` — which works
  identically from the full def (A) or the stub (B), because the helper resolves to the real implementation at runtime
  either way. Every trained-model solve (24/24 A, 21/21 B) delegates; none reimplements. So the agent never needs the
  retrieved body, and the A/B distinction never gates the fix. **What it does show (smaller):** the trained model
  delegates efficiently — one confirming `<defn>` then a call, ~100%/88% on A/B — where the untrained model
  reads/reimplements/thrashes (~50%); consistent with the efficiency story, but **not** evidence of coverage-judging.
  We therefore make no surface-keyed claim from this suite. **A second attempt** built a no-delegation suite whose fix
  must inline-transcribe an arbitrary multi-entry table (no callable to forward to) — but it *floored*: neither the base
  nor the trained 7B solves even variant A (0/18 and 3/18), where the full definition is handed over, so there is again
  no A-vs-B contrast to read. In removing the delegation escape we made the edit require transcribing arbitrary content,
  which the 7B's editing ability can't clear — the suite ends up gating on transcription, not coverage-judging. (The
  trained model does show the right *behaviour* on B — it escalates to a `<read>` on the stub — but can't produce the
  edit.) So the coverage-judging probe has now hit three distinct issues (guessability → delegation → difficulty floor);
  a clean version needs a stronger model that can transcribe, or a fix short enough that editing isn't the binding
  constraint. We leave it as future work. (This affects only this probe; the main results — efficiency isolation, the
  relabel, the real-LSP headline, the 27B transfer — use the effic suite, whose fixes genuinely require the retrieved
  API, and are unaffected.)
- **5.2 Non-degeneracy / the boundary (C2).** Read-required tasks: read rate stays 100%, success 0.58→0.79; on
  many-symbol tasks the agent reads once instead of issuing four go-to-definition calls (an economic choice). The model
  learned the boundary. Figure 3: use-rate by task type, PRE vs POST.
- **5.3 What fails (C3) — the baseline ladder.** Same task, four policies: default (2% use), explicit "prefer the LSP"
  prompt (still ~0–2%; 0% for a 35B), offline rejection-sampling on the cheap action (use ~0, tokens unchanged, though
  general success rises), on-policy imitation (100% use, ~4.5× tokens). One small table; one sentence of mechanism each.
  - *Cost-reward RL (GRPO) — an independent corroboration.* We also built and ran the token-cost RL alternative
    (group-sampled rollouts, reward = solve-at-min-tokens, group-normalized advantage, PG on the model's own action
    tokens; K=4 steps/round, G=8, λ=0.5, lr 1e-5). **It reaches the same cheap-retrieval operating point as the SFT
    relabel** — but it needs several on-policy rounds, not one. A single round *under-trains* and even regresses
    (use-defn 38%→6%, tokens 2048→3041); but across four rounds the policy converges monotonically on the harvest
    distribution (use-defn 37%→48%→86%, mean input tokens 2048→1740→790) and on a held-out clean retest the final
    adapter lands at **86% use-defn, 663 input tokens, 100% solved** (vs the wild baseline 38% / 2048 / 67%) — i.e. the
    independent RL signal arrives at essentially the SFT operating point (~100% defn, ~700 tokens). Two different training
    objectives — cost-aware imitation and a token-cost reward — instill the same preference, which is the result we'd
    want. (Caveat: needs ~3–4 rounds; single-round PG is a weak nudge; mild round-to-round oscillation; small retest n=36.)

### 6. Related work (methodological; verify every citation)
*Pre-2026 arXiv IDs verified 2026-06-20 (see docs/bibliography_efficiency.bib); the 2026 IDs (Revisiting-DAgger
arXiv:2605.12913; RLCSF arXiv:2510.22907) are pending PDF confirmation — do not ship as "verified" until checked.*
- On-policy distillation / imitation as the right tool for distribution shift: GKD (Agarwal et al., ICLR 2024,
  arXiv:2306.13649), DAgger (Ross, Gordon & Bagnell, AISTATS 2011), AggreVaTe cost-aware (Ross & Bagnell,
  arXiv:1406.5979), Revisiting-DAgger-for-LLM-Agents (Li et al., arXiv:2605.12913), and STaR (Zelikman et al.,
  "Bootstrapping Reasoning With Reasoning", arXiv:2203.14465) — the offline-cloning paradigm we contrast against.
- Cost-aware tool-use for LLM agents (the RL alternative we do not require): OTC-PO ("Acting Less is Reasoning More",
  Wang et al., arXiv:2504.14870) and IKEA (Huang et al., arXiv:2505.07596) reward fewer/cheaper tool calls with RL.
- **Closest prior work — LSP feedback for coding agents:** RLCSF ("Reinforcement Learning from Compiler and Language
  Server Feedback", Zhang et al., arXiv:2510.22907) *rewards* compiler/language-server diagnostics during RL.
  **Our positioning:** where RLCSF treats LSP feedback as a useful *signal* to reward, we show the LSP's *information*
  is redundant for a self-retrieving agent and that its sole residual value — retrieval *efficiency* — is a preference
  a lightweight on-policy imitation step instills where prompting and offline cloning cannot. We do not reward the
  tool; we train *when to call it*.

### 7. Limitations (honest)
- Token-magnitude and success are both significant on the pooled 12-seed sample: paired token test p=2.7e-4 (n=84,
  4.7× mean reduction), success McNemar p=6.2e-14 (n=144). (Earlier 4-seed sample was token-underpowered at p≈0.15;
  resolved by the extra-seed run.)
- **Cross-scale transfer (now shown).** The cost-preference training was originally 7B-only; we re-ran the *same*
  genuine relabel pipeline on **Qwen3.6-27B** (a different generation and a reasoning model) as a scale check: the wild
  27B is capable but reads-everything (0% go-to-definition, 96% read, 4058 tokens, 96% success), and the relabel flips
  it to **100% go-to-definition, 0% read, 100% success, 726 tokens — 5.5× cheaper at matched success** (n=24, adapter
  verified). So the preference is not a small-model artefact; the method transfers across a ~4× scale jump and a model-
  family change. *Caveat:* this is a lighter scale-check (2/4 seeds vs the 7B's 12), default thinking-on config, same
  definition-sufficient suite — robustness, not a fully-powered second headline.
- Synthetic tasks with a controlled cost gap; the read-required boundary covers two reasons a full read is needed
  (name-hidden, many-symbol), not all.
- `<defn>` is a real AST resolver over the live workspace (no oracle in the eval loop), but it is *hermetic* — a static
  resolver, not a running language-server client; deployment against a live `pyrefly` LSP daemon is unverified here
  (engineering, not a research gap — pyrefly is daemon-capable). (Note: the resolver retains an unused oracle-dict
  fallback in code; it is dead on every evaluation task, but should be removed before release to make "no oracle"
  literal.)
- **The boundary is, so far, supplied not discovered.** Definition-sufficiency is labelled by the task suite and used in
  the training mix; we show the preference is trainable *given* coverage, not that the agent learns to judge coverage on
  an unlabelled repo. This is the single largest scope limit (see open item 1).
- We instill the preference with on-policy SFT (DAgger round-0). We also built and ran the cost-reward RL alternative
  (GRPO) the cost-aware-tool-use literature offers: over ~4 on-policy rounds it converges to the same cheap-retrieval
  operating point (§5.3, clean retest 86% defn / 663 tokens / 100% solved), corroborating the SFT result via an
  independent objective. It is not cheaper to run (multi-round harvests vs one relabel pass), so SFT remains the
  headline recipe; GRPO is the corroboration, not a replacement.

### 8. Conclusion (the "so what")
- For agent builders: do not attach a language server expecting it to *inform* — a capable agent already reads what it
  would surface. Attach it for *retrieval efficiency*, and train the preference on-policy; prompting and offline
  demonstrations will not produce it.
- General form: any two actions returning the same information at different cost (index lookup vs document read,
  targeted API vs broad scrape) is the same problem with the same fix.

---

## Open TODOs
- [ ] Figure 1 (PRE/POST headline bars), Figure 2 (four no-effect channels), Figure 3 (use-rate by task type).
- [ ] One results table collecting the four token numbers (headline 3086→688/4.5×; relabel-only retest 724/4.3×; pilot
      matched-outcome 2108→675/3.1×; isolation control 3191→684/4.7×) with n and what each isolates.
- [ ] Verify the 2026 arXiv IDs (Revisiting-DAgger 2605.12913; RLCSF 2510.22907) against the PDFs before claiming
      "verified" in §6.
- [x] Path-B cost-RL (GRPO) DONE (2026-06-24): full 4-round run converges to the SFT operating point (clean retest 86%
      defn / 663 tokens / 100% solved); in-report as an independent corroboration of the relabel (§5.3). Single round
      under-trains (6% defn) — the convergence needs ~3–4 rounds.
- [ ] Title: pick between the working title and alternatives once Figure 1 is drawn.

---

## Reviewer pass v2 — open items for Ian (2026-06-21)

*The v2 adversarial + tech-writing review confirmed all four results HOLD: `<defn>` is a genuine AST resolver (no
oracle in the eval loop); efficiency is isolated from "retrieval helps success" (read-trained vs defn-trained at matched
outcome, 3191→684, p=6.8e-4); the relabel is genuine on-policy (the agent's own action, drop-prefix verified in
`stream_agent.py`); and the real-resolver headline reproduces (defn-suff 0→100% use, 3086→688, 4.5×, p=2.2e-4; success
0.65→1.00, McNemar p=1.5e-5; boundary read-rate stays 100%, success 0.54→0.83). The writing/scoping fixes it flagged are
applied above. What remains needs new runs or a decision — prioritized:*

1. **(Attempted twice, RETRACTED — honest open; see §5.1c) Surface-decoupled "judge coverage" test.** First build hit
   a *delegation* confound (gold fix `return helper(args)` works from stub or full def, so the body is never needed).
   Second build (2026-06-24) removed delegation — the fix must inline-transcribe an arbitrary table — but then *floored*:
   neither base nor trained 7B solves even variant A (0/18, 3/18), so there's no A-vs-B contrast; the suite ends up
   gating on transcription ability, not coverage-judging. Three distinct issues now (guessability → delegation →
   difficulty floor). The main story doesn't depend on this probe, so we leave it as an honest open and did not build a
   fourth iteration. **Open (your call):** a clean coverage test would need a stronger model that can transcribe (e.g.
   the 27B) or a fix short enough that the 7B's editing isn't the binding constraint — say the word if you want it.
2. **(DONE) A second model scale.** Ran Qwen3.6-27B: the relabel flips it 0→100% go-to-definition, 96→100% success,
   4058→726 tokens (5.5×, n=24) — the method transfers across a ~4× scale jump and a model-family/generation change.
   The 7B-only objection is answered (lighter scale-check seeds; see §Limitations). No further action unless a fully-
   powered 27B run is wanted.
3. **(DONE) Real pyrefly-LSP-client validation + proper run.** Built `scripts/validate_pyrefly_lsp.py` (live `pyrefly
   lsp` JSON-RPC client): `<defn>` resolves 12/12 to the same definition as a production language server. Also wired an
   opt-in `--lsp-defn` runtime path and ran the headline with `<defn>` backed by the live daemon — it reproduces (POST
   0→100% use, 2894→689 tokens, 58→100% success). So the cheap action is a real go-to-definition, validated against and
   working with pyrefly. (Daemon is sequential-only; default bulk path is the validated-equal static resolver.)
4. **(Partly DONE) Held-out reported separately.** Held-out (queue/cache/clamp) reported separately in §5.1b (0→100%
   defn, 0.42→1.00 success, 5.2× tokens). The *non-clone* held-out family = the surface-decoupled suite (§5.1c, item 1),
   which is done; the remaining gap is the guessability fix (item 1's open part), not a separate task.
5. **(DONE — converges, corroborates the SFT relabel) Path-B cost-RL (GRPO).** Built `scripts/grpo_cost.py` +
   `run_grpo.sh` (reward = solve-at-min-tokens, group-normalized advantage, PG on the model's own action tokens; 4
   rounds, K=4, G=8, λ=0.5, lr 1e-5). A **single** round under-trains and even regresses (use-defn 38%→6%, tokens
   2048→3041) — which is why the first probe read as a negative. But the **full 4-round run converges**: on the harvest
   distribution use-defn climbs 37%→48%→86% and mean input tokens fall 2048→1740→790, and the final adapter on a clean
   held-out retest (n=36, no force-LSP) lands at **86% use-defn / 663 input tokens / 100% solved** — essentially the SFT
   operating point (~100% defn, ~700 tokens). So an independent RL objective instills the same cheap-retrieval
   preference as the cost-aware imitation. It is *not* cheaper to run (multi-round harvests vs one relabel pass), so the
   SFT relabel stays the headline recipe and GRPO is the corroboration. Caveats: needs ~3–4 rounds; mild round-to-round
   PG oscillation; small retest n. Infra: `grpo_cost.py`, `run_grpo.sh`; trajectory in `log.md` (2026-06-24).

**Shippable core today:** C1 (isolated, powered efficiency win with a real resolver) + C2 (non-degenerate boundary) +
C3 (prompting/offline failure) at 7B on synthetic suites, with C4 scoped to motivation. Items 1 and 2 are what would
most raise external credibility; everything else above is writing cleanup already landed.

*(Credibility asset worth surfacing in §4 or a methods box: the boundary gate caught a data-pipeline bug — the
sft_lora filter dropping read trajectories — that would otherwise have produced a spurious always-defn collapse.)*
