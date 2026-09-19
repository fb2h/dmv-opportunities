"""Authoritative review store: observations, candidates, approved revisions, membership.

Existing contract fields reused: record_version, review_status,
reviewed_record_version, reviewed_at, reviewer_kind, RecordRevision.
Additive 2.4.0 fields: DirectoryMembership, ExplicitRemoval,
FactualRevisionCandidate, material_facts_fingerprint.
"""
from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone

from . import DIRECTORY_SCHOOL_YEAR, REVIEW_STORE_SCHEMA, CONTRACT_VERSION
from .facts import material_fingerprint

NOTES_FILENAME = ".review-notes.local.json"
STORE_FILENAME = "store.json"


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def empty_store():
    return {
        "schema_version": REVIEW_STORE_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "directory_school_year": DIRECTORY_SCHOOL_YEAR,
        "programs": {},
        "offerings": {},
        "revisions": [],
        "approved": {},
        "memberships": {},
        "removals": {},
        "candidates": {},
        "observations": [],
        "locks": {},
        "publication": {
            "last_decision_commit": None,
            "last_published_release_id": None,
            "last_published_at": None,
            "last_catalog_sha256": None,
            "decision_saved_at": None,
        },
    }


def store_dir(workspace):
    return os.path.join(workspace, "data", "review")


def store_path(workspace):
    return os.path.join(store_dir(workspace), STORE_FILENAME)


def notes_path(workspace):
    return os.path.join(store_dir(workspace), NOTES_FILENAME)


def load_store(workspace):
    path = store_path(workspace)
    if not os.path.exists(path):
        return empty_store()
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_notes(workspace):
    path = notes_path(workspace)
    if not os.path.exists(path):
        return {"by_candidate_id": {}}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def atomic_write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_store(workspace, store):
    atomic_write_json(store_path(workspace), store)


def save_notes(workspace, notes):
    atomic_write_json(notes_path(workspace), notes)


def program_of(store, pid):
    return store["programs"].get(pid)


def offering_of(store, oid):
    return store["offerings"].get(oid)


def approved_entry(store, oid):
    return store["approved"].get(oid)


def approved_revision(store, oid):
    entry = approved_entry(store, oid)
    if not entry:
        return None
    for rev in store["revisions"]:
        if rev.get("revision_id") == entry.get("revision_id"):
            return rev
    return None


def approved_facts(store, oid):
    """Exact approved factual revision. Never the newest unapproved candidate."""
    rev = approved_revision(store, oid)
    if not rev:
        return None, None
    record = rev["record"]
    return record.get("program"), record.get("offering")


def bump_lock(store, key, when=None):
    lock = store["locks"].setdefault(key, {"store_seq": 0, "updated_at": None})
    lock["store_seq"] = int(lock.get("store_seq") or 0) + 1
    lock["updated_at"] = when or utcnow()
    return lock["store_seq"]


def lock_seq(store, key):
    return int((store["locks"].get(key) or {}).get("store_seq") or 0)


def put_program_offering(store, program, offering):
    store["programs"][program["pid"]] = deepcopy(program)
    rec = deepcopy(offering)
    rec["program_id"] = program["pid"]
    store["offerings"][offering["oid"]] = rec


def add_revision(store, *, entity_id, record_version, actor_kind, change_reason, program, offering, role, when=None):
    when = when or utcnow()
    revision_id = f"rev-{entity_id}-v{record_version}-{role}"
    # Keep one immutable row per revision_id; recreate with a unique suffix on collision.
    existing = {r["revision_id"] for r in store["revisions"]}
    if revision_id in existing:
        revision_id = f"{revision_id}-{len(store['revisions']) + 1}"
    rev = {
        "revision_id": revision_id,
        "entity_kind": "offering",
        "entity_id": entity_id,
        "record_version": record_version,
        "saved_at": when,
        "actor_kind": actor_kind,
        "change_reason": change_reason,
        "role": role,
        "record": {"program": deepcopy(program), "offering": deepcopy(offering)},
        "evidence_ids": list(offering.get("evidence_ids") or []),
    }
    store["revisions"].append(rev)
    return rev


def set_approved(store, oid, revision, when=None):
    when = when or utcnow()
    program = revision["record"]["program"]
    offering = revision["record"]["offering"]
    store["approved"][oid] = {
        "revision_id": revision["revision_id"],
        "record_version": revision["record_version"],
        "facts_fingerprint": material_fingerprint(program, offering),
        "review_status": "passed",
        "reviewed_record_version": revision["record_version"],
        "reviewed_at": when,
        "reviewer_kind": "human",
        "approved_at": when,
    }
    put_program_offering(store, program, offering)
    bump_lock(store, oid, when)


def assign_membership(store, oid, school_year, when=None, candidate_id=None):
    when = when or utcnow()
    store["memberships"][oid] = {
        "offering_id": oid,
        "school_year": school_year,
        "assigned_at": when,
        "assigned_by": "human",
        "assignment_revision_id": (store["approved"].get(oid) or {}).get("revision_id"),
        "assignment_candidate_id": candidate_id,
    }


def explicit_remove(store, oid, school_year, reason, audit_id, when=None):
    when = when or utcnow()
    store["removals"][f"{oid}:{school_year}"] = {
        "offering_id": oid,
        "school_year": school_year,
        "removed_at": when,
        "removed_by": "human",
        "reason": reason,
        "audit_id": audit_id,
    }
    bump_lock(store, oid, when)


def is_removed(store, oid, school_year):
    return f"{oid}:{school_year}" in store["removals"]


def outstanding_candidates(store):
    return [
        c for c in store["candidates"].values()
        if c.get("status") in ("pending", "held")
    ]


def validate_store(store):
    errors = []
    if store.get("schema_version") != REVIEW_STORE_SCHEMA:
        errors.append(f"unexpected store schema {store.get('schema_version')}")
    for oid, entry in store.get("approved", {}).items():
        if not any(r.get("revision_id") == entry.get("revision_id") for r in store.get("revisions", [])):
            errors.append(f"approved {oid} points at missing revision {entry.get('revision_id')}")
        if entry.get("review_status") != "passed":
            errors.append(f"approved {oid} review_status is not passed")
        if entry.get("reviewed_record_version") != entry.get("record_version"):
            errors.append(f"approved {oid} reviewed_record_version mismatch")
    for oid, mem in store.get("memberships", {}).items():
        if mem.get("school_year") and oid not in store.get("approved", {}) and not is_removed(store, oid, mem["school_year"]):
            # Membership without approval is invalid for a public rebuild.
            errors.append(f"membership {oid} has no approved revision")
    for cid, cand in store.get("candidates", {}).items():
        if cand.get("candidate_id") != cid:
            errors.append(f"candidate key {cid} != candidate_id")
    return errors
