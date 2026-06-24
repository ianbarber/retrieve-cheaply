#!/usr/bin/env python3
"""Continuous-stream coding agent with live (in-flight) LSP feedback — the v0.5
option-D apparatus. The agent generates ONE continuous token stream of reasoning
+ edits; depending on the condition, pyrefly diagnostics about completed edits are
delivered:
  A : never (no feedback)
  C : synchronously — generation PAUSES at the edit boundary, the diagnostic is
      injected, then generation resumes (production post-edit-hook / turn feedback)
  D : live/async — generation does NOT pause; the diagnostic is spliced into the
      stream `latency_tokens` AFTER the edit completes (the model sees it
      mid-work and must look back), exactly the prototype-validated KV splice.

Edit format the model emits (parsed live from the stream):
    <edit path="FILE">
    <<<<<<< SEARCH
    ...old...
    =======
    ...new...
    >>>>>>> REPLACE
    </edit>
and a final  <done/>  to stop.

The agent is environment-agnostic: it calls an env with
  read_file(path) -> str
  apply_edit(path, search, replace) -> (ok: bool, info: str)   # records rework
  pyrefly_diagnostics(path) -> str   # normalized "(sev,line,code,msg)" text, or ""
  run_tests() -> dict  (resolved: bool, ...)
  metrics() -> dict
"""
from __future__ import annotations
import re, ast, time, torch

# Robust SEARCH/REPLACE parser: the 7B inconsistently drops the <<<<<<</=======/>>>>>>>
# markers, so make them optional and terminate the replace at END / blank line / next
# action / EOS. Matches both the canonical aider block and the bare SEARCH/REPLACE form.
EDIT_RE = re.compile(
    r'(?:<<<<<<<\s*)?SEARCH\s*\n(?P<search>.*?)\n(?:END\s*\n)?(?:=======|REPLACE)\s*\n(?P<replace>.*?)'
    r'(?=\n\s*(?:END\b|>>>>>>>|<test\s*/>|<done\s*/>|SEARCH\b)|\Z)', re.S)
DONE_RE = re.compile(r'<done\s*/>')
TEST_RE = re.compile(r'<test\s*/>')
READ_RE = re.compile(r'<read\s+path="(?P<path>[^"]+)"\s*/>')   # gather repo context
GREP_RE = re.compile(r'<grep\s+q="(?P<q>[^"]+)"\s*/>')          # search the workspace (the agent's nav tool; navigation experiment)
# PULL LSP actions (efficiency-as-policy experiment): a CHEAP retrieval action the model can ELECT
# instead of reading whole files. Oracle-backed (resolved refs / definition from the gold task).
FINDREFS_RE = re.compile(r'<findrefs\s+sym="(?P<sym>[^"]+)"\s*/>')   # go-to-references: where is SYM used
DEFN_RE     = re.compile(r'<defn\s+sym="(?P<sym>[^"]+)"\s*/>')       # go-to-definition / hover: SYM's def+signature
# whole-file rewrite protocol — robust for single-function tasks (no SEARCH-match
# brittleness, no irrecoverable corruption: a bad rewrite is just rewritten).
REWRITE_RE = re.compile(r'<rewrite>\s*\n(?P<src>.*?)\n\s*</rewrite>', re.S)
NUMPREFIX_RE = re.compile(r'(?m)^\s*\d+\|\s?')   # strip accidental "  3| " file-view prefixes
# line-range edit: robust for weak models on big files (no string matching).
LINE_EDIT_RE = re.compile(
    r'<edit\s+path="(?P<path>[^"]+)"\s+lines="(?P<start>\d+)(?:\s*-\s*(?P<end>\d+))?"\s*>\s*\n'
    r'(?P<body>.*?)\n?\s*</edit>', re.S)   # END optional: accept lines="N" and lines="N-M"

def _strip_fences(s: str) -> str:
    """Drop a leading ```lang and trailing ``` the model often wraps code in, and
    any leftover NNN| line-number prefixes it copied from the numbered file view."""
    s = s.strip("\n")
    lines = s.split("\n")
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return NUMPREFIX_RE.sub("", "\n".join(lines))
DIAG_OPEN, DIAG_CLOSE = "\n‹diag›\n", "\n‹/diag›\n"
TEST_OPEN, TEST_CLOSE = "\n<test_result>\n", "\n</test_result>\n"

SYS = """You are a coding agent fixing a bug in a Python repository. The bug is in file
`{file}`, whose current contents are shown below. Work iteratively.

To EDIT, emit a block in EXACTLY this form (the SEARCH text must match the file verbatim and
be UNIQUE in it; change as few lines as you need — you choose the scope):

SEARCH
def foo(x):
    return x + 0
REPLACE
def foo(x):
    return x + 1
END

To READ another file for context, emit:  <read path="pkg/other.py"/>
After editing, emit <test/> to RUN THE TESTS; you will receive the results. If tests fail,
read the failure, make another SEARCH/REPLACE/END edit, and <test/> again — keep iterating
until they pass. A static analyzer may also surface diagnostics; use them to catch mistakes
early. Emit <done/> only once the tests pass. Reason briefly between actions."""

SYS_LINE = """You are a coding agent fixing a bug in a Python repository. The bug is in file
`{file}`, shown below with line numbers (`NNN| code`). Work iteratively.

To EDIT, replace a range of lines by emitting EXACTLY:
<edit path="{file}" lines="START-END">
<the new code for those lines, WITHOUT line-number prefixes>
</edit>
START-END are inclusive 1-based line numbers from the numbered view. Include proper
indentation. You choose the range — one line or many. Do not wrap the code in ``` fences.
To READ another file for context: <read path="pkg/other.py"/>
After editing, emit <test/> to RUN THE TESTS; you'll get the results, then a fresh numbered
view of the file (line numbers may have shifted — always use the latest view). Keep iterating:
edit -> <test/> -> fix -> <test/> until tests pass, then emit <done/>. Reason briefly between
actions. A static analyzer may also surface diagnostics; use them to catch mistakes early."""

