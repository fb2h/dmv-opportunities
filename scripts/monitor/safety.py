"""Guards so the monitor cannot write the production checkout."""
from __future__ import annotations

import os


class SafetyError(Exception):
    pass


def _real(path):
    return os.path.realpath(os.path.abspath(path))


def assert_isolated_workspace(workspace, repo_root):
    """Refuse the production checkout and any tree that still holds the live catalog."""
    ws = _real(workspace)
    root = _real(repo_root)
    if ws == root or ws.startswith(root + os.sep):
        raise SafetyError(f"refusing to use a path inside the repository as the monitor workspace: {ws}")
    catalog = os.path.join(ws, "site", "data", "catalog.json")
    programs = os.path.join(ws, "data", "programs")
    if os.path.exists(catalog) and os.path.isdir(programs):
        raise SafetyError("refusing to write monitor results into a production-shaped tree")
    return ws


def assert_output_outside_repo(path, repo_root, *, label):
    dest = _real(path)
    root = _real(repo_root)
    if dest == root or dest.startswith(root + os.sep):
        raise SafetyError(f"refusing to write {label} inside the repository: {dest}")
    return dest
