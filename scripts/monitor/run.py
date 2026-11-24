"""Run one known-source check and stage the result through Round 1.

Monitoring records a snapshot and, when the source supports a structured
change, a review candidate. It does not approve, unpublish, or edit the
approved revision.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone

from review.facts import material_fingerprint
from review.stage import stage_observation
from review.store import approved_facts, atomic_write_json, bump_lock, utcnow

from .normalize import as_bytes, reviewable_text, sha256_bytes, sha256_text
from .propose import (
    apply_material_changes,
    assess,
    build_next_offering,
    next_offering_id,
    stable_program,
    unstated_cycle_fields,
)
from .report import render, summarize
from .snapshots import EphemeralSnapshots, snapshot_id_for


def _stamp(now):
    if now is None:
        return utcnow()
    if isinstance(now, datetime):
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return str(now)


def _js_shell(body, reviewable):
    if reviewable.strip():
        return False
    raw = body.lower() if isinstance(body, (bytes, bytearray)) else str(body).lower().encode("utf-8")
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return b"<script" in raw


def _supersede(store, *, target_oid, source_oid, classification, fingerprint, now):
    superseded = []
    for cand in store.get("candidates", {}).values():
        if cand.get("status") not in ("pending", "held"):
            continue
        same_target = cand.get("offering_id") == target_oid
        same_next = (
            classification == "next_cycle"
            and cand.get("review_reason") == "next_cycle"
            and cand.get("source_offering_id") == source_oid
        )
        if not same_target and not same_next:
            continue
        if cand.get("material_facts_fingerprint") == fingerprint:
            continue
        cand["status"] = "superseded"
        cand["superseded_at"] = now
        notes = list(cand.get("monitor_notes") or [])
        notes.append(
            "Newer source observation recorded a different fact. "
            "This candidate's proposed facts were not changed."
        )
        cand["monitor_notes"] = notes
        superseded.append(cand["candidate_id"])
    return superseded


def _annotate_observation(store, observation_id, extra):
    for rec in reversed(store.get("observations") or []):
        if rec.get("observation_id") == observation_id:
            rec.update(extra)
            return rec
    return None


def _attach_evidence(store, candidate_id, evidence, now):
    cand = store.get("candidates", {}).get(candidate_id)
    if not cand:
        return
    if "monitor_evidence" not in cand:
        cand["monitor_evidence"] = evidence
    else:
        cand.setdefault("monitor_rechecks", []).append(now)


def _evidence(source, *, final_url, snapshot_id, now, classification, excerpts, changes, extracted, approved_offering, proposed_offering):
    fields = []
    if classification == "material_change":
        fields = [change.as_dict() for change in changes]
    elif classification == "next_cycle":
        fields.append({
            "field": "cycle_label",
            "prior_approved_value": (approved_offering or {}).get("cycle_label"),
            "proposed_value": extracted.cycle_label if extracted else None,
            "excerpt": extracted.cycle_excerpt if extracted else None,
        })
        if extracted and extracted.deadline:
            fields.append({
                "field": "app.deadlines",
                "prior_approved_value": None,
                "proposed_value": extracted.deadline,
                "excerpt": extracted.deadline_excerpt,
                "note": "stated on the new-cycle source; other cycle-dependent facts were not copied",
            })
        fields.extend(unstated_cycle_fields(approved_offering, proposed_offering or {}))
    elif classification == "first_party_cancellation":
        fields.append({
            "field": "reported_lifecycle",
            "prior_approved_value": (approved_offering or {}).get("reported_lifecycle"),
            "proposed_value": "cancelled",
            "excerpt": excerpts[0] if excerpts else None,
        })
    return {
        "source_id": source["source_id"],
        "official_url": final_url,
        "snapshot_id": snapshot_id,
        "supporting_excerpts": list(excerpts or []),
        "affected_fields": fields,
        "detected_at": now,
        "monitored_offering_id": source["offering_id"],
    }


def _persist_state(state_root, report):
    os.makedirs(state_root, exist_ok=True)
    checks_path = os.path.join(state_root, "checks.json")
    existing = []
    if os.path.exists(checks_path):
        with open(checks_path, encoding="utf-8") as fh:
            existing = json.load(fh)
    existing.extend(report.get("sources") or [])
    atomic_write_json(checks_path, existing)
    atomic_write_json(os.path.join(state_root, "last_report.json"), {
        "counts": report.get("counts"),
        "dry_run": report.get("dry_run"),
        "source_ids": [item.get("source_id") for item in report.get("sources") or []],
    })
    with open(os.path.join(state_root, "last_report.txt"), "w", encoding="utf-8") as fh:
        fh.write(report.get("text") or "")


def run_monitor(store, sources, fetcher, snapshots, *, now=None, dry_run=False, state_root=None):
    """Check each known source once. Mutates `store` unless dry_run is set."""
    if dry_run:
        store = deepcopy(store)
        snapshots = EphemeralSnapshots(snapshots)
        state_root = None
    stamp = _stamp(now)
    details = []
    for source in sources:
        details.append(_check_one(store, source, fetcher, snapshots, stamp))
    report = {
        "dry_run": bool(dry_run),
        "checked_at": stamp,
        "counts": summarize(details),
        "sources": details,
    }
    report["text"] = render(report)
    if state_root and not dry_run:
        _persist_state(state_root, report)
    return report


def _check_one(store, source, fetcher, snapshots, now):
    fetched = fetcher.fetch(source)
    body = as_bytes(fetched.get("body"))
    raw_sha = sha256_bytes(body)
    reviewable = ""
    if fetched.get("kind") == "ok" and body.lstrip().startswith(b"%PDF"):
        fetched = dict(fetched)
        fetched["kind"] = "fetch_failed"
        fetched["ok"] = False
        fetched["error"] = "unsupported_pdf"
        fetched["reason"] = "binary PDF was snapshotted without text extraction; not a cancellation or a fact change"
        body = as_bytes(fetched.get("body"))
    elif fetched.get("kind") == "ok":
        reviewable = reviewable_text(body)
        if _js_shell(body, reviewable) or not reviewable.strip():
            fetched = dict(fetched)
            fetched["kind"] = "fetch_failed"
            fetched["ok"] = False
            fetched["error"] = "javascript_only" if b"<script" in body.lower() else "empty_body"
            fetched["reason"] = "page had no reviewable text; treated as a fetch failure, not a disappearance"
            reviewable = ""

    norm_sha = sha256_text(reviewable)
    snap_id = snapshot_id_for(source["source_id"], fetched.get("kind") or "fetch_failed", fetched.get("status"), raw_sha)
    prior_obs = [item for item in store.get("observations") or [] if item.get("source_id") == source["source_id"]]
    seq = len(prior_obs) + 1
    observation_id = f"obs-{source['source_id']}-{seq}-{raw_sha[:8]}"
    detail = {
        "check_id": f"check-{source['source_id']}-{seq}",
        "source_id": source["source_id"],
        "program_id": source["program_id"],
        "offering_id": source["offering_id"],
        "requested_url": fetched.get("requested_url") or source.get("url"),
        "final_url": fetched.get("final_url") or "",
        "http_status": fetched.get("status"),
        "content_type": fetched.get("content_type") or "",
        "fetched_at": now,
        "etag": fetched.get("etag"),
        "last_modified": fetched.get("last_modified"),
        "raw_sha256": raw_sha,
        "normalized_sha256": norm_sha,
        "snapshot_id": snap_id,
        "user_agent": fetched.get("user_agent"),
        "redirect_chain": list(fetched.get("redirect_chain") or []),
        "url_change_flag": False,
        "unexpected_redirect": fetched.get("kind") == "unexpected_redirect",
        "fetch_kind": fetched.get("kind"),
        "candidate_id": None,
        "queued": False,
        "duplicate_suppressed": False,
        "superseded_candidate_ids": [],
        "note": fetched.get("reason") or "",
        "evidence": None,
    }

    approved_program, approved_offering = approved_facts(store, source["offering_id"])
    classification = None
    excerpts = []
    changes = []
    proposed_program = None
    proposed_offering = None
    proposed_oid = None
    extracted = None
    stage_outcome = None

    if fetched.get("kind") == "missing_page":
        classification = "missing_page"
        stage_outcome = "missing_page"
        detail["note"] = "HTTP missing page recorded; not treated as a cancellation or a removal"
    elif fetched.get("kind") == "unexpected_redirect":
        classification = "pending_update"
        stage_outcome = "pending_update"
        detail["note"] = fetched.get("reason") or "unexpected redirect"
    elif fetched.get("kind") != "ok":
        classification = "fetch_failed"
        stage_outcome = "fetch_failed"
        detail["note"] = fetched.get("reason") or "fetch failed"
    else:
        prior = snapshots.latest_ok(source["source_id"])
        raw_changed = bool(prior and prior.get("raw_sha256") != raw_sha)
        normalized_changed = bool(prior and prior.get("normalized_sha256") != norm_sha)
        first_run = prior is None
        from .extract import extract
        extracted = extract(reviewable)
        decision = assess(
            approved_offering, extracted,
            raw_changed=raw_changed, normalized_changed=normalized_changed, first_run=first_run,
        )
        classification = decision["classification"]
        excerpts = list(decision["excerpts"])
        changes = list(decision["changes"])
        detail["note"] = decision["note"]
        if fetched.get("final_url") and fetched.get("final_url") != source.get("url"):
            detail["url_change_flag"] = True
            detail["note"] = (detail["note"] + "; " if detail["note"] else "") + (
                "final URL differs from the recorded source URL; source identity was not changed"
            )
        authority = source.get("source_authority") or "unknown"
        if classification == "first_party_cancellation" and authority != "first_party":
            classification = "cancellation_report"
            stage_outcome = "cancellation_report"
            changes = []
            detail["note"] = "cancellation was not from a first-party source; observation only"
        elif classification in ("material_change", "next_cycle") and authority != "first_party":
            classification = "pending_update"
            stage_outcome = "pending_update"
            changes = []
            detail["note"] = "source is not first-party; change was not staged as a factual candidate"
        elif classification == "first_party_cancellation" and not (excerpts and fetched.get("final_url")):
            classification = "cancellation_report"
            stage_outcome = "cancellation_report"
            detail["note"] = "cancellation was missing an official link or excerpt"
        elif classification == "material_change":
            proposed_program, proposed_offering = apply_material_changes(
                approved_program, approved_offering, changes, extracted,
            )
        elif classification == "next_cycle":
            proposed_oid = next_offering_id(source["offering_id"], extracted.cycle_label)
            proposed_program = stable_program(approved_program or store.get("programs", {}).get(source["program_id"]) or {"pid": source["program_id"]})
            proposed_offering = build_next_offering(extracted, proposed_oid)
        elif classification in ("unchanged", "formatting_only"):
            stage_outcome = classification
            if approved_program is not None:
                proposed_program = deepcopy(approved_program)
                proposed_offering = deepcopy(approved_offering)
        else:
            stage_outcome = classification

    fingerprint = None
    target_oid = proposed_oid or source["offering_id"]
    if classification == "material_change" and proposed_program is not None:
        fingerprint = material_fingerprint(proposed_program, proposed_offering)
    elif classification == "next_cycle" and proposed_program is not None:
        fingerprint = material_fingerprint(proposed_program, proposed_offering)
        target_oid = proposed_oid
    elif classification == "first_party_cancellation" and approved_program is not None:
        preview = deepcopy(approved_offering)
        preview["reported_lifecycle"] = "cancelled"
        proposed_program = deepcopy(approved_program)
        proposed_offering = preview
        fingerprint = material_fingerprint(proposed_program, proposed_offering)
        target_oid = source["offering_id"]

    if fingerprint and classification in ("material_change", "next_cycle", "first_party_cancellation"):
        superseded = _supersede(
            store, target_oid=target_oid, source_oid=source["offering_id"],
            classification=classification, fingerprint=fingerprint, now=now,
        )
        detail["superseded_candidate_ids"] = superseded
        if superseded and classification != "next_cycle":
            bump_lock(store, target_oid, now)

    links = []
    if fetched.get("final_url") and not detail["unexpected_redirect"] and fetched.get("kind") == "ok":
        links = [fetched["final_url"]]
    observation = {
        "observation_id": observation_id,
        "program_id": source["program_id"],
        "offering_id": source["offering_id"],
        "source_id": source["source_id"],
        "observed_at": now,
        "extracted_text": reviewable if fetched.get("kind") == "ok" else "",
        "official_links": links,
        "excerpts": excerpts if classification in ("material_change", "next_cycle", "first_party_cancellation") else [],
        "source_authority": source.get("source_authority") or "unknown",
    }
    if stage_outcome:
        observation["outcome"] = stage_outcome
    if classification == "first_party_cancellation":
        observation["outcome"] = "first_party_cancellation"
    if proposed_oid:
        observation["proposed_offering_id"] = proposed_oid

    staged = stage_observation(store, observation, proposed_program, proposed_offering, now=now)
    classification = staged.get("outcome") or classification
    detail["classification"] = classification
    detail["candidate_id"] = staged.get("candidate_id")
    detail["queued"] = bool(staged.get("queued"))
    detail["reason"] = staged.get("reason")
    detail["duplicate_suppressed"] = bool(
        staged.get("candidate_id") and not staged.get("queued")
        and classification in ("material_change", "next_cycle", "first_party_cancellation")
    )
    if detail["duplicate_suppressed"]:
        detail["note"] = (detail["note"] + "; " if detail["note"] else "") + staged.get("reason", "")

    evidence = None
    if staged.get("candidate_id"):
        evidence = _evidence(
            source, final_url=links[0] if links else fetched.get("final_url") or source.get("url"),
            snapshot_id=snap_id, now=now, classification=classification, excerpts=observation["excerpts"],
            changes=changes, extracted=extracted, approved_offering=approved_offering,
            proposed_offering=proposed_offering,
        )
        _attach_evidence(store, staged["candidate_id"], evidence, now)
        detail["evidence"] = evidence

    _annotate_observation(store, observation_id, {
        "snapshot_id": snap_id,
        "requested_url": detail["requested_url"],
        "final_url": detail["final_url"],
        "http_status": detail["http_status"],
        "note": detail["note"],
        "monitor_classification": classification,
    })
    snapshots.save({
        "snapshot_id": snap_id,
        "source_id": source["source_id"],
        "kind": "ok" if fetched.get("kind") == "ok" else fetched.get("kind"),
        "retrieved_at": now,
        "requested_url": detail["requested_url"],
        "final_url": detail["final_url"],
        "http_status": detail["http_status"],
        "content_type": detail["content_type"],
        "raw_sha256": raw_sha,
        "normalized_sha256": norm_sha,
        "etag": detail["etag"],
        "last_modified": detail["last_modified"],
        "reviewable_text": reviewable if fetched.get("kind") == "ok" else "",
        "interpreted": fetched.get("kind") == "ok",
        "body": body if fetched.get("kind") != "unexpected_redirect" else b"",
    })
    return detail
