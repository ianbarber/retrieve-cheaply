#!/usr/bin/env python3
"""RefactorBench -> internal task-dict loader + candidate filter.

Parses the microsoft/RefactorBench clone (problems/ + tests/ + the
scripts/<variant>_mapping.py join) into the SAME internal task schema the
synthetic suite uses, then filters to the subset that fits the <defn>-vs-<read>
efficiency experiment: small edits whose fix depends on a symbol that lives in a
LARGE, not-fully-shown file (the move / rename / relocate / cross-module shape).

PURE AST + TEXT. No pyrefly, no model, no Docker, no pip-install of the repos.
The RefactorBench AST test file IS the spec (scoring is static `ast.parse` +
structural assertions; see refactorbench_recon.md). We never import/run target
code and never spawn a language server here.

Internal task dict (superset of synth_mf.task_meta's fields):
  name, repo, repo_dir(abs), instruction, test_spec(abs path to the AST test),
  target_symbol, target_symbols, symbol_confidence, symbol_method, kind,
  is_cross_module, asserted_files, asserted_source_files, def_file,
  def_file_loc, biggest_referenced_file, biggest_referenced_loc,
  n_asserted_files, editable, shown, file_list, passes_filter, filter_reasons.

CLI:
  python scripts/real_repo_loader.py [--rb-root DIR] [--variant base]
      [--repos a,b,..] [--include-salt-ansible] [--include-tornado]
      [--max-asserted 3] [--min-big-loc 200] [--shown-max 260]
      [--all] [--out runs/real/refactorbench_candidates.json]
  -> prints the candidate table and writes the JSON.
"""
from __future__ import annotations
import os
import re
import ast
import sys
import json
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from scaffold.real_env import SymbolResolver  # AST-only; safe (no pyrefly)

DEFAULT_RB_ROOT = ("/tmp/claude-1000/-home-ianbarber-Projects-Streams/"
                   "4c20856c-b6b1-4797-847f-d0c62bde21b4/scratchpad/RefactorBench")

# repos that are conventional / statically analysable (recon section 6)
PREFERRED_REPOS = {"flask_refactor", "requests_refactor", "fastapi_refactor",
                   "celery_refactor", "django_refactor", "scrapy_refactor"}
DYNAMIC_REPOS = {"salt_refactor", "ansible_refactor"}   # excluded by default

IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
PY_PATH_RE = re.compile(r"""['"](\.\./)?([A-Za-z0-9_][A-Za-z0-9_./-]*\.py)['"]""")
TEST_DIR_RE = re.compile(r"(^|/)(tests?|t)/")   # project test trees (tests/, test/, t/)

# English words that survive the snake/Pascal "looks like code" sieve -> drop.
STOPWORDS = {
    "log", "True", "False", "None", "self", "py", "utils", "init", "main",
    "the", "and", "for", "all", "new", "old", "repo", "file", "class",
    "function", "method", "test", "tests", "import", "imports", "from",
    "into", "out", "base", "case", "make", "add", "move", "rename", "update",
    # generic instruction/test nouns + open()-mode / module noise that leak in
    "in", "inside", "that", "a", "an", "two", "it", "its", "select", "content",
    "everything", "outside", "within", "stray", "functions", "classes",
    "standalone", "parameter", "parameters", "boolean", "logging", "repository",
    "codebase", "usage", "usages", "reference", "references", "name", "names",
    "r", "w", "rb", "wb", "string", "typing", "regex", "labels", "json", "os",
    "sys", "ast", "unittest", "node", "tree", "this", "where", "which",
}


# --------------------------------------------------------------------------- #
# mapping parse
# --------------------------------------------------------------------------- #
def load_mapping(rb_root, variant):
    """Return {test_abs: task_abs} from scripts/<variant>_mapping.py.

    The mapping file is `file_mapping = {'../tests/...': '../problems/...'}`,
    paths relative to the scripts/ dir. We exec it and re-anchor each `../x`
    against rb_root (strip the leading `../`)."""
    mp = os.path.join(rb_root, "scripts", f"{variant}_mapping.py")
    ns: dict = {}
    with open(mp) as f:
        exec(f.read(), ns)
    fm = ns["file_mapping"]

    def anchor(p):
        return os.path.normpath(os.path.join(rb_root, p[3:] if p.startswith("../") else p))

    return {anchor(k): anchor(v) for k, v in fm.items()}


