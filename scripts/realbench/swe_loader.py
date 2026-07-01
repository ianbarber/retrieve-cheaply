#!/usr/bin/env python3
"""SWE-bench task loader for the real-repo generalization experiment (docs/real_repo_plan.md).

Loads SWE-bench Verified tasks, keeps a per-repo blobless clone cache, checks a task out at its
base_commit, applies the task's test_patch (which adds the FAIL_TO_PASS/PASS_TO_PASS oracle tests),
and builds the pytest command over the oracle node ids. The selection scan (select.py) uses only the
checkout + gold-patch parsing (no dependency install); running the tests for S4/S5 and the matrix needs
the task's environment (official SWE-bench Docker image), wired separately.

Repo clones live under runs/realbench/repos/ (gitignored, large). Network + git required.
"""
import os
import re
import sys
import json
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_CACHE = os.path.join(ROOT, "runs", "realbench", "repos")
DATASET = "princeton-nlp/SWE-bench_Verified"


def load_tasks(n=None, repos=None, offset=0):
    """Yield SWE-bench Verified task dicts (optionally the first n, a repo subset, from an offset)."""
    os.environ.setdefault("HF_HUB_OFFLINE", "0")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "0")
    from datasets import load_dataset
    ds = load_dataset(DATASET, split="test", streaming=True)
    i = -1
    yielded = 0
    for ex in ds:
        i += 1
        if i < offset:
            continue
        if repos and ex["repo"] not in repos:
            continue
        yield ex
        yielded += 1
        if n is not None and yielded >= n:
            return


def _run(cmd, cwd=None, timeout=600):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def ensure_clone(repo):
    """Blobless partial clone of github.com/<repo> into the cache (once). Returns the repo dir.
    Blobless clone keeps the checkout fast and only fetches blobs for the commit we check out."""
    os.makedirs(REPO_CACHE, exist_ok=True)
    dest = os.path.join(REPO_CACHE, repo.replace("/", "__"))
    if os.path.isdir(os.path.join(dest, ".git")):
        return dest
    url = f"https://github.com/{repo}.git"
    r = _run(["git", "clone", "--filter=blob:none", "--no-checkout", url, dest], timeout=1200)
    if not os.path.isdir(os.path.join(dest, ".git")):
        raise RuntimeError(f"clone failed for {repo}: {r.stderr[-300:]}")
    return dest


def checkout(repo_dir, commit):
    """Hard checkout of a commit (fetches its blobs on demand under a blobless clone)."""
    r = _run(["git", "-C", repo_dir, "checkout", "-f", commit], timeout=600)
    if r.returncode != 0:
        # commit may be unreachable in a shallow default fetch; fetch it explicitly then retry
        _run(["git", "-C", repo_dir, "fetch", "--filter=blob:none", "origin", commit], timeout=900)
        r = _run(["git", "-C", repo_dir, "checkout", "-f", commit], timeout=600)
        if r.returncode != 0:
            raise RuntimeError(f"checkout {commit[:10]} failed: {r.stderr[-300:]}")
    # clean untracked leftovers from a previous task on the same repo
    _run(["git", "-C", repo_dir, "clean", "-fdx"], timeout=300)


def apply_test_patch(repo_dir, test_patch):
    """Apply the task's test_patch (adds/updates the oracle test files). Returns (ok, msg)."""
    if not test_patch.strip():
        return True, "empty test_patch"
    pf = os.path.join(repo_dir, ".swe_test.patch")
    with open(pf, "w") as f:
        f.write(test_patch)
    for args in (["apply", "--3way"], ["apply"], ["apply", "--reject"]):
        r = _run(["git", "-C", repo_dir, *args, pf], timeout=120)
        if r.returncode == 0:
            os.remove(pf)
            return True, "applied " + " ".join(args)
    os.remove(pf)
    return False, r.stderr[-200:]


def patched_files(patch):
    """Repo-relative paths touched by a unified diff (b/ side)."""
    return sorted(set(re.findall(r"^\+\+\+ b/(.+)$", patch, flags=re.M)))


def added_lines_by_file(patch):
    """{repo-rel path: [added source lines]} for a unified diff (the '+' lines of the fix)."""
    out, cur = {}, None
    for ln in patch.splitlines():
        m = re.match(r"^\+\+\+ b/(.+)$", ln)
        if m:
            cur = m.group(1); out.setdefault(cur, [])
            continue
        if cur and ln.startswith("+") and not ln.startswith("+++"):
            out[cur].append(ln[1:])
    return out


def pytest_command(f2p, p2p, include_p2p=True):
    """Build the oracle pytest command over FAIL_TO_PASS (+ PASS_TO_PASS) node ids."""
    nodes = list(f2p) + (list(p2p) if include_p2p else [])
    quoted = " ".join('"' + n.replace('"', '\\"') + '"' for n in nodes)
    return f"python -m pytest -p no:cacheprovider -q {quoted}"


def repo_py_files(repo_dir, limit=4000):
    """Repo-relative .py files (bounded), skipping vendored/test dirs for symbol resolution."""
    skip = ("/.git/", "/build/", "/dist/", "/.tox/", "/node_modules/")
    files = []
    for dp, dns, fns in os.walk(repo_dir):
        dns[:] = [d for d in dns if d not in (".git", "build", "dist", ".tox", "node_modules")]
        for fn in fns:
            if fn.endswith(".py"):
                rel = os.path.relpath(os.path.join(dp, fn), repo_dir)
                if not any(s in "/" + rel + "/" for s in skip):
                    files.append(rel)
        if len(files) >= limit:
            break
    return files


if __name__ == "__main__":
    # smoke: clone+checkout one small-repo task, apply its test_patch, print the pytest command.
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None, help="only this repo (e.g. marshmallow-code/marshmallow)")
    ap.add_argument("--n", type=int, default=1)
    args = ap.parse_args()
    for t in load_tasks(n=args.n, repos={args.repo} if args.repo else None):
        print(f"[{t['instance_id']}] repo={t['repo']} base={t['base_commit'][:10]}")
        d = ensure_clone(t["repo"]); checkout(d, t["base_commit"])
        ok, msg = apply_test_patch(d, t["test_patch"])
        f2p = json.loads(t["FAIL_TO_PASS"]); p2p = json.loads(t["PASS_TO_PASS"])
        print(f"  clone={d}")
        print(f"  test_patch: {ok} ({msg}); F2P={len(f2p)} P2P={len(p2p)}")
        print(f"  gold edits: {patched_files(t['patch'])}")
        print(f"  cmd: {pytest_command(f2p, p2p)[:160]}")
