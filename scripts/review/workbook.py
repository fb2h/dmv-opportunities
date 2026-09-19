"""Review workbook export/import.

Each row is one candidate offering revision. Ryan may edit Decision and
Review notes only. Empty decision is not approval. Edited fact cells are
ignored. The importer never replaces the master with the workbook.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from . import DIRECTORY_SCHOOL_YEAR
from .facts import format_material_facts, material_fingerprint
from .store import (
    add_revision,
    approved_facts,
    assign_membership,
    load_notes,
    save_notes,
    set_approved,
    utcnow,
    validate_store,
)
from .xlsxutil import read_xlsx, write_xlsx

HEADERS = [
    "candidate_id",
    "program_id",
    "offering_id",
    "program_name",
    "cycle_label",
    "why_review",
    "official_links",
    "excerpts",
    "old_material_facts",
    "proposed_material_facts",
    "proposed_record_version",
    "approved_baseline_record_version",
    "candidate_fingerprint",
    "approved_baseline_fingerprint",
    "store_seq",
    "export_row_sha256",
    "Decision",
    "Review notes",
]

EDITABLE = {"Decision", "Review notes"}
DECISIONS = {"approve", "reject", "hold"}


def _row_integrity(row):
    payload = {k: row.get(k, "") for k in HEADERS if k not in EDITABLE and k != "export_row_sha256"}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def export_workbook(store, path=None):
    outstanding = sorted(store["candidates"].values(), key=lambda c: c["candidate_id"])
    outstanding = [c for c in outstanding if c.get("status") in ("pending", "held")]
    rows = [HEADERS]
    for cand in outstanding:
        pid = cand["program_id"]
        oid = cand["offering_id"]
        proposed = None
        for rev in store["revisions"]:
            if rev.get("revision_id") == cand.get("proposed_revision_id"):
                proposed = rev
                break
        if not proposed:
            continue
        proposed_program = proposed["record"]["program"]
        proposed_offering = proposed["record"]["offering"]
        old_program, old_offering = approved_facts(store, cand.get("source_offering_id") or oid)
        if old_program is None:
            old_program, old_offering = approved_facts(store, oid)
        old_text = format_material_facts(old_program, old_offering) if old_program else "(no approved version)"
        why = {
            "material_change": "Material facts differ from the approved revision.",
            "next_cycle": "A new cycle was announced. The previous cycle must stay intact.",
            "new_assignment": "Proposed directory-year membership needs review.",
            "other": "Review required.",
        }.get(cand.get("review_reason"), cand.get("review_reason") or "Review required.")
        if cand.get("status") == "held":
            why = "Previously held. " + why
        rec = {
            "candidate_id": cand["candidate_id"],
            "program_id": pid,
            "offering_id": oid,
            "program_name": proposed_program.get("name") or "",
            "cycle_label": proposed_offering.get("cycle_label") or "",
            "why_review": why,
            "official_links": "\n".join(cand.get("official_links") or []),
            "excerpts": "\n".join(cand.get("excerpts") or []),
            "old_material_facts": old_text,
            "proposed_material_facts": format_material_facts(proposed_program, proposed_offering),
            "proposed_record_version": str(cand.get("proposed_record_version") or ""),
            "approved_baseline_record_version": "" if cand.get("approved_baseline_record_version") is None else str(cand["approved_baseline_record_version"]),
            "candidate_fingerprint": cand.get("material_facts_fingerprint") or "",
            "approved_baseline_fingerprint": cand.get("approved_baseline_fingerprint") or "",
            "store_seq": str(cand.get("store_seq_at_create") if cand.get("store_seq_at_create") is not None else 0),
            "Decision": "",
            "Review notes": "",
        }
        rec["export_row_sha256"] = _row_integrity(rec)
        rows.append([rec.get(h, "") for h in HEADERS])

    instructions = [
        ["Review instructions"],
        ["Edit only the Decision and Review notes columns."],
        ["Decision values: Approve, Reject, Hold. An empty Decision is not approval."],
        ["Do not edit facts, IDs, or fingerprints. Edited fact cells are ignored."],
        ["Each row is one candidate offering revision. The importer never replaces the master with this file."],
        ["Private review notes stay on this machine and are not written to git."],
    ]
    data = write_xlsx([("Review", rows), ("Instructions", instructions)], path=path)
    return data, len(rows) - 1


def _norm_decision(value):
    text = (value or "").strip().lower()
    if not text:
        return ""
    return text


def import_workbook(store, data, notes=None, now=None, assign_directory_year=True):
    """Apply decisions about known store versions. Returns (store, notes, results)."""
    now = now or utcnow()
    notes = notes or {"by_candidate_id": {}}
    sheets = read_xlsx(data)
    records = sheets.get("Review") or []
    results = []
    seen = {}
    working = store

    for idx, rec in enumerate(records, start=2):
        cid = (rec.get("candidate_id") or "").strip()
        if cid and cid in seen:
            results.append({
                "row": idx,
                "candidate_id": cid,
                "status": "error",
                "reason": "competing rows for the same candidate in one workbook",
            })
            continue
        if cid:
            seen[cid] = True
        result = _apply_row(working, rec, row_number=idx, now=now, assign_directory_year=assign_directory_year)
        if rec.get("Review notes") and cid and result["status"] in ("accepted", "held", "rejected", "already_applied", "no_decision"):
            notes.setdefault("by_candidate_id", {})[cid] = rec.get("Review notes")
        results.append(result)

    errors = validate_store(working)
    if errors:
        raise ValueError("store invalid after import: " + "; ".join(errors))
    working["publication"]["decision_saved_at"] = now
    return working, notes, results


def _apply_row(store, rec, row_number, now, assign_directory_year):
    cid = (rec.get("candidate_id") or "").strip()
    decision = _norm_decision(rec.get("Decision"))
    base = {"row": row_number, "candidate_id": cid, "decision": decision or None}

    if not cid:
        return {**base, "status": "error", "reason": "missing candidate_id"}
    cand = store["candidates"].get(cid)
    if not cand:
        return {**base, "status": "error", "reason": "unknown candidate_id; workbook cannot create master records"}

    fact_cells_edited = False
    expected_sha = (rec.get("export_row_sha256") or "").strip()
    if expected_sha and expected_sha != _row_integrity(rec):
        fact_cells_edited = True

    if not decision:
        return {**base, "status": "no_decision", "reason": "empty Decision is not approval", "fact_cells_edited_ignored": fact_cells_edited}

    if decision not in DECISIONS:
        return {**base, "status": "error", "reason": f"invalid Decision {rec.get('Decision')!r}"}

    if (rec.get("program_id") or "").strip() and rec.get("program_id").strip() != cand["program_id"]:
        return {**base, "status": "error", "reason": "program_id does not match the known candidate"}
    if (rec.get("offering_id") or "").strip() and rec.get("offering_id").strip() != cand["offering_id"]:
        return {**base, "status": "error", "reason": "offering_id does not match the known candidate"}

    if cand.get("status") == "approved" and cand.get("material_facts_fingerprint") == (rec.get("candidate_fingerprint") or cand.get("material_facts_fingerprint")):
        if decision == "approve":
            return {**base, "status": "already_applied", "reason": "candidate already approved; idempotent re-upload", "fact_cells_edited_ignored": fact_cells_edited}
    if cand.get("status") == "rejected" and decision == "reject":
        return {**base, "status": "already_applied", "reason": "candidate already rejected; idempotent re-upload", "fact_cells_edited_ignored": fact_cells_edited}
    if cand.get("status") == "held" and decision == "hold":
        return {**base, "status": "already_applied", "reason": "candidate already held; idempotent re-upload", "fact_cells_edited_ignored": fact_cells_edited}

    if cand.get("status") not in ("pending", "held"):
        return {**base, "status": "stale", "reason": f"candidate is {cand.get('status')}, not outstanding"}

    if rec.get("candidate_fingerprint") and rec.get("candidate_fingerprint") != cand.get("material_facts_fingerprint"):
        return {**base, "status": "stale", "reason": "candidate fingerprint does not match the current proposed revision"}
    if str(rec.get("proposed_record_version") or "") and str(rec.get("proposed_record_version")) != str(cand.get("proposed_record_version")):
        return {**base, "status": "stale", "reason": "proposed_record_version does not match the current candidate"}

    oid = cand["offering_id"]
    source_oid = cand.get("source_offering_id") or oid
    if cand.get("review_reason") != "next_cycle":
        current = store["approved"].get(source_oid)
        live_seq = int((store["locks"].get(source_oid) or {}).get("store_seq") or 0)
        created_seq = int(cand.get("store_seq_at_create") or 0)
        if current and cand.get("approved_baseline_fingerprint") and current.get("facts_fingerprint") != cand.get("approved_baseline_fingerprint"):
            return {**base, "status": "error", "reason": "competing baseline: approved facts changed since this candidate was created"}
        if rec.get("approved_baseline_fingerprint") and current and rec.get("approved_baseline_fingerprint") != current.get("facts_fingerprint"):
            return {**base, "status": "error", "reason": "competing baseline: workbook baseline does not match the live approved revision"}
        if current and created_seq != live_seq:
            return {**base, "status": "error", "reason": "concurrent same-record change detected (store_seq)"}

    proposed = None
    for rev in store["revisions"]:
        if rev.get("revision_id") == cand.get("proposed_revision_id"):
            proposed = rev
            break
    if not proposed:
        return {**base, "status": "error", "reason": "proposed revision missing from the store"}

    snapshot = deepcopy(store)
    try:
        if decision == "hold":
            cand["status"] = "held"
            cand["decided_at"] = now
            return {**base, "status": "held", "reason": "held; existing approved version intact", "fact_cells_edited_ignored": fact_cells_edited}
        if decision == "reject":
            cand["status"] = "rejected"
            cand["decided_at"] = now
            return {**base, "status": "rejected", "reason": "rejected; existing approved version intact", "fact_cells_edited_ignored": fact_cells_edited}

        # Approve the exact proposed revision already in the store — never workbook facts.
        program = proposed["record"]["program"]
        offering = proposed["record"]["offering"]
        live_fp = material_fingerprint(program, offering)
        if live_fp != cand.get("material_facts_fingerprint"):
            raise ValueError("store candidate fingerprint drifted from its proposed revision")
        approved_rev = add_revision(
            store,
            entity_id=oid,
            record_version=cand["proposed_record_version"],
            actor_kind="human",
            change_reason=f"approved {cid}",
            program=program,
            offering=offering,
            role="approved",
            when=now,
        )
        set_approved(store, oid, approved_rev, when=now)
        if oid in store.get("memberships", {}):
            assign_membership(store, oid, store["memberships"][oid]["school_year"], when=now, candidate_id=cid)
        elif assign_directory_year and cand.get("review_reason") in ("next_cycle", "new_assignment"):
            # Approving a reviewed next-cycle or explicit-assignment candidate is the membership decision.
            assign_membership(store, oid, DIRECTORY_SCHOOL_YEAR, when=now, candidate_id=cid)
        cand["status"] = "approved"
        cand["decided_at"] = now
        cand["approved_revision_id"] = approved_rev["revision_id"]
        return {
            **base,
            "status": "accepted",
            "reason": "approved exact stored revision",
            "approved_revision_id": approved_rev["revision_id"],
            "approved_fingerprint": live_fp,
            "fact_cells_edited_ignored": fact_cells_edited,
        }
    except Exception as exc:
        store.clear()
        store.update(snapshot)
        return {**base, "status": "error", "reason": f"row rolled back: {exc}"}


def rewrite_review_rows(records):
    rows = [HEADERS]
    for rec in records:
        rows.append([rec.get(h, "") for h in HEADERS])
    return write_xlsx([("Review", rows), ("Instructions", [["Review instructions"]])] )


def set_decisions(data, decisions):
    """Set Decision / Review notes by candidate_id. Used by tests and the demo."""
    sheets = read_xlsx(data)
    records = sheets.get("Review") or []
    for rec in records:
        cid = (rec.get("candidate_id") or "").strip()
        if cid in decisions:
            rec["Decision"] = decisions[cid].get("Decision", rec.get("Decision", ""))
            rec["Review notes"] = decisions[cid].get("Review notes", rec.get("Review notes", ""))
    return rewrite_review_rows(records)


def persist_notes_only(workspace, notes):
    save_notes(workspace, notes)


def summarize_results(results):
    counts = {}
    for item in results:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return counts