# --------------------------------------------------------------------------- #
# test-file feature extraction (asserted files + symbol candidates)
# --------------------------------------------------------------------------- #
def parse_test(test_path):
    """Return (asserted_rel_paths, test_symbol_candidates) from an AST test.

    asserted_rel_paths : repo-relative `.py` paths the test string-references
                         (`../src/requests/utils.py` -> `src/requests/utils.py`).
    test_symbol_candidates: identifier-shaped string constants the test checks
                         (these are the very names the refactor renames/moves;
                         frequency-ordered, light noise filter)."""
    src = open(test_path, encoding="utf-8", errors="replace").read()
    asserted, order = [], []
    for m in PY_PATH_RE.finditer(src):
        rel = m.group(2)
        if rel not in asserted:
            asserted.append(rel)
    # symbol candidates from string constants in the AST
    counts: dict = {}
    try:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value
                if (re.fullmatch(IDENT, s) and not s.endswith(".py")
                        and len(s) >= 3 and not s.startswith("__")
                        and s not in STOPWORDS):
                    counts[s] = counts.get(s, 0) + 1
                    if s not in order:
                        order.append(s)
    except SyntaxError:
        pass
    # frequency desc, then first-seen
    cands = sorted(order, key=lambda s: (-counts[s], order.index(s)))
    return asserted, cands


# --------------------------------------------------------------------------- #
# symbol extraction from the instruction (heuristic + confidence)
# --------------------------------------------------------------------------- #
def _idents(text):
    return re.findall(IDENT, text)


def _code_like(tok):
    if tok in STOPWORDS:
        return False
    if "_" in tok:
        return True                              # snake_case
    if re.search(r"[a-z][A-Z]", tok):
        return True                              # camelCase / PascalCase
    if re.search(r"[A-Za-z]", tok) and re.search(r"[0-9]", tok):
        return True                              # HTTP1Connection, EX_X1
    if re.fullmatch(r"[A-Z]{2,}", tok):
        return True                              # EX_CANTCREAT bits, NotSupported-ish
    return False


# verb-anchored captures: (regex, confidence, method-label). First match wins.
_VERB_PATTERNS = [
    (re.compile(r"[Rr]ename\s+(?:all\s+the\s+|the\s+)?"
                r"(?:helper\s+function|core\s+function|standalone\s+function|"
                r"function|class|method|exception|exitcode|file)?\s*"
                r"`?([A-Za-z_][\w.]*)"), "high", "rename"),
    (re.compile(r"[Mm]ove\s+(?:only\s+|all\s+the\s+|all\s+|the\s+)?"
                r"`?([A-Za-z_][\w.]*)"), "high", "move"),
    (re.compile(r"parameter\s+(?:in|to)\s+(?:the\s+)?`?([A-Za-z_][\w.]*)"), "high", "param"),
    (re.compile(r"to\s+(?:the\s+)?`?([A-Za-z_][\w.]*)\s+function"), "high", "param"),
    (re.compile(r"[Cc]ombine\s+(?:all\s+the\s+|the\s+)?`?([A-Za-z_][\w.]*)"), "med", "combine"),
    (re.compile(r"functions?\s+(?:named\s+|called\s+)?`?([A-Za-z_][\w.]*)"), "med", "function"),
    (re.compile(r"class\s+(?:named\s+|called\s+)?`?([A-Za-z_][\w.]*)"), "med", "class"),
]


def _slug_candidates(name):
    """snake_case-ish candidates from the task slug, e.g.
    'add-log-parameter-select-proxy' -> {'select_proxy','add_log_parameter_...'}.
    Built from contiguous lowercase hyphen-runs (drop leading add/log/param noise
    is impossible to know, so we yield every contiguous window joined by '_')."""
    parts = [p for p in name.split("-") if p]
    out = set()
    n = len(parts)
    for i in range(n):
        for j in range(i + 1, n + 1):
            if j - i >= 2:                    # need at least two words for a snake symbol
                out.add("_".join(parts[i:j]))
    return out


