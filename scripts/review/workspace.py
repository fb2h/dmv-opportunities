"""Create an isolated git workspace for Round 1. Never uses main."""
from __future__ import annotations

import os
import subprocess

from .persist import ensure_gitignore
from .store import save_notes, save_store, store_dir


def _git(cwd, *args):
    result = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def init_isolated_workspace(workspace, store, branch="review-r1", remote_path=None):
    os.makedirs(workspace, exist_ok=True)
    if not os.path.isdir(os.path.join(workspace, ".git")):
        subprocess.run(["git", "init", "-b", branch, workspace], check=True, capture_output=True, text=True)
    _git(workspace, "config", "user.email", "round1-reviewer@localhost")
    _git(workspace, "config", "user.name", "Round1 Reviewer")
    ensure_gitignore(workspace)
    os.makedirs(store_dir(workspace), exist_ok=True)
    os.makedirs(os.path.join(workspace, "catalogs"), exist_ok=True)
    save_store(workspace, store)
    save_notes(workspace, {"by_candidate_id": {}})
    readme = os.path.join(workspace, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as fh:
            fh.write("# Isolated Round 1 review workspace\n\nNot the production catalog.\n")
    _git(workspace, "add", "README.md", ".gitignore", "data/review/store.json")
    _git(workspace, "reset", "-q", "--", "data/review/.review-notes.local.json")
    status = _git(workspace, "status", "--porcelain")
    if status:
        _git(workspace, "commit", "-m", "review: seed isolated store (decision-saved baseline)")
    if remote_path:
        os.makedirs(remote_path, exist_ok=True)
        if not os.path.isdir(os.path.join(remote_path, "objects")):
            subprocess.run(["git", "init", "--bare", remote_path], check=True, capture_output=True, text=True)
        remotes = _git(workspace, "remote")
        if "origin" not in remotes.split():
            _git(workspace, "remote", "add", "origin", remote_path)
        else:
            _git(workspace, "remote", "set-url", "origin", remote_path)
        _git(workspace, "push", "-u", "origin", branch)
        subprocess.run(["git", "--git-dir", remote_path, "symbolic-ref", "HEAD", f"refs/heads/{branch}"], check=True, capture_output=True, text=True)
    return {"workspace": workspace, "branch": branch, "remote": remote_path}
