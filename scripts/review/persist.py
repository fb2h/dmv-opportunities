"""Git-backed persistence for the review store.

Stage and validate a coherent candidate/approval transaction before commit.
Detect concurrent same-record changes. Never force-push. Never commit
private reviewer notes. Writes are restricted to the workspace review tree.
"""
from __future__ import annotations

import os
import subprocess

from .store import (
    NOTES_FILENAME,
    STORE_FILENAME,
    load_store,
    save_store,
    store_dir,
    store_path,
    validate_store,
)

ALLOWED_RELATIVE_PREFIXES = (
    os.path.join("data", "review") + os.sep,
    os.path.join("catalogs") + os.sep,
)
FORBIDDEN_NAMES = {NOTES_FILENAME, ".review-notes.local.json"}


class PersistError(Exception):
    def __init__(self, message, *, concurrent=False):
        super().__init__(message)
        self.concurrent = concurrent


def run_git(workspace, *args, check=True):
    result = subprocess.run(
        ["git", "-C", workspace, *args],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise PersistError((result.stderr or result.stdout or "git failed").strip())
    return result


def head_sha(workspace):
    result = run_git(workspace, "rev-parse", "HEAD", check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def current_branch(workspace):
    result = run_git(workspace, "rev-parse", "--abbrev-ref", "HEAD")
    return result.stdout.strip()


def assert_not_main(workspace):
    branch = current_branch(workspace)
    if branch in ("main", "master"):
        raise PersistError(f"refusing to write review state on {branch}")
    return branch


def relative_to_workspace(workspace, path):
    workspace = os.path.abspath(workspace)
    path = os.path.abspath(path)
    if path == workspace or not path.startswith(workspace + os.sep):
        raise PersistError(f"path escapes workspace: {path}")
    return path[len(workspace) + 1:]


def assert_allowed_write(workspace, path):
    rel = relative_to_workspace(workspace, path)
    if os.path.basename(rel) in FORBIDDEN_NAMES:
        raise PersistError(f"refusing to commit private notes file {rel}")
    if not any(rel.startswith(prefix) or rel == prefix.rstrip(os.sep) for prefix in ALLOWED_RELATIVE_PREFIXES):
        raise PersistError(f"write path not in the allowed review tree: {rel}")
    return rel


def sync_from_authoritative(workspace):
    """Fast-forward from the configured remote. Honest failure if not possible."""
    assert_not_main(workspace)
    remotes = run_git(workspace, "remote", check=False)
    if remotes.returncode != 0 or not remotes.stdout.strip():
        return {"ok": True, "synced": False, "reason": "no remote configured; using local workspace"}
    fetch = run_git(workspace, "fetch", "--all", check=False)
    if fetch.returncode != 0:
        return {"ok": False, "synced": False, "reason": f"fetch failed: {(fetch.stderr or fetch.stdout).strip()}"}
    branch = current_branch(workspace)
    upstream = run_git(workspace, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
    if upstream.returncode != 0:
        return {"ok": True, "synced": False, "reason": "no upstream; local store is authoritative"}
    merge = run_git(workspace, "merge", "--ff-only", "@{u}", check=False)
    if merge.returncode != 0:
        return {
            "ok": False,
            "synced": False,
            "concurrent": True,
            "reason": "authoritative remote has diverged; refusing last-writer-wins merge: " + (merge.stderr or merge.stdout).strip(),
        }
    return {"ok": True, "synced": True, "reason": f"fast-forwarded {branch}", "head": head_sha(workspace)}


def commit_paths(workspace, paths, message, expected_head=None):
    assert_not_main(workspace)
    live = head_sha(workspace)
    if expected_head and live and expected_head != live:
        raise PersistError(
            f"concurrent repository change: expected {expected_head[:12]}, found {live[:12]}",
            concurrent=True,
        )
    rels = []
    for path in paths:
        rel = assert_allowed_write(workspace, path)
        if not os.path.exists(path):
            raise PersistError(f"missing path {rel}")
        rels.append(rel)
    if os.path.exists(os.path.join(store_dir(workspace), NOTES_FILENAME)):
        run_git(workspace, "rm", "-f", "--cached", f"data/review/{NOTES_FILENAME}", check=False)
    run_git(workspace, "add", "--", *rels)
    # Never add notes, even if a caller listed the review directory.
    run_git(workspace, "reset", "-q", "--", f"data/review/{NOTES_FILENAME}", check=False)
    staged = run_git(workspace, "diff", "--cached", "--name-only")
    names = [n for n in staged.stdout.splitlines() if n]
    if any(os.path.basename(n) in FORBIDDEN_NAMES for n in names):
        raise PersistError("private reviewer notes were staged; aborting commit")
    if not names:
        return {"ok": True, "committed": False, "reason": "nothing to commit", "head": live}
    run_git(workspace, "commit", "-m", message)
    return {"ok": True, "committed": True, "reason": "committed", "head": head_sha(workspace), "files": names}


def push_ff_only(workspace, remote="origin", branch=None):
    branch = branch or current_branch(workspace)
    if branch in ("main", "master"):
        raise PersistError("refusing to push review state to main")
    result = run_git(workspace, "push", "-u", remote, branch, check=False)
    if result.returncode != 0:
        raise PersistError("push failed (no force-push): " + (result.stderr or result.stdout).strip())
    return {"ok": True, "remote": remote, "branch": branch, "head": head_sha(workspace)}


def save_store_transaction(workspace, store, message, expected_head=None):
    errors = validate_store(store)
    if errors:
        raise PersistError("refusing to commit invalid store: " + "; ".join(errors))
    save_store(workspace, store)
    return commit_paths(workspace, [store_path(workspace)], message, expected_head=expected_head)


def ensure_gitignore(workspace):
    path = os.path.join(workspace, ".gitignore")
    needed = f"data/review/{NOTES_FILENAME}\n"
    existing = ""
    if os.path.exists(path):
        existing = open(path, encoding="utf-8").read()
    if NOTES_FILENAME not in existing:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(needed)
    return path
