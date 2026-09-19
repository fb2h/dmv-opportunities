"""Round 1 review CLI. Isolated fixtures only."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .fixtures import (
    PARK_OID,
    RIVER_OID,
    RIVER_PID,
    HARBOR_OID_2526,
    HARBOR_OID_2627,
    HARBOR_PID,
    proposed_harbor_next,
    proposed_river,
    river_source_text,
    seed_store,
)
from .persist import PersistError, head_sha, save_store_transaction, sync_from_authoritative
from .publish import publish_test_catalog
from .stage import stage_observation
from .store import load_notes, load_store, save_notes
from .workbook import export_workbook, import_workbook, summarize_results
from .workspace import init_isolated_workspace


def _print(payload):
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def cmd_init(args):
    rec = init_isolated_workspace(args.workspace, seed_store(), branch=args.branch, remote_path=args.remote)
    _print({"ok": True, **rec})


def cmd_stage(args):
    store = load_store(args.workspace)
    if args.scenario == "unchanged":
        program, offering = proposed_river("unchanged")
        obs = {"observation_id": "obs-unchanged", "program_id": RIVER_PID, "offering_id": RIVER_OID, "source_id": "river-s1",
               "extracted_text": river_source_text("unchanged"), "official_links": [program["program_url"]],
               "excerpts": [river_source_text("unchanged")]}
        result = stage_observation(store, obs, program, offering)
    elif args.scenario == "formatting":
        program, offering = proposed_river("formatting")
        obs = {"observation_id": "obs-formatting", "program_id": RIVER_PID, "offering_id": RIVER_OID, "source_id": "river-s1",
               "extracted_text": river_source_text("formatting"), "official_links": [program["program_url"]],
               "excerpts": [river_source_text("formatting")]}
        result = stage_observation(store, obs, program, offering)
    elif args.scenario == "material":
        program, offering = proposed_river("material")
        obs = {"observation_id": "obs-material", "program_id": RIVER_PID, "offering_id": RIVER_OID, "source_id": "river-s1",
               "extracted_text": river_source_text("material"), "official_links": [program["program_url"]],
               "excerpts": ["$18/hour"]}
        result = stage_observation(store, obs, program, offering)
    elif args.scenario == "next_cycle":
        program, offering = proposed_harbor_next()
        obs = {"observation_id": "obs-next", "program_id": HARBOR_PID, "offering_id": HARBOR_OID_2526,
               "proposed_offering_id": HARBOR_OID_2627, "source_id": "harbor-s1",
               "extracted_text": "Announcing 2026-2027 school year teen docents. Apply by August 1, 2026.",
               "official_links": [program["program_url"]], "excerpts": ["2026-2027 school year"]}
        result = stage_observation(store, obs, program, offering)
    elif args.scenario == "fetch_failed":
        obs = {"observation_id": "obs-fetch", "program_id": RIVER_PID, "offering_id": RIVER_OID, "source_id": "river-s1",
               "outcome": "fetch_failed", "extracted_text": ""}
        result = stage_observation(store, obs)
    elif args.scenario == "cancellation":
        obs = {"observation_id": "obs-cancel", "program_id": RIVER_PID, "offering_id": RIVER_OID, "source_id": "river-s1",
               "outcome": "cancellation_report", "extracted_text": "A parent reported the session was cancelled."}
        result = stage_observation(store, obs)
    else:
        raise SystemExit(f"unknown scenario {args.scenario}")
    save_store_transaction(args.workspace, store, f"review: stage {args.scenario} observation")
    _print(result)


def cmd_export(args):
    store = load_store(args.workspace)
    _, n = export_workbook(store, path=args.out)
    _print({"ok": True, "path": args.out, "outstanding_rows": n})


def cmd_import(args):
    sync = sync_from_authoritative(args.workspace)
    if not sync.get("ok"):
        _print({"ok": False, "step": "sync", **sync})
        return 2
    store = load_store(args.workspace)
    notes = load_notes(args.workspace)
    expected = head_sha(args.workspace)
    with open(args.infile, "rb") as fh:
        data = fh.read()
    store, notes, results = import_workbook(store, data, notes=notes)
    save_notes(args.workspace, notes)
    commit = save_store_transaction(
        args.workspace, store,
        "review: apply workbook decisions (decision-saved, not site-published)",
        expected_head=expected,
    )
    _print({"ok": True, "sync": sync, "commit": commit, "counts": summarize_results(results), "results": results})
    return 0


def cmd_publish(args):
    result = publish_test_catalog(args.workspace, today=args.today, output=args.out, repo_root=args.repo_root)
    _print(result)
    return 0 if result.get("ok") else 2


def cmd_status(args):
    store = load_store(args.workspace)
    _print({
        "head": head_sha(args.workspace),
        "approved": list(store.get("approved", {})),
        "memberships": store.get("memberships", {}),
        "candidates": {k: {"status": v.get("status"), "reason": v.get("review_reason")} for k, v in store.get("candidates", {}).items()},
        "publication": store.get("publication"),
        "park_membership": PARK_OID in store.get("memberships", {}),
    })


def cmd_serve(args):
    from .server import serve
    serve(args.workspace, host=args.host, port=args.port, repo_root=args.repo_root)


def build_parser():
    p = argparse.ArgumentParser(description="Round 1 isolated review tool")
    p.add_argument("--workspace", required=True, help="Isolated git workspace (never main / never production catalog)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init")
    s.add_argument("--branch", default="review-r1")
    s.add_argument("--remote")
    s.set_defaults(func=cmd_init)
    s = sub.add_parser("stage")
    s.add_argument("scenario", choices=["unchanged", "formatting", "material", "next_cycle", "fetch_failed", "cancellation"])
    s.set_defaults(func=cmd_stage)
    s = sub.add_parser("export")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_export)
    s = sub.add_parser("import")
    s.add_argument("--in", dest="infile", required=True)
    s.set_defaults(func=cmd_import)
    s = sub.add_parser("publish")
    s.add_argument("--today")
    s.add_argument("--out")
    s.add_argument("--repo-root")
    s.set_defaults(func=cmd_publish)
    s = sub.add_parser("status")
    s.set_defaults(func=cmd_status)
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--repo-root")
    s.set_defaults(func=cmd_serve)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        code = args.func(args)
        return 0 if code is None else code
    except PersistError as exc:
        _print({"ok": False, "error": str(exc), "concurrent": getattr(exc, "concurrent", False)})
        return 3


if __name__ == "__main__":
    sys.exit(main())
