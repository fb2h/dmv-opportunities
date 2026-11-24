"""Operator report for one monitor run. Not a public page."""
from __future__ import annotations

COUNT_KEYS = (
    "sources_attempted",
    "successful_fetches",
    "unchanged",
    "formatting_only",
    "material_change_candidates",
    "next_cycle_candidates",
    "pending_update",
    "first_party_cancellations",
    "fetch_failures",
    "missing_pages",
    "duplicate_suppressions",
    "unverified_cancellations",
    "unexpected_redirects",
)


def empty_counts():
    return {key: 0 for key in COUNT_KEYS}


def summarize(details):
    counts = empty_counts()
    counts["sources_attempted"] = len(details)
    for item in details:
        if item.get("fetch_kind") == "ok":
            counts["successful_fetches"] += 1
        classification = item.get("classification")
        if classification in counts and classification not in (
            "material_change_candidates", "next_cycle_candidates", "first_party_cancellations",
            "duplicate_suppressions", "sources_attempted", "successful_fetches",
        ):
            if classification in ("unchanged", "formatting_only", "pending_update"):
                counts[classification] += 1
        if classification == "fetch_failed":
            counts["fetch_failures"] += 1
        if classification == "missing_page":
            counts["missing_pages"] += 1
        if classification == "cancellation_report":
            counts["unverified_cancellations"] += 1
        if item.get("unexpected_redirect"):
            counts["unexpected_redirects"] += 1
        if item.get("queued") and classification == "material_change":
            counts["material_change_candidates"] += 1
        if item.get("queued") and classification == "next_cycle":
            counts["next_cycle_candidates"] += 1
        if item.get("queued") and classification == "first_party_cancellation":
            counts["first_party_cancellations"] += 1
        if item.get("duplicate_suppressed"):
            counts["duplicate_suppressions"] += 1
    return counts


def render(report):
    counts = report.get("counts") or {}
    lines = [
        "Known-source monitor",
        f"dry_run: {bool(report.get('dry_run'))}",
        f"sources attempted: {counts.get('sources_attempted', 0)}",
        f"successful fetches: {counts.get('successful_fetches', 0)}",
        f"unchanged: {counts.get('unchanged', 0)}",
        f"formatting / non-material: {counts.get('formatting_only', 0)}",
        f"material-change candidates: {counts.get('material_change_candidates', 0)}",
        f"next-cycle candidates: {counts.get('next_cycle_candidates', 0)}",
        f"pending / ambiguous: {counts.get('pending_update', 0)}",
        f"first-party cancellations: {counts.get('first_party_cancellations', 0)}",
        f"unverified cancellations: {counts.get('unverified_cancellations', 0)}",
        f"fetch failures: {counts.get('fetch_failures', 0)}",
        f"missing pages: {counts.get('missing_pages', 0)}",
        f"unexpected redirects: {counts.get('unexpected_redirects', 0)}",
        f"duplicate / open-candidate suppressions: {counts.get('duplicate_suppressions', 0)}",
        "",
    ]
    for item in report.get("sources") or []:
        lines.append(f"--- {item.get('source_id')}")
        lines.append(f"classification: {item.get('classification')}")
        lines.append(f"requested_url: {item.get('requested_url')}")
        lines.append(f"final_url: {item.get('final_url')}")
        lines.append(f"http_status: {item.get('http_status')}")
        lines.append(f"snapshot_id: {item.get('snapshot_id')}")
        lines.append(f"candidate_id: {item.get('candidate_id')}")
        lines.append(f"queued: {item.get('queued')}")
        lines.append(f"duplicate_suppressed: {item.get('duplicate_suppressed')}")
        if item.get("url_change_flag"):
            lines.append("url_change_flag: true (source identity unchanged)")
        if item.get("unexpected_redirect"):
            lines.append("unexpected_redirect: destination was not used as evidence")
        if item.get("note"):
            lines.append(f"note: {item.get('note')}")
        evidence = item.get("evidence")
        if evidence:
            lines.append(f"detected_at: {evidence.get('detected_at')}")
            for field in evidence.get("affected_fields") or []:
                lines.append(
                    f"field {field.get('field')}: {field.get('prior_approved_value')!r} -> {field.get('proposed_value')!r}"
                )
            for excerpt in evidence.get("supporting_excerpts") or []:
                lines.append(f"excerpt: {excerpt}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
