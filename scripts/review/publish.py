"""Explicit publication entry point.

Decision-saved is not site-published. This command builds the test catalog
from the approved revision + membership and records a publication event.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

from .catalog import build_catalog_document, write_catalog_atomic, catalog_sha256
from .persist import PersistError, assert_not_main, commit_paths, head_sha
from .store import load_store, save_store, utcnow


def publish_test_catalog(workspace, today=None, output=None, repo_root=None, expected_head=None):
    assert_not_main(workspace)
    store = load_store(workspace)
    today = today or date.today()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    release_id = f"test-release-{today.isoformat()}-{generated_at.replace(':', '').replace('-', '')[:15]}"
    catalog, skipped = build_catalog_document(store, today, generated_at, release_id=release_id)
    output = output or os.path.join(workspace, "catalogs", "catalog.json")
    previous = output if os.path.exists(output) else None
    write = write_catalog_atomic(output, catalog, previous_path=previous, repo_root=repo_root, allow_production=False)
    if not write.get("ok"):
        return {
            "ok": False,
            "published": False,
            "decision_saved": bool(store.get("publication", {}).get("decision_saved_at")),
            "reason": write.get("reason"),
            "skipped": skipped,
        }
    store.setdefault("publication", {})
    store["publication"]["last_published_release_id"] = release_id
    store["publication"]["last_published_at"] = utcnow()
    store["publication"]["last_catalog_sha256"] = catalog_sha256(catalog)
    store["publication"]["last_decision_commit"] = head_sha(workspace)
    save_store(workspace, store)
    try:
        commit = commit_paths(
            workspace,
            [output, os.path.join(workspace, "data", "review", "store.json")],
            f"review: publish test catalog {release_id} (site-published; distinct from decision-saved)",
            expected_head=expected_head,
        )
    except PersistError as exc:
        return {
            "ok": False,
            "published": False,
            "decision_saved": True,
            "reason": f"catalog file written but publication commit failed: {exc}",
            "retryable": True,
            "release_id": release_id,
            "output": output,
            "skipped": skipped,
        }
    return {
        "ok": True,
        "published": True,
        "decision_saved": True,
        "release_id": release_id,
        "output": output,
        "sha256": write.get("sha256"),
        "skipped": skipped,
        "commit": commit,
        "program_count": catalog["program_count"],
        "offering_count": catalog["offering_count"],
    }
