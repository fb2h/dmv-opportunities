"""Deterministic staging interface a later monitor can call.

A change creates a candidate. Unchanged / harmless formatting does not
requeue an approved revision. Failed fetch, pending update, and cancellation
reports are observations only — they must not unpublish.
"""
from __future__ import annotations

from copy import deepcopy

from .facts import (
    classify_observation,
    content_sha256,
    material_fingerprint,
    looks_like_next_cycle,
)
from .store import (
    add_revision,
    approved_facts,
    bump_lock,
    lock_seq,
    utcnow,
)


def _next_record_version(store, oid):
    versions = [0]
    for rev in store.get("revisions", []):
        if rev.get("entity_id") == oid:
            versions.append(int(rev.get("record_version") or 0))
    entry = store.get("approved", {}).get(oid)
    if entry:
        versions.append(int(entry.get("record_version") or 0))
    return max(versions) + 1


def _existing_open_candidate(store, oid, fingerprint):
    for cand in store["candidates"].values():
        if cand.get("offering_id") == oid and cand.get("status") in ("pending", "held"):
            if cand.get("material_facts_fingerprint") == fingerprint:
                return cand
    return None


def stage_observation(store, observation, proposed_program=None, proposed_offering=None, now=None):
    """Stage one observation. Returns a result dict. Does not write files.

    observation keys:
      observation_id, program_id, offering_id, source_id, observed_at,
      extracted_text, official_links, excerpts, outcome (optional override),
      proposed_offering_id (for next-cycle)
    """
    now = now or utcnow()
    oid = observation["offering_id"]
    pid = observation["program_id"]
    raw = observation.get("extracted_text") or ""
    raw_hash = content_sha256(raw)
    last = None
    for item in reversed(store.get("observations", [])):
        if item.get("offering_id") == oid and item.get("source_id") == observation.get("source_id"):
            last = item
            break
    raw_changed = bool(last and last.get("content_sha256") != raw_hash)

    approved_program, approved_offering = approved_facts(store, oid)
    outcome = observation.get("outcome")
    if outcome in ("fetch_failed", "cancellation_report", "pending_update"):
        rec = {
            "observation_id": observation["observation_id"],
            "program_id": pid,
            "offering_id": oid,
            "source_id": observation.get("source_id"),
            "observed_at": observation.get("observed_at") or now,
            "content_sha256": raw_hash,
            "outcome": outcome,
            "candidate_id": None,
            "note": "recorded only; approved membership unchanged",
        }
        store["observations"].append(rec)
        return {
            "ok": True,
            "outcome": outcome,
            "candidate_id": None,
            "queued": False,
            "unpublished": False,
            "reason": "observation recorded; approved version left intact",
        }

    if proposed_program is None:
        proposed_program = deepcopy(approved_program or store["programs"].get(pid) or {"pid": pid})
    if proposed_offering is None:
        proposed_offering = deepcopy(approved_offering or store["offerings"].get(oid) or {"oid": oid})

    if not outcome:
        outcome = classify_observation(
            approved_program, approved_offering, proposed_program, proposed_offering, raw_changed,
        )

    rec = {
        "observation_id": observation["observation_id"],
        "program_id": pid,
        "offering_id": oid,
        "source_id": observation.get("source_id"),
        "observed_at": observation.get("observed_at") or now,
        "content_sha256": raw_hash,
        "outcome": outcome,
        "candidate_id": None,
    }
    store["observations"].append(rec)

    if outcome in ("unchanged", "formatting_only"):
        return {
            "ok": True,
            "outcome": outcome,
            "candidate_id": None,
            "queued": False,
            "unpublished": False,
            "reason": "approved factual revision unchanged; no duplicate review",
        }

    target_oid = proposed_offering.get("oid") or oid
    if outcome == "next_cycle":
        target_oid = observation.get("proposed_offering_id") or proposed_offering.get("oid")
        if not target_oid or target_oid == oid:
            target_oid = f"{oid}-next"
        proposed_offering = deepcopy(proposed_offering)
        proposed_offering["oid"] = target_oid
        if not looks_like_next_cycle(approved_offering or {"oid": oid, "cycle_label": ""}, {**proposed_offering, "offering_id": target_oid}):
            # still treat as a new offering identity
            pass

    fingerprint = material_fingerprint(proposed_program, proposed_offering)
    existing = _existing_open_candidate(store, target_oid, fingerprint)
    if existing:
        rec["candidate_id"] = existing["candidate_id"]
        return {
            "ok": True,
            "outcome": outcome,
            "candidate_id": existing["candidate_id"],
            "queued": False,
            "unpublished": False,
            "reason": "equivalent candidate already outstanding",
        }

    baseline_fp = None
    baseline_ver = None
    if approved_program and approved_offering and outcome != "next_cycle":
        baseline_fp = material_fingerprint(approved_program, approved_offering)
        baseline_ver = (store["approved"].get(oid) or {}).get("record_version")

    proposed_version = 1 if outcome == "next_cycle" else _next_record_version(store, oid)
    candidate_id = f"cand-{target_oid}-v{proposed_version}-{fingerprint[:10]}"
    if candidate_id in store["candidates"]:
        candidate_id = f"{candidate_id}-{len(store['candidates']) + 1}"

    revision = add_revision(
        store,
        entity_id=target_oid,
        record_version=proposed_version,
        actor_kind="rule_engine",
        change_reason=outcome,
        program=proposed_program,
        offering=proposed_offering,
        role="proposed",
        when=now,
    )
    candidate = {
        "candidate_id": candidate_id,
        "program_id": pid,
        "offering_id": target_oid,
        "source_offering_id": oid,
        "proposed_record_version": proposed_version,
        "proposed_revision_id": revision["revision_id"],
        "material_facts_fingerprint": fingerprint,
        "approved_baseline_fingerprint": baseline_fp,
        "approved_baseline_record_version": baseline_ver,
        "review_reason": outcome,
        "official_links": list(observation.get("official_links") or []),
        "excerpts": list(observation.get("excerpts") or []),
        "created_at": now,
        "status": "pending",
        "store_seq_at_create": lock_seq(store, target_oid if target_oid in store["approved"] else oid),
    }
    store["candidates"][candidate_id] = candidate
    rec["candidate_id"] = candidate_id
    bump_lock(store, f"candidate:{candidate_id}", now)
    return {
        "ok": True,
        "outcome": outcome,
        "candidate_id": candidate_id,
        "queued": True,
        "unpublished": False,
        "reason": "candidate created; approved version left intact",
    }