SYS_LINE_MULTI = """You are a coding agent fixing a bug that SPANS MULTIPLE FILES in a Python
repository. The EDITABLE files are: {files}. Each is shown below with line numbers (`NNN| code`).
The same fix is likely needed in SEVERAL of them — you must fix EVERY affected site across all
the files, or the tests will still fail. Work iteratively.

To EDIT a file, emit EXACTLY:
<edit path="pkg/file.py" lines="START-END">
<the new code for those lines, WITHOUT line-number prefixes>
</edit>
Use the path of the file you are editing and ITS OWN 1-based line numbers from the numbered view.
After each edit you receive a fresh numbered view of every editable file (line numbers shift —
always use the latest view for the file you are editing). To READ a non-editable file for
context: <read path="pkg/other.py"/>. After your edits, emit <test/> to RUN THE TESTS; you'll get
the results. Keep iterating: edit the affected sites -> <test/> -> fix any remaining site ->
<test/> until tests pass, then emit <done/>. A static analyzer may also surface diagnostics naming
the files/lines still wrong — use them to find sites you missed. Reason briefly between actions."""

SYS_REWRITE = """You are a coding agent fixing a bug in file `{file}`. Work iteratively.
To EDIT, output the ENTIRE corrected file inside a rewrite block:

<rewrite>
def foo(x):
    return x + 1
</rewrite>

Then emit <test/> to RUN THE TESTS; you will receive the results. If they fail, read the
failure, output another COMPLETE <rewrite>...</rewrite> (the whole file), and <test/> again —
keep iterating until they pass. A static analyzer may also surface diagnostics mid-work; use
them to catch mistakes early. Output ONLY code inside <rewrite> — no line numbers, no markdown
fences. Emit <done/> only once the tests pass. Reason briefly between actions."""