def extract_symbol(name, instruction, test_cands, repo_names):
    """Pick the (old) symbol the task moves/renames/parameterises.

    Strategy (most -> least confident):
      1. a verb-anchored identifier that the TEST also checks  -> high
      2. a verb-anchored identifier alone                      -> med/high
      3. an instruction code-like identifier in test_cands     -> high
      4. a slug-derived snake symbol in test/repo names        -> med
      5. the most-checked test symbol                          -> med
      6. first code-like identifier in the instruction         -> low
      7. nothing                                               -> low
    repo_names = set of identifiers actually defined in the repo subset (for
    cross-checking); may be empty (then we lean on test_cands).
    Returns (symbol, symbols_list, confidence, method)."""
    repo_set = set(repo_names)
    known = set(test_cands) | repo_set

    verb_heads = []
    for rx, conf, label in _VERB_PATTERNS:
        m = rx.search(instruction)
        if not m:
            continue
        sym = m.group(1).strip(".")
        sym = sym[:-3] if sym.endswith(".py") else sym
        head = sym.split(".")[-1]
        if head and head not in STOPWORDS and head not in verb_heads:
            verb_heads.append(head)

    instr_code = [t for t in _idents(instruction) if _code_like(t)]
    slug = sorted(_slug_candidates(name), key=len, reverse=True)

    def _secondary(chosen):
        # other named code symbols (e.g. the new class, or a 2nd moved function)
        return [t for t in (instr_code + test_cands) if t in known and t != chosen][:2]

    # We STRONGLY prefer a symbol that actually EXISTS in the repo subset: that is
    # the OLD function/class the agent must comprehend (a to-be-created class/file
    # has no definition to resolve), and the experiment cares about resolving it.
    # 1-4: existing symbol, by descending source reliability.
    for h in verb_heads:
        if h in repo_set:
            return h, [h] + _secondary(h), "high", "verb+repo"
    for t in instr_code:
        if t in repo_set:
            return t, [t] + _secondary(t), "high", "instr+repo"
    filt = [c for c in test_cands if c in repo_set]
    if filt:
        filt.sort(key=lambda c: (0 if _code_like(c) else 1, test_cands.index(c)))
        return filt[0], filt[:3], "high", "test+repo"
    for cand in slug:
        if cand in repo_set:
            return cand, [cand], "high", "slug+repo"
    # 5-7: no existing symbol identified -> the named NEW class/file, or a
    # test-checked name (lower confidence; won't resolve via <defn>).
    for h in verb_heads:
        if h in known:
            return h, [h] + _secondary(h), "med", "verb+test"
    for t in instr_code:
        if t in known:
            return t, [t] + _secondary(t), "med", "instr+test"
    tcode = [c for c in test_cands if _code_like(c)]
    if tcode:
        return tcode[0], tcode[:3], "med", "test"
    # 8-9: last resort
    for h in verb_heads:
        if _code_like(h):
            return h, [h], "low", "verb"
    if instr_code:
        return instr_code[0], instr_code[:3], "low", "instr"
    return None, [], "low", "none"


# --------------------------------------------------------------------------- #
# refactor-kind + cross-module classification
# --------------------------------------------------------------------------- #
def classify_kind(instruction):
    s = instruction.lower()
    if "new class" in s or "a new class" in s or "as a method for the class" in s:
        kind = "new-class"
    elif re.search(r"\.py to .*\.py|rename .*\.py", s):
        kind = "file-rename"
    elif "new file" in s or "newly created" in s or "a new file" in s or "new utils" in s:
        kind = "new-file"
    elif "rename" in s:
        kind = "rename"
    elif any(k in s for k in ("move", "take out", "out of the class", "outside of",
                              "put all that content", "put it all", "put that",
                              "relay import")):
        kind = "move"
    elif "combine" in s:
        kind = "combine"
    elif "split" in s:
        kind = "split"
    elif "parameter" in s and ("log" in s or "logging" in s):
        kind = "add-param"
    elif "into a new class" in s or "into a separate dataclass" in s or "encapsulate" in s:
        kind = "new-class"
    else:
        kind = "other"

    cross_kw = ("move", "rename", "relocate", "combine", "split", "new file",
                "new class", "take out", "outside of", "out of the class",
                "newly created", "new utils", "put it", "put all", "put that",
                "into a", "encapsulate")
    usage_kw = ("throughout the repo", "throughout the repository", "all references",
                "all the references", "all usages", "all calls", "all the calls",
                "all the usages", "update the repo", "update all", "update the entire",
                "all the other files", "references in the repo", "the codebase",
                "across the files")
    is_cross = any(k in s for k in cross_kw) or any(k in s for k in usage_kw)
    return kind, is_cross


