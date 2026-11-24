"""Operator CLI for known-source checks. Fixture mode is the default path."""
from __future__ import annotations

import argparse
import json
import os
import sys

from review.fixtures import seed_store
from review.store import load_store, save_store, store_path

from .fetch import FixtureFetcher, LiveFetcher, load_fixture_manifest
from .inventory import load_inventory, select_sources
from .run import run_monitor
from .safety import SafetyError, assert_isolated_workspace, assert_output_outside_repo
from .snapshots import SnapshotStore


def _repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _print(payload):
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def build_parser():
    parser = argparse.ArgumentParser(description="Known-source monitor (Round 2). Does not publish.")
    parser.add_argument("--workspace", required=True, help="Isolated Round 1 review workspace. Never the production checkout.")
    parser.add_argument("--state-root", required=True, help="Directory for check history. Not inside the repository.")
    parser.add_argument("--snapshot-root", help="Directory for snapshots. Defaults to STATE_ROOT/snapshots.")
    parser.add_argument("--inventory", required=True, help="JSON list of known sources. This is not a discovery seed.")
    parser.add_argument("--fixtures", help="Fixture manifest. Required unless --live is set.")
    parser.add_argument("--source", action="append", default=[], help="Source id to check. Repeat for a small allowlist.")
    parser.add_argument("--all-listed", action="store_true", help="Check every source in the inventory file and nothing else.")
    parser.add_argument("--dry-run", action="store_true", help="Classify and print a report without writing snapshots, checks, or the review store.")
    parser.add_argument("--seed-fixtures", action="store_true", help="If the workspace has no review store, seed the isolated Round 1 fixtures.")
    parser.add_argument("--now", help="ISO timestamp for a deterministic run.")
    parser.add_argument("--live", action="store_true", help="Manual live fetch. Requires --allow-url. Not used by tests or schedules.")
    parser.add_argument("--allow-url", action="append", default=[], help="Exact URL permitted for --live. Repeat to match each selected source.")
    parser.add_argument("--repo-root", help=argparse.SUPPRESS)
    return parser


def _seed_if_requested(workspace, enabled):
    path = store_path(workspace)
    if not enabled:
        return
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    save_store(workspace, seed_store())


def main(argv=None):
    args = build_parser().parse_args(argv)
    repo_root = os.path.abspath(args.repo_root or _repo_root())
    try:
        assert_isolated_workspace(args.workspace, repo_root)
        assert_output_outside_repo(args.state_root, repo_root, label="monitor state")
        snapshot_root = args.snapshot_root or os.path.join(args.state_root, "snapshots")
        assert_output_outside_repo(snapshot_root, repo_root, label="snapshots")
        if args.live and args.fixtures:
            raise SafetyError("pass either --fixtures or --live, not both")
        if not args.live and not args.fixtures:
            raise SafetyError("refusing to fetch: pass --fixtures, or pass --live with --allow-url")
        sources = select_sources(load_inventory(args.inventory), args.source, args.all_listed)
        if args.live:
            allowed = set(args.allow_url or [])
            missing = [item["url"] for item in sources if item["url"] not in allowed]
            if missing:
                raise SafetyError("live fetch refused; every source URL must be passed with --allow-url: " + ", ".join(missing))
            fetcher = LiveFetcher()
        else:
            fetcher = FixtureFetcher(load_fixture_manifest(args.fixtures))
        _seed_if_requested(args.workspace, args.seed_fixtures and not args.dry_run)
        if args.seed_fixtures and args.dry_run and not os.path.exists(store_path(args.workspace)):
            os.makedirs(os.path.dirname(store_path(args.workspace)), exist_ok=True)
            save_store(args.workspace, seed_store())
        store = load_store(args.workspace)
        snapshots = SnapshotStore(snapshot_root)
        report = run_monitor(
            store, sources, fetcher, snapshots,
            now=args.now, dry_run=args.dry_run,
            state_root=args.state_root,
        )
        if not args.dry_run:
            save_store(args.workspace, store)
        sys.stdout.write(report["text"])
        return 0
    except (SafetyError, ValueError) as exc:
        _print({"ok": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