class StreamAgent:
    def __init__(self, model, tok, env, condition="D", latency_tokens=8,
                 max_new_tokens=3000, max_tests=8, max_turns=12, max_bad=5,
                 max_reads=6, max_greps=8, edit_mode="search", temperature=0.0, seed=0,
                 debounce=0, pause_align=False, announce_lsp=False, c_eager=False,
                 syntax_gate=False, rich_signal=False, clean_delivery=False,
                 diag_filter=None, oracle_hint=None, steer_hint=None, lsp_oracle=None,
                 force_lsp=False, lead_defn=None, lead_read=None, relabel=False, device=None,
                 use_lsp_defn=False):
        assert condition in ("A", "C", "D")
        assert edit_mode in ("search", "rewrite", "line")
        self.temperature, self.seed = temperature, seed
        # D-delivery tuning: debounce>0 re-queries pyrefly only after the stream has
        # SETTLED `debounce` tokens since the last edit and (if pause_align) at a
        # newline — so transient self-inflicted squiggles the model already fixed are
        # never delivered, and delivery lands at a natural pause not mid-token.
        self.debounce, self.pause_align, self.announce_lsp = debounce, pause_align, announce_lsp
        self.c_eager = c_eager   # C: deliver the diagnostic immediately after each edit (post-edit hook) vs batched at the next yield
        self.syntax_gate = syntax_gate   # D: only deliver a live diagnostic when the file currently PARSES (suppress self-inflicted mid-edit syntax-error squiggles)
        self.rich_signal = rich_signal   # append go-to-def/hover-style context (signature/fields of the symbols the diagnostic names) to each delivered diagnostic
        self.clean_delivery = clean_delivery   # D: deliver the live diagnostic as a clean USER turn + file view (not a raw ‹diag› splice) — isolates delivery FORMAT from timing; avoids marker leakage
        self.diag_filter = diag_filter   # None | "type" | "syntax": deliver only cross-file TYPE errors, or only self-inflicted syntax/scope errors (mechanism decomposition)
        self.steer_hint = steer_hint     # appended to the system prompt: extra instruction steering the model to USE the diagnostics / READ the named file (tests whether the channel's value is latent-but-unelicited, i.e. a prompting gap vs a real null)
        self.oracle_hint = oracle_hint   # POSITIVE CONTROL: when set, the sync channel delivers this oracle string (perfect localization or the gold fix) IN PLACE OF the pyrefly diagnostic, but only while the file still has errors. Tests the ceiling of helpful feedback: if even this doesn't lift pass@1, the bottleneck is the model's ability to act, not feedback availability.
        self.model, self.tok, self.env = model, tok, env
        self.cond, self.latency = condition, latency_tokens
        self.max_new, self.max_tests, self.max_turns = max_new_tokens, max_tests, max_turns
        self.max_bad = max_bad   # bail after this many consecutive non-applying / no-op edits
        self.max_reads = max_reads
        self.max_greps = max_greps   # nav experiment: cap workspace searches (the agent's realistic find-refs alternative)
        self.lsp_oracle = lsp_oracle or {}   # efficiency-as-policy: {"refs": {sym:[paths]}, "defn": {sym:src}} backing the pull <findrefs>/<defn> actions
        self.force_lsp = force_lsp   # OPSD harvest: DENY <read> of non-editable files (forces the model onto <defn>/<findrefs>) -> manufactures the LSP-using trajectories to distill
        self.lead_defn = lead_defn   # DAgger round-0: inject <defn sym=lead_defn/> as the TRAINED first action (oracle's optimal action at the deployment-prompt state) -> clean defn-first trajectories with NO <read> to clone (the fix for the off-policy SFT that reinforced reading)
        self.lead_read = lead_read   # DAgger round-0 for READ-REQUIRED tasks: inject <read path=lead_read/> as the TRAINED first action -> clean read-first trajectories (the boundary half of the mixed SFT set: read when defn is insufficient)
        self.relabel = relabel   # GENUINE relabel (earns the DAgger framing, no teacher-forced action): roll out on-policy with force_lsp; when the model emits <read> of a non-editable file, MASK that turn's tokens in the SFT labels (the model's read-attempt) and redirect; the model then CHOOSES <defn sym=...> itself (picking the symbol) -> we train only on the model's own corrected behavior, not an injected gold action
        self.use_lsp_defn = use_lsp_defn   # OPT-IN: back <defn> with a LIVE pyrefly LSP daemon (env.lsp_definition) instead of the AST resolver (env.goto_definition). Validated to agree 12/12 on effic. SEQUENTIAL only (daemon deadlock risk) and falls back to the AST resolver on any LSP error.
        self.test_p2p_cap = 5    # in-loop <test/> caps P2P for speed; final resolved runs full
        self.edit_mode = edit_mode
        self.dev = device or model.device

    def _resolve_defn(self, sym):
        """REAL go-to-definition, oracle fallback. With use_lsp_defn, ask a LIVE pyrefly LSP daemon first
        (env.lsp_definition); otherwise (default) use the env's AST resolver over the live workspace (genuine
        LSP behavior — no gold knowledge). Either way fall back to the AST resolver, then the lsp_oracle dict."""
        if self.use_lsp_defn and hasattr(self.env, "lsp_definition"):
            src, _ = self.env.lsp_definition(sym)
            if src:
                return src
            # LSP miss/timeout: fall through to the AST resolver (never hang on the daemon)
        if hasattr(self.env, "goto_definition"):
            src, _ = self.env.goto_definition(sym)
            if src:
                return src
        return (self.lsp_oracle.get("defn") or {}).get(sym)

    def _resolve_refs(self, sym):
        if hasattr(self.env, "find_references"):
            refs = self.env.find_references(sym)
            if refs:
                return refs
        return (self.lsp_oracle.get("refs") or {}).get(sym)

    def _run_tests(self, cap=None):
        """Env-agnostic: TaskEnv accepts max_p2p; MockEnv doesn't."""
        try:
            return self.env.run_tests(max_p2p=cap) if cap is not None else self.env.run_tests()
        except TypeError:
            return self.env.run_tests()

    @staticmethod
    def _turn_obs(last_test, n_edits):
        if last_test is None:
            if n_edits == 0:
                return ("You have not edited the file yet. Make a SEARCH/REPLACE edit to fix "
                        "the bug, then emit <test/> to run the tests.")
            return "Run <test/> to check whether your edit fixed the tests."
        return ("Tests are still failing (see the result above). Make another SEARCH/REPLACE "
                "edit to fix the remaining problem, then <test/> again. If you cannot find the "
                "fix, re-read the failing assertion carefully.")

    @staticmethod
    def _fmt_test(tr):
        if tr.get("resolved"):
            return "ALL TESTS PASS."
        parts = [f"FAIL: F2P {tr.get('f2p_pass','?')}/{tr.get('f2p_total','?')}, "
                 f"P2P {tr.get('p2p_pass','?')}/{tr.get('p2p_total','?')}."]
        for k in ("f2p_summary", "p2p_summary", "failure", "f2p_output", "output"):
            v = tr.get(k)
            if v and isinstance(v, str):
                parts.append(v[:600])
        return "\n".join(parts)

    def _ids(self, text, special=False):
        return self.tok(text, return_tensors="pt", add_special_tokens=special).input_ids.to(self.dev)

    def _file_view(self, path):
        """Current file state, line-numbered — delivered each turn so the model can
        write SEARCH blocks that match (after its own edits the file has changed).
        Condition-NEUTRAL: identical across A/C/D; only the LSP channel differs."""
        try:
            src = self.env.read_file(path)
        except Exception:
            return ""
        lines = src.splitlines() or [""]
        if len(lines) > 250:   # degenerate bloat guard: never re-feed a runaway file in full
            shown = lines[:250]
            body = "\n".join(f"{i+1:>3}| {ln}" for i, ln in enumerate(shown))
            body += f"\n... (file has {len(lines)} lines; truncated — it has grown far beyond the original)"
        else:
            body = "\n".join(f"{i+1:>3}| {ln}" for i, ln in enumerate(lines))
        return f"Current `{path}` (edit against THIS exact text):\n{body}"

    @staticmethod
    def _fmt_diag(diag):
        """Normalize a diagnostics result to text. TaskEnv returns list[dict]
        {severity,line,code,message}; MockEnv returns a pre-formatted string."""
        if isinstance(diag, str):
            return diag
        if not diag:
            return ""
        lines = []
        for d in diag:
            if isinstance(d, dict):
                lines.append(f"[{d.get('severity','error')}] L{d.get('line','?')} "
                             f"{d.get('code','')}: {d.get('message','')}")
            elif isinstance(d, (tuple, list)) and len(d) >= 4:
                lines.append(f"[{d[0]}] L{d[1]} {d[2]}: {d[3]}")
            else:
                lines.append(str(d))
        return "\n".join(lines)

    def _enrich_diag(self, diag_text, src):
        """Go-to-def/hover-lite: pyrefly backticks the symbols it names; resolve each
        to its def/class in the current file and append the signature (+ a class's
        field lines). Constructive context, not just the error."""
        names = []
        for nm in re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", diag_text):
            if nm not in names:
                names.append(nm)
        lines = src.splitlines()
        ctx = []
        for nm in names[:5]:
            for i, ln in enumerate(lines):
                if re.match(rf"\s*(?:def|class)\s+{re.escape(nm)}\b", ln):
                    indent = len(ln) - len(ln.lstrip())
                    ctx.append(f"L{i+1}: {ln.strip()}")
                    if ln.lstrip().startswith("class"):
                        for j in range(i + 1, min(i + 8, len(lines))):
                            s = lines[j]
                            if s.strip() and (len(s) - len(s.lstrip())) > indent:
                                ctx.append(f"L{j+1}:   {s.strip()}")
                            elif s.strip():
                                break
                    break
        if ctx:
            diag_text += "\ndefinitions:\n" + "\n".join(ctx[:10])
        return diag_text

    # cross-file TYPE errors (the bug the task is "about") vs self-inflicted syntax/scope
    # errors created by the model's own brittle edits (everything else).
    TYPE_CODES = {"missing-argument", "bad-unpacking", "bad-typed-dict-key", "missing-attribute",
                  "bad-index", "unsupported-operation", "no-matching-overload", "bad-override",
                  "bad-assignment", "bad-argument-type"}

    def _filter_diag(self, text):
        """Keep only TYPE-code lines (diag_filter='type') or only non-TYPE/self-inflicted
        lines (diag_filter='syntax'). Lines look like '[error] [file] Lnn code: msg'."""
        if not self.diag_filter or not text:
            return text
        keep = []
        for ln in text.splitlines():
            m = re.search(r"L\d+\s+([\w-]+):", ln)
            code = m.group(1) if m else ""
            is_type = code in self.TYPE_CODES
            if (self.diag_filter == "type" and is_type) or (self.diag_filter == "syntax" and not is_type):
                keep.append(ln)
        return "\n".join(keep)

    def _diag_text(self, path):
        """Formatted (optionally filtered/enriched) current diagnostics for `path`."""
        d = self._filter_diag(self._fmt_diag(self.env.pyrefly_diagnostics(path)))
        if self.oracle_hint is not None:
            # oracle positive control: deliver the oracle hint while the file is still
            # broken (pyrefly fires), silent once fixed — same gating as a real diagnostic.
            return self.oracle_hint if d else ""
        if d and self.rich_signal:
            try:
                # enrich across the WHOLE workspace: the def the diagnostic names usually
                # lives in a REMOTE file, not `path` (the non-redundant-channel setting).
                # Scanning only the target made --rich-signal a no-op on rich tasks.
                src = "\n".join(self.env.read_file(f) for f in self.env.list_files())
                d = self._enrich_diag(d, src)
            except Exception:
                pass
        return d

    def _next_token(self, logits):
        if self.temperature and self.temperature > 0:
            probs = torch.softmax(logits.float() / self.temperature, dim=-1)
            return int(torch.multinomial(probs, 1))
        return int(logits.argmax(-1))

    def _prefill(self, input_ids, cache):
        with torch.no_grad():
            o = self.model(input_ids=input_ids, past_key_values=cache, use_cache=True)
        return o.logits[:, -1, :], o.past_key_values

    def run(self, task_prompt, target_file, editable=None):
        tok = self.tok
        # editable = the set of files the model may edit (default: just the target). >1 file ->
        # the multi-file / blast-radius setting (the bug spans files; completeness is the challenge).
        editable = editable or [target_file]
        # build the chat prompt; assistant stream is what we generate + parse
        if self.edit_mode == "line" and len(editable) > 1:
            sys_text = SYS_LINE_MULTI.format(files=", ".join(f"`{f}`" for f in editable))
        else:
            sys_tmpl = {"rewrite": SYS_REWRITE, "line": SYS_LINE}.get(self.edit_mode, SYS)
            sys_text = sys_tmpl.format(file=target_file)
        if self.announce_lsp and self.cond == "D":
            sys_text += ("\nA static type-checker runs continuously as you edit; its diagnostics "
                         "appear INLINE in your stream between ‹diag› and ‹/diag› markers a moment "
                         "after each edit. Treat them as live editor squigglies — when one appears, "
                         "fix the issue it names before moving on.")
        if self.steer_hint:
            sys_text += "\n" + self.steer_hint
        msgs = [{"role": "system", "content": sys_text},
                {"role": "user", "content": task_prompt}]
        # enable_thinking=False: Qwen3.x prefills an EMPTY <think></think> so the model answers
        # directly instead of emitting reasoning that would shred our tag-parsing and eat the token
        # budget. No-op for templates (e.g. Qwen2.5-Coder) that don't reference the variable.
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True,
                                         enable_thinking=False)
        cache = None
        prompt_ids = self._ids(prompt, special=True)
        logits, cache = self._prefill(prompt_ids, cache)
        in_toks = int(prompt_ids.shape[1])   # input tokens FED to the model (prompt + every observation/splice)

        emitted = ""          # decoded assistant stream so far
        out_ids = []
        out_labels = []       # parallel to out_ids: token id if MODEL-generated (train), -100 if spliced (observation)
        turn_start_tok = [0]  # out_ids index where the CURRENT model turn began
        relabel_keep_from = [None]  # --relabel: drop everything before this out_ids index from the SFT trace (the read-attempt + redirect prefix), so the model's own <defn> is trained as the first action from the clean prompt
        applied_upto = 0      # char index up to which edits are applied
        done_from = 0         # char index from which to look for <done/>
        test_from = 0         # char index from which to look for <test/>
        read_from = 0         # char index from which to look for <read/>
        grep_from = 0         # char index from which to look for <grep/>
        lsp_from = 0          # char index from which to look for <findrefs/>/<defn/>
        n_tests = n_edits = n_reads = n_greps = n_lsp = turns = 0
        fail_streak = 0       # consecutive non-applying / no-op edits (anti-degeneracy)
        changed_files = set()  # files edited since the last turn -> re-show their numbered view (per-file, multi-file safe)
        done_seen = resolved = bailed = False
        last_test = None
        pending = []          # D (immediate): in-flight diag spliced mid-stream (the live channel)
        d_dirty_at = None     # D (debounced): token index of the last edit; re-query after settle
        d_last_delivered = "" # D (debounced): avoid re-splicing an unchanged diagnostic
        c_diag_queue = []     # C: diags delivered as the next USER observation (sync, turn-boundary)
        events = []           # trajectory log
        eos = tok.eos_token_id

        def deliver_turn(obs_text):
            """End the assistant turn, give an observation as a USER message, start a
            new assistant turn. Tool results / sync feedback go here (not raw-spliced
            into the assistant stream — chat models parrot in-stream content). The
            current file view is appended so SEARCH blocks match the live file."""
            nudge = ""
            if fail_streak > 0:
                if self.edit_mode == "line":
                    nudge = ("\n[Your last edit did NOT apply (bad line range or format). Use line "
                             "numbers from the CURRENT numbered view below: "
                             "<edit path=\"...\" lines=\"START-END\"> then the new code (no ``` "
                             "fences, no NNN| prefixes) then </edit>.]")
                else:
                    nudge = ("\n[Your last edit did NOT apply. The SEARCH text must be copied "
                             "VERBATIM from the current file below — exact whitespace, no `END` "
                             "line inside SEARCH. Use one block: SEARCH / lines / REPLACE / lines / END.]")
            # re-show the numbered view of every file EDITED since the last turn (fresh line numbers
            # for follow-up edits). changed_files is mutated in place -> no nonlocal needed.
            fv = "\n\n".join(self._file_view(f) for f in sorted(changed_files)) if changed_files else ""
            changed_files.clear()
            body = obs_text + nudge + ("\n\n" + fv if fv else "")
            splice("<|im_end|>\n<|im_start|>user\n" + body + "<|im_end|>\n<|im_start|>assistant\n")

        def splice(text):
            nonlocal logits, cache, emitted, out_ids, in_toks
            ids = self._ids(text, special=False)
            in_toks += int(ids.shape[1])    # spliced observations/diagnostics/turn-scaffold = INPUT tokens
            logits, cache = self._prefill(ids, cache)
            out_ids.extend(ids[0].tolist())
            out_labels.extend([-100] * ids.shape[1])   # spliced = observation = masked for SFT
            turn_start_tok[0] = len(out_ids)            # a new model turn begins after this observation
            emitted = tok.decode(out_ids)   # full faithful decode (per-token concat mangles markers)

        # DAgger round-0 lead action: teacher-force the oracle's optimal first action <defn sym/> as a
        # TRAINED token, deliver its (masked) result, then let the model continue on-policy. Produces clean
        # "deployment-prompt -> defn -> solve" trajectories with NO <read> for SFT to clone.
        if self.lead_defn:
            sym = self.lead_defn
            act = f'<defn sym="{sym}"/>'
            ids = self._ids(act, special=False)
            in_toks += int(ids.shape[1])
            logits, cache = self._prefill(ids, cache)
            out_ids.extend(ids[0].tolist()); out_labels.extend(ids[0].tolist())   # TRAINED (the model's "action")
            emitted = tok.decode(out_ids)
            n_lsp += 1
            defn = self._resolve_defn(sym)
            events.append({"tok": 0, "type": "defn", "n": n_lsp, "sym": sym, "found": bool(defn), "lead": True})
            turns += 1
            deliver_turn(f'<defn sym="{sym}">\n' + (defn or "(no definition found)") + "\n</defn>")
            read_from = grep_from = lsp_from = test_from = done_from = applied_upto = len(emitted)

        # DAgger round-0 for READ-REQUIRED tasks: lead with <read path/> as the TRAINED first action -> clean
        # read-first trajectories (the boundary half: the model must read when <defn> is insufficient).
        if self.lead_read:
            rpath = self.lead_read
            ids = self._ids(f'<read path="{rpath}"/>', special=False)
            in_toks += int(ids.shape[1])
            logits, cache = self._prefill(ids, cache)
            out_ids.extend(ids[0].tolist()); out_labels.extend(ids[0].tolist())   # TRAINED
            emitted = tok.decode(out_ids)
            n_reads += 1
            try:
                content = self.env.read_file(rpath)
                view = content if len(content) <= 16000 else content[:16000] + "\n... (truncated)"
                obs = f'<file path="{rpath}">\n{view}\n</file>'
            except Exception as e:
                obs = f"Could not read {rpath}: {type(e).__name__}: {e}"
            events.append({"tok": 0, "type": "read", "n": n_reads, "path": rpath, "lead": True})
            turns += 1
            deliver_turn(obs)
            read_from = grep_from = lsp_from = test_from = done_from = applied_upto = len(emitted)

        if self.temperature and self.temperature > 0:
            torch.manual_seed(self.seed)
        t = 0
        CTX_CAP = 24000   # hard context cap (model max 32768): bail before indexing errors
        while t < self.max_new:
            if len(out_ids) + int(prompt_ids.shape[1]) > CTX_CAP:
                bailed = True
                events.append({"tok": t, "type": "bail", "reason": "context_overflow"})
                break
            nxt = self._next_token(logits)
            if nxt == eos:
                # EOS = end of THIS turn, not necessarily the task. Continue into a
                # new turn with an observation, unless done/resolved/turn-capped.
                if done_seen or resolved or turns >= self.max_turns:
                    break
                turns += 1
                obs = self._turn_obs(last_test, n_edits)
                if self.cond == "C" and c_diag_queue:
                    obs = "Static analysis after your edits:\n" + "\n".join(c_diag_queue) + "\n" + obs
                    c_diag_queue = []
                deliver_turn(obs)
                events.append({"tok": t, "type": "turn", "n": turns, "via": "eos"})
                if self.cond == "D" and pending:   # live diag spliced into the new assistant turn
                    for _, diag in pending:
                        if diag:
                            splice(DIAG_OPEN + diag + DIAG_CLOSE)
                            events.append({"tok": t, "type": "diag_async", "ondone": True, "text": diag})
                    pending = []
                continue
            out_ids.append(nxt)
            out_labels.append(nxt)   # model-generated action token = trained for SFT
            t += 1
            # advance one token
            logits, cache = self._prefill(torch.tensor([[nxt]], device=self.dev), cache)
            emitted = tok.decode(out_ids)   # full faithful decode each step (markers intact)

            # D (immediate): deliver any pending diagnostics whose latency has elapsed
            if self.cond == "D" and self.debounce == 0 and pending:
                due = [d for d in pending if t >= d[0]]
                for d in due:
                    pending.remove(d)
                    if d[1]:
                        splice(DIAG_OPEN + d[1] + DIAG_CLOSE)
                        events.append({"tok": t, "type": "diag_async", "text": d[1]})

            # D (debounced): after the stream settles `debounce` tokens past the last
            # edit, re-query CURRENT diagnostics (transient self-inflicted ones the model
            # already fixed are gone) and deliver at a pause; only if changed.
            if self.cond == "D" and self.debounce > 0 and d_dirty_at is not None:
                settled = t - d_dirty_at >= self.debounce
                at_pause = (not self.pause_align) or emitted.endswith(("\n", " ", ".", ":")) \
                           or (t - d_dirty_at >= self.debounce * 3)
                # syntax-gate: if the file is mid-edit/unparseable, DEFER (don't deliver a
                # self-inflicted syntax squiggle); retry once the model makes it parse again.
                gated = False
                if settled and at_pause and self.syntax_gate:
                    try:
                        ast.parse(self.env.read_file(target_file))
                    except Exception:
                        gated = True
                        d_dirty_at = t   # reset settle timer; retry when parseable
                if settled and at_pause and not gated:
                    diag = self._diag_text(target_file)
                    if diag and diag != d_last_delivered:
                        if self.clean_delivery:
                            # live timing, CLEAN format: deliver as a user turn + file view
                            # (no raw ‹diag› markers in the assistant stream -> no leakage)
                            fv = self._file_view(target_file)
                            body = "Static analysis:\n" + diag + ("\n\n" + fv if fv else "")
                            splice("<|im_end|>\n<|im_start|>user\n" + body +
                                   "<|im_end|>\n<|im_start|>assistant\n")
                        else:
                            splice(DIAG_OPEN + diag + DIAG_CLOSE)
                        d_last_delivered = diag
                        events.append({"tok": t, "type": "diag_debounced",
                                       "clean": self.clean_delivery, "text": diag})
                    d_dirty_at = None

            # detect a newly-completed whole-file rewrite (rewrite mode)
            if self.edit_mode == "rewrite":
                rm = REWRITE_RE.search(emitted, applied_upto)
                if rm:
                    applied_upto = rm.end()
                    src = NUMPREFIX_RE.sub("", rm["src"])
                    res = self.env.rewrite_file(src)
                    ok = res[0] if isinstance(res, tuple) else res.ok
                    if ok: n_edits += 1; fail_streak = 0
                    else: fail_streak += 1
                    events.append({"tok": t, "type": "rewrite", "ok": ok, "fail_streak": fail_streak})
                    if fail_streak >= self.max_bad:
                        bailed = True; events.append({"tok": t, "type": "bail", "reason": "rewrite_fail_streak"}); break
                    if self.cond in ("C", "D") and ok:
                        diag = self._diag_text(target_file)
                        if self.cond == "C" and diag:
                            c_diag_queue.append(diag)
                            events.append({"tok": t, "type": "diag_sync_queued", "text": diag})
                        elif self.cond == "D" and diag:
                            pending.append((t + self.latency, diag))
                            events.append({"tok": t, "type": "diag_pending", "text": diag})

            # detect a newly-completed line-range edit (line mode)
            if self.edit_mode == "line":
                lm = LINE_EDIT_RE.search(emitted, applied_upto)
                if lm:
                    applied_upto = lm.end()
                    body = _strip_fences(lm["body"])
                    epath, s = lm["path"], int(lm["start"])
                    e = int(lm["end"]) if lm["end"] else s
                    if hasattr(self.env, "apply_line_edit"):
                        res = self.env.apply_line_edit(epath, s, e, body)
                        ok = res.ok if hasattr(res, "ok") else res[0]
                        info = res.reason if hasattr(res, "reason") else (res[1] if isinstance(res, tuple) else "")
                    else:
                        ok, info = False, "line edits unsupported by env"
                    if ok: n_edits += 1; fail_streak = 0
                    else: fail_streak += 1
                    if ok: changed_files.add(epath)
                    events.append({"tok": t, "type": "line_edit", "path": epath, "lines": f"{s}-{e}",
                                   "ok": ok, "info": str(info)[:80], "fail_streak": fail_streak,
                                   "replace": body[:300]})   # prevention metric: scan for hallucinated symbols
                    if fail_streak >= self.max_bad:
                        bailed = True; events.append({"tok": t, "type": "bail", "reason": "edit_fail_streak"}); break
                    if self.cond == "D" and self.debounce > 0 and ok:
                        d_dirty_at = t   # settle timer; re-query at delivery (debounced)
                    elif self.cond in ("C", "D") and ok:
                        diag = self._diag_text(epath)
                        if self.cond == "C" and diag:
                            if self.c_eager:
                                turns += 1
                                deliver_turn("Static analysis after your edit:\n" + diag)
                                events.append({"tok": t, "type": "diag_eager", "text": diag})
                                continue   # eager post-edit hook: yield right after the edit
                            c_diag_queue.append(diag)
                            events.append({"tok": t, "type": "diag_sync_queued", "text": diag})
                        elif self.cond == "D" and diag:
                            pending.append((t + self.latency, diag))
                            events.append({"tok": t, "type": "diag_pending", "text": diag})

            # detect a newly-completed edit (search/replace mode)
            m = EDIT_RE.search(emitted, applied_upto) if self.edit_mode == "search" else None
            if m:
                applied_upto = m.end()
                noop = m["search"].strip() == m["replace"].strip()
                if noop:
                    ok, info = False, "no-op (search == replace)"
                else:
                    res = self.env.apply_edit(target_file, m["search"], m["replace"])
                    ok = res[0] if isinstance(res, tuple) else res.ok
                    info = (res[1] if isinstance(res, tuple) else res.reason)
                if ok: n_edits += 1; fail_streak = 0
                else: fail_streak += 1
                if ok: changed_files.add(target_file)
                events.append({"tok": t, "type": "edit", "path": target_file, "ok": ok,
                               "info": str(info)[:80], "fail_streak": fail_streak,
                               "replace": m["replace"][:300]})   # prevention metric: scan for hallucinated symbols
                if fail_streak >= self.max_bad:
                    bailed = True
                    events.append({"tok": t, "type": "bail", "reason": "edit_fail_streak"})
                    break
                if self.cond in ("C", "D") and ok:
                    diag = self._diag_text(target_file)
                    if self.cond == "C" and diag:
                        # sync: queue for the next USER observation (turn boundary)
                        c_diag_queue.append(diag)
                        events.append({"tok": t, "type": "diag_sync_queued", "text": diag})
                    elif self.cond == "D" and diag:
                        # live: splice into the assistant stream latency_tokens later
                        pending.append((t + self.latency, diag))

            # detect <test/> -> run tests, splice results back (the try-and-correct
            # loop; all conditions get test feedback — only LSP delivery differs)
            tm = TEST_RE.search(emitted, test_from)
            if tm and n_tests < self.max_tests:
                test_from = tm.end()
                n_tests += 1
                tr = self._run_tests(cap=self.test_p2p_cap)
                last_test = tr; resolved = bool(tr.get("resolved"))
                events.append({"tok": t, "type": "test", "n": n_tests, "resolved": resolved})
                obs = "<test_result>\n" + self._fmt_test(tr) + "\n</test_result>"
                if resolved:
                    obs += "\nTests pass — emit <done/> if the fix is complete."
                elif self.cond == "C" and c_diag_queue:
                    obs += "\nStatic analysis after your edits:\n" + "\n".join(c_diag_queue)
                    c_diag_queue = []
                turns += 1
                deliver_turn(obs)
                events.append({"tok": t, "type": "turn", "n": turns, "via": "test"})
                continue

            # detect <read path="..."/> -> deliver that file's contents (gather repo
            # context). Blocking in all conditions (you can't continue without it).
            rdm = READ_RE.search(emitted, read_from)
            if rdm and n_reads < self.max_reads:
                rpath = rdm["path"]
                # OPSD harvest: deny reads of non-editable files -> force the model onto <defn>/<findrefs>.
                # Kept under the DEPLOYMENT prompt (read still advertised) so harvested trajectories match
                # the distribution the distilled student is later evaluated in.
                if self.force_lsp and rpath not in editable:
                    read_from = rdm.end()
                    avail = list((self.lsp_oracle.get("defn") or {}).keys())
                    eg = avail[0] if avail else "Account"
                    listing = (" Symbols you can query: " + ", ".join(avail) + ".") if avail else ""
                    obs = (f"Reading `{rpath}` is disabled (large file — costly to load in full). To see a "
                           f"symbol's definition/signature emit <defn sym=\"<the symbol name>\"/> "
                           f"(for example <defn sym=\"{eg}\"/>), or <findrefs sym=\"<the symbol name>\"/> "
                           f"to find where it is used.{listing}")
                    turns += 1
                    deliver_turn(obs)
                    # The redirect obs CONTAINS literal self-closing <defn .../>/<findrefs .../> examples ("for example
                    # <defn sym=\"Account\"/>"). Those match DEFN_RE/FINDREFS_RE, so we MUST advance the action-search
                    # cursors past the spliced obs — otherwise the next search fires on the redirect's EXAMPLE tags
                    # instead of the model's OWN action, and the model is never required to emit <defn> itself (it just
                    # emits filler and the examples auto-resolve). That silently breaks the relabel harvest: the model's
                    # <defn> would never be trained. Cursors are char offsets into `emitted`, refreshed inside splice().
                    read_from = grep_from = lsp_from = len(emitted)
                    # GENUINE relabel (proper DAgger): the model chose to <read> at this state; the rule oracle redirects
                    # it to the cost-dominant <defn>, which the model now picks ITSELF (its own symbol choice). We DROP the
                    # read-attempt + redirect PREFIX from the SFT trace entirely (not just mask its labels) so the model's
                    # own <defn> action is trained as the FIRST action from the CLEAN prompt state — the fix for the
                    # masked-prefix variant, which left the read+redirect in context and never trained <defn>-from-prompt.
                    if self.relabel:
                        relabel_keep_from[0] = len(out_ids)   # = turn_start_tok after the redirect (start of the model's defn turn)
                    events.append({"tok": t, "type": "read_blocked", "path": rpath})
                    continue
                read_from = rdm.end(); n_reads += 1
                try:
                    if len(editable) > 1:
                        # multi-file: hand back a NUMBERED view so a DISCOVERED file is immediately
                        # editable with <edit path=... lines=...> (partial-visibility / find-refs setting).
                        obs = self._file_view(rpath)
                    else:
                        content = self.env.read_file(rpath)
                        view = content if len(content) <= 16000 else content[:16000] + "\n... (truncated)"
                        obs = f"<file path=\"{rpath}\">\n{view}\n</file>"
                except Exception as e:
                    obs = f"Could not read {rpath}: {type(e).__name__}: {e}"
                turns += 1
                deliver_turn(obs)
                events.append({"tok": t, "type": "read", "n": n_reads, "path": rpath})
                continue

            # detect <grep q="..."/> -> substring-search the workspace (the agent's realistic
            # navigation tool; the nav experiment turns on whether re-export aliasing defeats it).
            gm = GREP_RE.search(emitted, grep_from)
            if gm and n_greps < self.max_greps:
                grep_from = gm.end(); n_greps += 1
                q = gm["q"]
                hits = []
                try:
                    for fp in self.env.list_files():
                        try: src = self.env.read_file(fp)
                        except Exception: continue
                        for i, ln in enumerate(src.splitlines(), 1):
                            if q in ln:
                                hits.append(f"{fp}:{i}: {ln.strip()[:120]}")
                                if len(hits) >= 50: break
                        if len(hits) >= 50: break
                    obs = (f"<grep q=\"{q}\">\n" + ("\n".join(hits) if hits else "(no matches)") +
                           ("\n... (truncated at 50)" if len(hits) >= 50 else "") + "\n</grep>")
                except Exception as e:
                    obs = f"grep failed: {type(e).__name__}: {e}"
                turns += 1
                deliver_turn(obs)
                events.append({"tok": t, "type": "grep", "n": n_greps, "q": q, "hits": len(hits)})
                continue

            # PULL LSP actions: <findrefs sym=.../> (go-to-references) and <defn sym=.../> (go-to-def/hover).
            # Oracle-backed, CHEAP (a few lines) vs reading whole files — the efficiency-as-policy lever.
            frm = FINDREFS_RE.search(emitted, lsp_from)
            dfm = DEFN_RE.search(emitted, lsp_from)
            lm2 = min([x for x in (frm.start() if frm else None, dfm.start() if dfm else None) if x is not None], default=None)
            if lm2 is not None:
                if frm and frm.start() == lm2:
                    lsp_from = frm.end(); n_lsp += 1; sym = frm["sym"]
                    refs = self._resolve_refs(sym)
                    obs = (f"<findrefs sym=\"{sym}\">\n" +
                           ("\n".join(refs) if refs else "(no references found)") + "\n</findrefs>")
                    events.append({"tok": t, "type": "findrefs", "n": n_lsp, "sym": sym, "hits": len(refs or [])})
                else:
                    lsp_from = dfm.end(); n_lsp += 1; sym = dfm["sym"]
                    defn = self._resolve_defn(sym)
                    obs = (f"<defn sym=\"{sym}\">\n" + (defn if defn else "(no definition found)") + "\n</defn>")
                    events.append({"tok": t, "type": "defn", "n": n_lsp, "sym": sym, "found": bool(defn)})
                turns += 1
                deliver_turn(obs)
                continue

            dm = DONE_RE.search(emitted, done_from)
            if dm:
                done_from = dm.end()
                done_seen = True
                # In D, a 'done' while a diagnostic about the last edit is still in
                # flight: deliver it live and let the model react before stopping
                # (the "I'm done — oh wait, a squiggle appeared" case). Only truly
                # stop once done AND nothing pending.
                if self.cond == "D" and pending:
                    for dl, diag in pending:
                        if diag:
                            splice(DIAG_OPEN + diag + DIAG_CLOSE)
                            events.append({"tok": t, "type": "diag_async", "ondone": True, "text": diag})
                    pending = []
                    continue
                break

        # flush any straggler D diagnostics (info content matched vs C), recorded
        for _, diag in pending:
            if diag:
                splice(DIAG_OPEN + diag + DIAG_CLOSE)
                events.append({"tok": t, "type": "diag_async", "flushed": True, "text": diag})

        result = self._run_tests(cap=None)   # authoritative: full F2P + full P2P
        prompt_list = prompt_ids[0].tolist()
        # --relabel (proper DAgger): drop the read-attempt + redirect PREFIX so the model's own <defn> action is the
        # first trained action conditioned on the CLEAN prompt (not on a read+redirect that never occurs at deployment).
        keep = relabel_keep_from[0] if (self.relabel and relabel_keep_from[0] is not None) else 0
        kept_ids, kept_labels = out_ids[keep:], out_labels[keep:]
        sft_input_ids = prompt_list + kept_ids
        sft_labels = [-100] * len(prompt_list) + kept_labels   # prompt masked; train only on model actions
        return {"condition": self.cond, "resolved": result.get("resolved"),
                "bailed": bailed, "tests": result, "metrics": self.env.metrics(),
                "events": events, "stream": emitted,
                "out_tokens": t, "in_tokens": in_toks, "n_tokens": t,
                "n_edits": n_edits, "n_tests": n_tests, "n_reads": n_reads, "n_greps": n_greps, "n_lsp": n_lsp, "turns": turns,
                "sft_input_ids": sft_input_ids, "sft_labels": sft_labels,
                "n_train_tokens": sum(1 for x in kept_labels if x != -100)}