# --------------------------------------------------------------------------- #
# per-task assembly
# --------------------------------------------------------------------------- #
def _loc(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def build_task(test_abs, task_abs, rb_root, shown_max):
    repo = os.path.basename(os.path.dirname(task_abs))            # e.g. requests_refactor
    name = os.path.basename(task_abs)
    name = name[:-len("-task.txt")] if name.endswith("-task.txt") else name
    repo_dir = os.path.join(rb_root, "repositories", repo)
    instruction = open(task_abs, encoding="utf-8", errors="replace").read().strip()

    asserted, test_cands = parse_test(test_abs)
    # split asserted into repo-existing source vs test/missing
    asserted_source, missing = [], []
    for rel in asserted:
        ap = os.path.join(repo_dir, rel)
        if not os.path.isfile(ap):
            missing.append(rel)
            continue
        if TEST_DIR_RE.search(rel) or os.path.basename(rel).startswith("test_"):
            continue
        asserted_source.append(rel)

    # resolve the symbol's def file over the asserted source subset (AST-only)
    files_dict = {}
    repo_names: set = set()
    for rel in asserted_source:
        try:
            with open(os.path.join(repo_dir, rel), encoding="utf-8", errors="replace") as f:
                src = f.read()
            files_dict[rel] = src
            tree = ast.parse(src)
            for node in ast.walk(tree):
                nm = getattr(node, "name", None)
                if nm:
                    repo_names.add(nm)
        except Exception:
            continue

    sym, syms, conf, method = extract_symbol(name, instruction, test_cands, repo_names)
    kind, is_cross = classify_kind(instruction)

    # def file (strict) + relaxed scan for the line range / big-file feature
    def_file, def_loc = None, 0
    if sym and files_dict:
        resolver = SymbolResolver(files_dict)
        span, rel = resolver.resolve(sym)
        if rel is None:                          # bare-method miss -> relaxed scan
            rel = _relaxed_def_file(files_dict, sym)
        if rel:
            def_file = rel
            def_loc = _loc(os.path.join(repo_dir, rel))

    # biggest referenced SOURCE file (the comprehension-target proxy)
    biggest_file, biggest_loc = None, 0
    for rel in asserted_source:
        loc = _loc(os.path.join(repo_dir, rel))
        if loc > biggest_loc:
            biggest_loc, biggest_file = loc, rel

    editable = list(asserted_source)
    locmap = {rel: _loc(os.path.join(repo_dir, rel)) for rel in editable}
    shown = [rel for rel in editable if locmap[rel] <= shown_max]
    if not shown and editable:                   # never show nothing
        shown = [min(editable, key=lambda r: locmap[r])]
    file_list = sorted(set(editable + ([def_file] if def_file else [])))

    return {
        "name": name, "repo": repo, "repo_dir": repo_dir,
        "instruction": instruction, "test_spec": test_abs,
        "target_symbol": sym, "target_symbols": syms,
        "symbol_confidence": conf, "symbol_method": method,
        "kind": kind, "is_cross_module": is_cross,
        "asserted_files": asserted,
        "asserted_source_files": asserted_source,
        "missing_or_test_asserts": missing,
        "def_file": def_file, "def_file_loc": def_loc,
        "biggest_referenced_file": biggest_file,
        "biggest_referenced_loc": biggest_loc,
        "n_asserted_files": len(asserted),
        "editable": editable, "shown": shown, "file_list": file_list,
        "test_symbol_candidates": test_cands[:6],
    }


def _relaxed_def_file(files_dict, sym):
    """Find ANY file defining a def/class/method/assign named `sym` (last dotted
    component). Returns relpath or None. Used only to locate the big def file for
    the feature columns (the strict resolver is what the agent's <defn> uses)."""
    head = sym.split(".")[-1]
    best = None
    for rel in sorted(files_dict):
        try:
            tree = ast.parse(files_dict[rel])
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                    and node.name == head:
                return rel
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == head:
                        best = best or rel
    return best


# --------------------------------------------------------------------------- #
# filter
# --------------------------------------------------------------------------- #
def passes(task, repos, max_asserted, min_big_loc):
    reasons = []
    if task["repo"] not in repos:
        reasons.append(f"repo:{task['repo']} not in preferred")
    if task["n_asserted_files"] > max_asserted:
        reasons.append(f"asserts {task['n_asserted_files']} files (>{max_asserted})")
    if task["biggest_referenced_loc"] < min_big_loc:
        reasons.append(f"biggest ref {task['biggest_referenced_loc']}L (<{min_big_loc})")
    if not task["is_cross_module"]:
        reasons.append("not move/rename/cross-module")
    if task["target_symbol"] is None:
        reasons.append("no symbol extracted")
    return (len(reasons) == 0), reasons


def load_candidates(rb_root=DEFAULT_RB_ROOT, variant="base", repos=None,
                    max_asserted=3, min_big_loc=200, shown_max=260):
    repos = repos or PREFERRED_REPOS
    mapping = load_mapping(rb_root, variant)
    tasks = []
    for test_abs, task_abs in sorted(mapping.items()):
        try:
            t = build_task(test_abs, task_abs, rb_root, shown_max)
        except Exception as e:                   # never let one bad task kill the run
            tasks.append({"name": os.path.basename(task_abs), "error": str(e),
                          "repo": os.path.basename(os.path.dirname(task_abs))})
            continue
        ok, reasons = passes(t, repos, max_asserted, min_big_loc)
        t["passes_filter"] = ok
        t["filter_reasons"] = reasons
        tasks.append(t)
    return tasks


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rb-root", default=os.environ.get("REFACTORBENCH_ROOT", DEFAULT_RB_ROOT))
    ap.add_argument("--variant", default="base", choices=["base", "descriptive", "lazy"])
    ap.add_argument("--repos", default=None, help="comma list of repo dirs to allow")
    ap.add_argument("--include-salt-ansible", action="store_true")
    ap.add_argument("--include-tornado", action="store_true")
    ap.add_argument("--max-asserted", type=int, default=3)
    ap.add_argument("--min-big-loc", type=int, default=200)
    ap.add_argument("--shown-max", type=int, default=260)
    ap.add_argument("--all", action="store_true", help="print every task, not just passers")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs/real/refactorbench_candidates.json"))
    A = ap.parse_args()

    if A.repos:
        repos = set(A.repos.split(","))
    else:
        repos = set(PREFERRED_REPOS)
        if A.include_salt_ansible:
            repos |= DYNAMIC_REPOS
        if A.include_tornado:
            repos.add("tornado_refactor")

    tasks = load_candidates(A.rb_root, A.variant, repos, A.max_asserted,
                            A.min_big_loc, A.shown_max)
    good = [t for t in tasks if t.get("passes_filter")]
    errs = [t for t in tasks if "error" in t]

    show = tasks if A.all else good
    show = sorted(show, key=lambda t: (t["repo"], -t.get("biggest_referenced_loc", 0)))
    print(f"\n{'NAME':40} {'REPO':10} {'#F':>3} {'BIG-LOC':>7} {'DEFLOC':>6} "
          f"{'KIND':10} {'CONF':4} {'SYMBOL':28} PASS")
    print("-" * 130)
    for t in show:
        if "error" in t:
            continue
        print(f"{t['name'][:40]:40} {t['repo'].replace('_refactor',''):10} "
              f"{t['n_asserted_files']:>3} {t['biggest_referenced_loc']:>7} "
              f"{t['def_file_loc']:>6} {t['kind'][:10]:10} {t['symbol_confidence'][:4]:4} "
              f"{str(t['target_symbol'])[:28]:28} {'Y' if t.get('passes_filter') else '-'}")

    # per-repo breakdown of passers
    by_repo: dict = {}
    for t in good:
        by_repo.setdefault(t["repo"].replace("_refactor", ""), 0)
        by_repo[t["repo"].replace("_refactor", "")] += 1
    print("\n== PASSED FILTER ==", len(good), "of", len(tasks), "tasks")
    print("   per-repo:", ", ".join(f"{k}:{v}" for k, v in sorted(by_repo.items())))
    if errs:
        print("   extraction errors:", ", ".join(t["name"] for t in errs))

    os.makedirs(os.path.dirname(A.out), exist_ok=True)
    with open(A.out, "w") as f:
        json.dump({"rb_root": A.rb_root, "variant": A.variant,
                   "filters": {"repos": sorted(repos), "max_asserted": A.max_asserted,
                               "min_big_loc": A.min_big_loc, "shown_max": A.shown_max},
                   "n_total": len(tasks), "n_passed": len(good),
                   "candidates": good, "all_tasks": tasks}, f, indent=2)
    print(f"-> {A.out}")


if __name__ == "__main__":
    main()
