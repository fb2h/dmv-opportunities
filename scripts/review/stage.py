"""Deterministic staging interface a later monitor can call.

A change creates a candidate. Unchanged / harmless formatting does not
requeue an approved revision.

Fetch failure, a missing page, a pending update, and an unverified or
third-party cancellation report are observations only — they must not
unpublish and must not write an unsupported cancelled fact.

A first-party official confirmation that an approved offering was
cancelled is a material factual change: it creates a review candidate
and leaves the approved revision intact until human review.
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

UNVERIFIED_OBSERVATIONS = frozenset({
    "fetch_failed",
    "missing_page",
    "pending_update",
    "cancellation_report",
})


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


def _record_observation(store, observation, outcome, now, candidate_id=None, note=None):
    rec = {
        "observation_id": observation["observation_id"],
        "program_id": observation["program_id"],
        "offering_id": observation["offering_id"],
        "source_id": observation.get("source_id"),
        "observed_at": observation.get("observed_at") or now,
        "content_sha256": content_sha256(observation.get("extracted_text") or ""),
        "outcome": outcome,
        "candidate_id": candidate_id,
        "source_authority": observation.get("source_authority") or "unknown",
        "note": note,
    }
    store["observations"].append(rec)
    return rec


def _observation_only(store, observation, outcome, now, reason):
    _record_observation(store, observation, outcome, now, note=reason)
    return {
        "ok": True,
        "outcome": outcome,
        "candidate_id": None,
        "queued": False,
        "unpublished": False,
        "reason": reason,
    }


def first_party_cancellation_confirmed(observation):
    """True only for an explicit first-party official cancellation.

    Not inferred from fetch failure, a missing page, a deadline, an end
    date, or a third-party / unsupported statement.
    """
    return (
        observation.get("outcome") == "first_party_cancellation"
        and observation.get("source_authority") == "first_party"
    )


def _without_unconfirmed_cancellation(approved_offering, proposed_offering):
    proposed = deepcopy(proposed_offering)
    if proposed.get("reported_lifecycle") != "cancelled":
        return proposed
    prior = (approved_offering or {}).get("reported_lifecycle")
    if prior == "cancelled":
        return proposed
    if prior:
        proposed["reported_lifecycle"] = prior
    else:
        proposed.pop("reported_lifecycle", None)
    return proposed


def stage_observation(store, observation, proposed_program=None, proposed_offering=None, now=None):
    """Stage one observation. Returns a result dict. Does not write files.

    observation keys:
      observation_id, program_id, offering_id, source_id, observed_at,
      extracted_text, official_links, excerpts, outcome (optional override),
      source_authority, proposed_offering_id (for next-cycle)
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
    authority = observation.get("source_authority") or "unknown"

    if outcome in UNVERIFIED_OBSERVATIONS:
        return _observation_only(
            store, observation, outcome, now,
            "observation recorded; approved version left intact",
        )

    if outcome == "first_party_cancellation" and authority != "first_party":
        return _observation_only(
            store, observation, "cancellation_report", now,
            "cancellation not first-party; recorded as unverified; approved version left intact",
        )

    if proposed_program is None:
        proposed_program = deepcopy(approved_program or store["programs"].get(pid) or {"pid": pid})
    if proposed_offering is None:
        proposed_offering = deepcopy(approved_offering or store["offerings"].get(oid) or {"oid": oid})

    if first_party_cancellation_confirmed(observation):
        proposed_program = deepcopy(proposed_program)
        proposed_offering = deepcopy(proposed_offering)
        proposed_offering["reported_lifecycle"] = "cancelled"
        outcome = "first_party_cancellation"
    else:
        proposed_offering = _without_unconfirmed_cancellation(approved_offering, proposed_offering)
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
        "source_authority": authority,
    }
    store["observations"].append(rec)

    if outcome in ("unchanged", "formatting_only"):
        rec["note"] = "approved factual revision unchanged; no duplicate review"
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
