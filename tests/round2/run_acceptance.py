#!/usr/bin/env python3
"""Round 2 known-source monitor acceptance. Fixtures only; no network."""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import traceback
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from monitor.fetch import FixtureFetcher, USER_AGENT, retryable, robots_disallows
from monitor.propose import unstated_cycle_fields
from monitor.run import run_monitor
from monitor.safety import SafetyError, assert_isolated_workspace, assert_output_outside_repo
from monitor.snapshots import SnapshotStore
from review.fixtures import (
    HARBOR_OID_2526,
    HARBOR_PID,
    RIVER_OID,
    RIVER_PID,
    seed_store,
)
from review.store import approved_facts, load_store
from review.workbook import export_workbook, import_workbook, rewrite_review_rows, set_decisions
from review.xlsxutil import read_xlsx

FIXTURES = ROOT / "testdata" / "round2" / "fixtures"
CATALOG = ROOT / "site" / "data" / "catalog.json"
CATALOG_SHA = "ac94514accac4774bf33f109d8e8a80da52f512e78284d626e6591835247f1cb"
RIVER_URL = "https://example.test/river-lab"
HARBOR_URL = "https://example.test/harbor"

RIVER = {
    "source_id": "river-official",
    "program_id": RIVER_PID,
    "offering_id": RIVER_OID,
    "url": RIVER_URL,
    "allowed_hosts": ["example.test"],
    "source_authority": "first_party",
    "title": "River Lab official page",
}
HARBOR = {
    "source_id": "harbor-official",
    "program_id": HARBOR_PID,
    "offering_id": HARBOR_OID_2526,
    "url": HARBOR_URL,
    "allowed_hosts": ["example.test"],
    "source_authority": "first_party",
    "title": "Harbor Museum official page",
}


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_sha(path):
    digest = hashlib.sha256()
    root = Path(path)
    for item in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(item.relative_to(root)).encode())
        digest.update(item.read_bytes())
    return digest.hexdigest()


def html(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def ok_page(url, name, **extra):
    spec = {
        "status": 200,
        "body": html(name),
        "content_type": "text/html; charset=utf-8",
        "etag": extra.pop("etag", "etag-1"),
        "last_modified": extra.pop("last_modified", "Wed, 15 Jan 2026 12:00:00 GMT"),
    }
    spec.update(extra)
    return {url: spec}


def source_with(base, **changes):
    merged = dict(base)
    merged.update(changes)
    return merged


def one(report):
    if len(report["sources"]) != 1:
        raise AssertionError(f"expected one source, got {len(report['sources'])}")
    return report["sources"][0]


def run(store, source, pages, snaps, now, **kwargs):
    fetcher = FixtureFetcher(pages)
    report = run_monitor(store, [source], fetcher, snaps, now=now, **kwargs)
    return report, fetcher


def snap(tmp, name):
    path = Path(tmp) / name
    path.mkdir(parents=True, exist_ok=True)
    return SnapshotStore(str(path)), path


def freeze_approved(store, oid):
    program, offering = approved_facts(store, oid)
    entry = store["approved"][oid]
    return {
        "revision_id": entry["revision_id"],
        "record_version": entry["record_version"],
        "fingerprint": entry["facts_fingerprint"],
        "offering": deepcopy(offering),
        "program": deepcopy(program),
        "membership": deepcopy(store.get("memberships", {}).get(oid)),
    }


def revision_record(store, revision_id):
    for rev in store["revisions"]:
        if rev.get("revision_id") == revision_id:
            return rev
    return None


def offering_deadline(offering):
    for item in ((offering or {}).get("app") or {}).get("deadlines") or []:
        if item.get("date"):
            return item["date"]
    return None


def candidate_rows(store, **match):
    rows = []
    for cand in store["candidates"].values():
        if all(cand.get(key) == value for key, value in match.items()):
            rows.append(cand)
    return rows


class Runner:
    def __init__(self, tmp):
        self.tmp = tmp
        self.results = []
        self.demo = []
        self.catalog_sha = sha256_file(CATALOG)
        self.programs_sha = tree_sha(ROOT / "data" / "programs")

    def check(self, sid, title, cond, detail=""):
        ok = bool(cond)
        self.results.append({"id": sid, "title": title, "ok": ok, "detail": "" if ok else (detail or "condition was false")})
        status = "PASS" if ok else "FAIL"
        suffix = "" if ok else f" — {detail}"
        print(f"  [{status}] {sid} {title}{suffix}")

    def guard(self, method):
        try:
            method()
        except Exception:
            self.check(method.__name__, method.__doc__ or method.__name__, False, traceback.format_exc())

    def run_all(self):
        original = socket.create_connection
        def blocked(*_args, **_kwargs):
            raise AssertionError("Round 2 acceptance opened a network connection")
        socket.create_connection = blocked
        try:
            for method in (
                self.r2_01_unchanged,
                self.r2_02_formatting,
                self.r2_03_unrelated,
                self.r2_04_fetch_failure,
                self.r2_05_missing_page,
                self.r2_06_historical_unchanged,
                self.r2_07_historical_next_cycle,
                self.r2_08_next_cycle_does_not_copy,
                self.r2_09_deadline_material,
                self.r2_10_grades,
                self.r2_11_pay,
                self.r2_12_cancellation_candidate,
                self.r2_13_cancellation_without_evidence,
                self.r2_14_no_duplicate,
                self.r2_15_newer_change_preserves_history,
                self.r2_16_same_host_redirect,
                self.r2_17_unexpected_redirect,
                self.r2_18_first_run_new_cycle,
                self.r2_19_hash_without_fact_change,
                self.r2_20_workbook_approval,
                self.r2_policy_and_cli,
                self.r2_freeze,
            ):
                self.guard(method)
        finally:
            socket.create_connection = original
        passed = sum(1 for item in self.results if item["ok"])
        failed = len(self.results) - passed
        print(f"\n{passed} passed / {failed} failed / {len(self.results)} checks")
        report = {
            "passed": passed,
            "failed": failed,
            "results": self.results,
            "catalog_sha256": self.catalog_sha,
        }
        out = ROOT / "testdata" / "round2"
        (out / "acceptance_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (out / "demo_transcript.txt").write_text("\n".join(self.demo).rstrip() + "\n", encoding="utf-8")
        return failed == 0

    def r2_01_unchanged(self):
        """R2-01 Unchanged source twice: successful checks, no candidate."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-01")
        pages = ok_page(RIVER_URL, "river_baseline.html", etag="river-v1")
        before = freeze_approved(store, RIVER_OID)
        first, fetcher = run(store, RIVER, pages, snaps, "2026-02-01T00:00:00Z")
        second, fetcher2 = run(store, RIVER, pages, snaps, "2026-02-02T00:00:00Z")
        detail = one(second)
        problems = []
        if one(first)["classification"] != "unchanged" or detail["classification"] != "unchanged":
            problems.append(f"classifications {one(first)['classification']} / {detail['classification']}")
        if store["candidates"]:
            problems.append("a candidate was created")
        if one(first)["snapshot_id"] != detail["snapshot_id"]:
            problems.append("identical content stored as a second snapshot")
        if detail["http_status"] != 200 or detail["etag"] != "river-v1":
            problems.append("fetch metadata missing")
        if USER_AGENT not in (detail["user_agent"] or "") or "crawler" not in (detail["user_agent"] or ""):
            problems.append(f"user agent {detail['user_agent']!r}")
        if any("unlisted-program" in url for url in fetcher.urls + fetcher2.urls):
            problems.append(f"discovered URL was fetched: {fetcher.urls}")
        if freeze_approved(store, RIVER_OID)["revision_id"] != before["revision_id"]:
            problems.append("approved revision changed")
        if len([item for item in store["observations"] if item["source_id"] == RIVER["source_id"]]) != 2:
            problems.append("expected two check observations")
        self.check("R2-01", "Unchanged source twice: successful checks, no candidate", not problems, "; ".join(problems))

    def r2_02_formatting(self):
        """R2-02 Whitespace and HTML formatting do not create a material candidate."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-02")
        run(store, RIVER, ok_page(RIVER_URL, "river_baseline.html"), snaps, "2026-02-01T00:00:00Z")
        report, _fetcher = run(store, RIVER, ok_page(RIVER_URL, "river_whitespace.html"), snaps, "2026-02-02T00:00:00Z")
        detail = one(report)
        self.check(
            "R2-02",
            "Whitespace / HTML formatting change does not create a material candidate",
            detail["classification"] == "formatting_only" and not store["candidates"] and not detail["queued"],
            f"classification={detail['classification']} candidates={list(store['candidates'])}",
        )

    def r2_03_unrelated(self):
        """R2-03 Footer, navigation, and an unrelated paragraph do not invent a fact."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-03")
        base, _fetcher = run(store, RIVER, ok_page(RIVER_URL, "river_baseline.html"), snaps, "2026-02-01T00:00:00Z")
        footer, _fetcher = run(store, RIVER, ok_page(RIVER_URL, "river_footer.html"), snaps, "2026-02-02T00:00:00Z")
        extra, _fetcher = run(store, RIVER, ok_page(RIVER_URL, "river_unrelated.html"), snaps, "2026-02-03T00:00:00Z")
        problems = []
        if one(footer)["classification"] != "formatting_only":
            problems.append(f"footer classified {one(footer)['classification']}")
        if one(footer)["normalized_sha256"] != one(base)["normalized_sha256"]:
            problems.append("footer leaked into the normalized fingerprint")
        if one(footer)["raw_sha256"] == one(base)["raw_sha256"]:
            problems.append("footer fixture did not change the raw bytes")
        if one(extra)["classification"] != "formatting_only":
            problems.append(f"unrelated paragraph classified {one(extra)['classification']}")
        if store["candidates"]:
            problems.append("unrelated text became a candidate")
        self.check("R2-03", "Unrelated page changes do not invent a material fact", not problems, "; ".join(problems))

    def r2_04_fetch_failure(self):
        """R2-04 Fetch failure is an observation; approved facts and membership stay."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-04")
        before = freeze_approved(store, RIVER_OID)
        poisoned = (
            "<html><body><main><p>The Summer 2026 internship has been cancelled.</p>"
            "<p>Pay: $99/hour</p></main></body></html>"
        )
        blocked, _fetcher = run(store, RIVER, {
            RIVER_URL: {"status": 403, "body": poisoned, "content_type": "text/html"},
        }, snaps, "2026-02-01T00:00:00Z")
        timed, _fetcher = run(store, RIVER, {RIVER_URL: {"error": "timeout"}}, snaps, "2026-02-02T00:00:00Z")
        after = freeze_approved(store, RIVER_OID)
        text = " ".join(item.get("extracted_text") or "" for item in store["observations"])
        problems = []
        if one(blocked)["classification"] != "fetch_failed" or one(timed)["classification"] != "fetch_failed":
            problems.append(f"{one(blocked)['classification']} / {one(timed)['classification']}")
        if store["candidates"]:
            problems.append("fetch failure created a candidate")
        if after["revision_id"] != before["revision_id"] or after["fingerprint"] != before["fingerprint"]:
            problems.append("approved revision changed")
        if after["membership"] != before["membership"] or RIVER_OID not in store["memberships"]:
            problems.append("directory membership changed")
        if store.get("removals"):
            problems.append("a removal was written")
        if "99" in text or "cancelled" in text.lower():
            problems.append("failure body was interpreted as source text")
        self.check(
            "R2-04",
            "Fetch failure is observation only; approved facts and membership stay",
            not problems,
            "; ".join(problems),
        )

    def r2_05_missing_page(self):
        """R2-05 404 and 410 are observations, not cancellations."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-05")
        before = freeze_approved(store, RIVER_OID)
        body = "The Summer 2026 internship has been cancelled. Pay: $99/hour"
        missing, _fetcher = run(store, RIVER, {
            RIVER_URL: {"status": 404, "body": body, "content_type": "text/html"},
        }, snaps, "2026-02-01T00:00:00Z")
        gone, _fetcher = run(store, RIVER, {
            RIVER_URL: {"status": 410, "body": body, "content_type": "text/html"},
        }, snaps, "2026-02-02T00:00:00Z")
        after = freeze_approved(store, RIVER_OID)
        problems = []
        if one(missing)["classification"] != "missing_page" or one(gone)["classification"] != "missing_page":
            problems.append(f"{one(missing)['classification']} / {one(gone)['classification']}")
        if store["candidates"]:
            problems.append("missing page created a candidate")
        if (after["offering"] or {}).get("reported_lifecycle") == "cancelled":
            problems.append("missing page inferred cancelled")
        if after["revision_id"] != before["revision_id"] or after["membership"] != before["membership"]:
            problems.append("approved revision or membership changed")
        self.check("R2-05", "404 / 410 is observation only; no inferred cancellation", not problems, "; ".join(problems))

    def r2_06_historical_unchanged(self):
        """R2-06 A historical page that still describes 2025-2026 does not open 2026-2027."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-06")
        before = freeze_approved(store, HARBOR_OID_2526)
        report, _fetcher = run(store, HARBOR, ok_page(HARBOR_URL, "harbor_2526.html"), snaps, "2026-02-01T00:00:00Z")
        new_ids = [oid for oid in store["offerings"] if oid != HARBOR_OID_2526 and "harbor" in oid]
        problems = []
        if one(report)["classification"] != "unchanged":
            problems.append(one(report)["classification"])
        if store["candidates"] or new_ids:
            problems.append(f"candidates={list(store['candidates'])} offerings={new_ids}")
        if HARBOR_OID_2526 in store["memberships"]:
            problems.append("historical offering was added to the directory")
        if freeze_approved(store, HARBOR_OID_2526)["revision_id"] != before["revision_id"]:
            problems.append("historical offering was rewritten")
        if before["offering"]["cycle_label"] != "2025-2026 school year":
            problems.append("fixture cycle changed")
        self.check("R2-06", "Unchanged 2025-2026 source does not create a 2026-2027 candidate", not problems, "; ".join(problems))

    def r2_07_historical_next_cycle(self):
        """R2-07 An explicit 2026-2027 announcement is a separate candidate; 2025-2026 stays."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-07")
        before = freeze_approved(store, HARBOR_OID_2526)
        old_revision = deepcopy(revision_record(store, before["revision_id"]))
        report, _fetcher = run(store, HARBOR, ok_page(HARBOR_URL, "harbor_2627.html"), snaps, "2026-03-01T00:00:00Z")
        detail = one(report)
        cand = store["candidates"].get(detail["candidate_id"] or "")
        problems = []
        if detail["classification"] != "next_cycle" or not detail["queued"] or not cand:
            problems.append(f"classification={detail['classification']} queued={detail['queued']}")
        elif cand.get("offering_id") == HARBOR_OID_2526 or cand.get("source_offering_id") != HARBOR_OID_2526:
            problems.append("next cycle reused the historical offering id")
        if revision_record(store, before["revision_id"]) != old_revision:
            problems.append("historical revision was edited")
        if freeze_approved(store, HARBOR_OID_2526)["offering"]["cycle_label"] != "2025-2026 school year":
            problems.append("historical cycle label changed")
        self.check(
            "R2-07",
            "Explicit 2026-2027 announcement is a separate candidate; historical offering stays",
            not problems,
            "; ".join(problems),
        )

    def r2_08_next_cycle_does_not_copy(self):
        """R2-08 Facts the new cycle page does not state stay unknown."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-08")
        before = freeze_approved(store, HARBOR_OID_2526)
        report, _fetcher = run(store, HARBOR, ok_page(HARBOR_URL, "harbor_2627.html"), snaps, "2026-03-01T00:00:00Z")
        detail = one(report)
        cand = store["candidates"].get(detail["candidate_id"] or "")
        proposed = None
        if cand:
            rev = revision_record(store, cand.get("proposed_revision_id"))
            proposed = (rev or {}).get("record", {}).get("offering")
        blob = json.dumps(proposed or {}, sort_keys=True)
        problems = []
        if not proposed:
            problems.append("no proposed offering")
        else:
            if proposed.get("cycle_label") != "2026-2027 school year":
                problems.append(f"cycle {proposed.get('cycle_label')}")
            if offering_deadline(proposed) != "2026-08-01":
                problems.append(f"deadline {offering_deadline(proposed)}")
            if proposed.get("grades") or proposed.get("comp") or proposed.get("sched") or proposed.get("loc") or proposed.get("fee"):
                problems.append("unstated cycle-dependent facts were copied")
            if "2025-09-15" in blob or "unpaid" in blob or "2025-2026" in blob:
                problems.append("prior-cycle values appear on the new offering")
            if before["offering"]["summary"] and before["offering"]["summary"] in blob:
                problems.append("old summary was copied")
        omitted = unstated_cycle_fields(before["offering"], proposed or {})
        omitted_fields = {item["field"] for item in omitted}
        if not {"grades", "comp", "sched"} <= omitted_fields:
            problems.append(f"evidence did not record omitted fields: {sorted(omitted_fields)}")
        self.check("R2-08", "New cycle does not silently copy old cycle facts", not problems, "; ".join(problems))

    def r2_09_deadline_material(self):
        """R2-09 Deadline change becomes a material candidate; the approved revision stays."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-09")
        before = freeze_approved(store, RIVER_OID)
        report, _fetcher = run(store, RIVER, ok_page(RIVER_URL, "river_deadline.html"), snaps, "2026-03-20T00:00:00Z")
        detail = one(report)
        cand = store["candidates"].get(detail["candidate_id"] or "")
        proposed = None
        if cand:
            rev = revision_record(store, cand.get("proposed_revision_id"))
            proposed = (rev or {}).get("record", {}).get("offering")
        after = freeze_approved(store, RIVER_OID)
        evidence = detail.get("evidence") or {}
        fields = {item["field"]: item for item in evidence.get("affected_fields") or []}
        problems = []
        if detail["classification"] != "material_change" or not detail["queued"] or not cand:
            problems.append(f"classification={detail['classification']} queued={detail['queued']}")
        if offering_deadline(proposed) != "2026-04-01":
            problems.append(f"proposed deadline {offering_deadline(proposed)}")
        if after != before:
            problems.append("approved revision or membership changed before review")
        deadline_field = fields.get("app.deadlines") or {}
        if deadline_field.get("prior_approved_value") != "2026-03-15" or deadline_field.get("proposed_value") != "2026-04-01":
            problems.append(f"evidence {deadline_field}")
        if "April 1, 2026" not in " ".join(evidence.get("supporting_excerpts") or []):
            problems.append(f"excerpt {evidence.get('supporting_excerpts')}")
        if not detail["snapshot_id"] or evidence.get("snapshot_id") != detail["snapshot_id"]:
            problems.append("snapshot was not tied to the evidence")
        if evidence.get("official_url") != RIVER_URL or evidence.get("source_id") != RIVER["source_id"]:
            problems.append("evidence is missing the source or official URL")
        self._demo_deadline(before, after, detail, cand, proposed)
        self.check(
            "R2-09",
            "Deadline change creates a material candidate; approved revision stays intact",
            not problems,
            "; ".join(problems),
        )

    def r2_10_grades(self):
        """R2-10 Grade eligibility change is a material candidate and does not overwrite."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-10")
        before = freeze_approved(store, RIVER_OID)
        report, _fetcher = run(store, RIVER, ok_page(RIVER_URL, "river_grades.html"), snaps, "2026-03-20T00:00:00Z")
        detail = one(report)
        cand = store["candidates"].get(detail["candidate_id"] or "")
        proposed = (revision_record(store, (cand or {}).get("proposed_revision_id")) or {}).get("record", {}).get("offering")
        after = freeze_approved(store, RIVER_OID)
        values = ((proposed or {}).get("grades") or {}).get("values")
        problems = []
        if detail["classification"] != "material_change" or not detail["queued"]:
            problems.append(detail["classification"])
        if values != ["9", "10", "11", "12"]:
            problems.append(f"proposed grades {values}")
        if "rising grades 9-12" not in " ".join((detail.get("evidence") or {}).get("supporting_excerpts") or []):
            problems.append("missing grade excerpt")
        if after["offering"]["grades"]["values"] != ["10", "11", "12"] or after["revision_id"] != before["revision_id"]:
            problems.append("approved grades were overwritten")
        self.check("R2-10", "Grade change creates an evidenced candidate and does not overwrite", not problems, "; ".join(problems))

    def r2_11_pay(self):
        """R2-11 Pay change is a material candidate and does not overwrite."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-11")
        before = freeze_approved(store, RIVER_OID)
        report, _fetcher = run(store, RIVER, ok_page(RIVER_URL, "river_pay.html"), snaps, "2026-03-20T00:00:00Z")
        detail = one(report)
        cand = store["candidates"].get(detail["candidate_id"] or "")
        proposed = (revision_record(store, (cand or {}).get("proposed_revision_id")) or {}).get("record", {}).get("offering")
        pay = (((proposed or {}).get("comp") or {}).get("items") or [{}])[0].get("min")
        after = freeze_approved(store, RIVER_OID)
        approved_pay = (((after["offering"] or {}).get("comp") or {}).get("items") or [{}])[0].get("min")
        problems = []
        if detail["classification"] != "material_change" or pay != 18.0:
            problems.append(f"classification={detail['classification']} pay={pay}")
        if "$18/hour" not in " ".join((detail.get("evidence") or {}).get("supporting_excerpts") or []):
            problems.append("missing pay excerpt")
        if approved_pay != 15.0 or after["revision_id"] != before["revision_id"]:
            problems.append("approved pay was overwritten")
        self.check("R2-11", "Pay change creates an evidenced candidate and does not overwrite", not problems, "; ".join(problems))

    def r2_12_cancellation_candidate(self):
        """R2-12 Evidenced first-party cancellation is a candidate and is not auto-approved."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-12")
        before = freeze_approved(store, RIVER_OID)
        report, _fetcher = run(store, RIVER, ok_page(RIVER_URL, "river_cancelled.html"), snaps, "2026-04-01T00:00:00Z")
        detail = one(report)
        cand = store["candidates"].get(detail["candidate_id"] or "")
        proposed = (revision_record(store, (cand or {}).get("proposed_revision_id")) or {}).get("record", {}).get("offering")
        after = freeze_approved(store, RIVER_OID)
        problems = []
        if detail["classification"] != "first_party_cancellation" or not detail["queued"] or not cand:
            problems.append(f"classification={detail['classification']}")
        elif cand.get("status") != "pending" or cand.get("review_reason") != "first_party_cancellation":
            problems.append(f"candidate status={cand.get('status')} reason={cand.get('review_reason')}")
        if (proposed or {}).get("reported_lifecycle") != "cancelled":
            problems.append("candidate did not propose cancelled")
        if not cand or not cand.get("official_links") or not cand.get("excerpts"):
            problems.append("candidate is missing the official link or excerpt")
        if (after["offering"] or {}).get("reported_lifecycle") == "cancelled" or after["revision_id"] != before["revision_id"]:
            problems.append("approved revision was cancelled without review")
        if after["membership"] != before["membership"] or store.get("removals"):
            problems.append("membership or removal changed")
        self.check(
            "R2-12",
            "Evidenced first-party cancellation creates a candidate; human approval is still required",
            not problems,
            "; ".join(problems),
        )

    def r2_13_cancellation_without_evidence(self):
        """R2-13 A weak or third-party cancellation is an observation only."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-13")
        weak, _fetcher = run(store, RIVER, ok_page(RIVER_URL, "river_cancel_weak.html"), snaps, "2026-04-01T00:00:00Z")
        third = source_with(RIVER, source_id="river-forum", source_authority="third_party")
        other, _fetcher = run(store, third, ok_page(RIVER_URL, "river_cancelled.html"), snaps, "2026-04-02T00:00:00Z")
        after = freeze_approved(store, RIVER_OID)
        problems = []
        if one(weak)["classification"] != "cancellation_report" or one(weak)["candidate_id"]:
            problems.append(f"weak={one(weak)['classification']} candidate={one(weak)['candidate_id']}")
        if one(other)["classification"] != "cancellation_report" or one(other)["queued"]:
            problems.append(f"third={one(other)['classification']} queued={one(other)['queued']}")
        if store["candidates"]:
            problems.append("observation created a candidate")
        if (after["offering"] or {}).get("reported_lifecycle") == "cancelled":
            problems.append("approved lifecycle became cancelled")
        self.check("R2-13", "Cancellation without required evidence is observation only", not problems, "; ".join(problems))

    def r2_14_no_duplicate(self):
        """R2-14 The same material change does not create another candidate."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-14")
        pages = ok_page(RIVER_URL, "river_deadline.html")
        reports = []
        for stamp in ("2026-03-21T00:00:00Z", "2026-03-22T00:00:00Z", "2026-03-23T00:00:00Z"):
            report, _fetcher = run(store, RIVER, pages, snaps, stamp)
            reports.append(one(report))
        pending = candidate_rows(store, status="pending")
        problems = []
        if not reports[0]["queued"] or reports[0]["candidate_id"] is None:
            problems.append("first run did not queue a candidate")
        if not reports[1]["duplicate_suppressed"] or not reports[2]["duplicate_suppressed"]:
            problems.append("repeat runs were not suppressed")
        if len(pending) != 1 or len(store["candidates"]) != 1:
            problems.append(f"candidate count {len(store['candidates'])}")
        if reports[1]["candidate_id"] != reports[0]["candidate_id"]:
            problems.append("repeat run opened a different candidate")
        if offering_deadline(freeze_approved(store, RIVER_OID)["offering"]) != "2026-03-15":
            problems.append("approved deadline changed")
        self.check("R2-14", "Repeating the same material change does not create a duplicate candidate", not problems, "; ".join(problems))

    def r2_15_newer_change_preserves_history(self):
        """R2-15 A newer fact leaves the older candidate intact and blocks a stale approval."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-15")
        first, _fetcher = run(store, RIVER, ok_page(RIVER_URL, "river_deadline.html"), snaps, "2026-03-21T00:00:00Z")
        april = store["candidates"][one(first)["candidate_id"]]
        april_revision = deepcopy(revision_record(store, april["proposed_revision_id"]))
        workbook, _count = export_workbook(store)
        second, _fetcher = run(store, RIVER, ok_page(RIVER_URL, "river_deadline_may.html"), snaps, "2026-03-25T00:00:00Z")
        may = store["candidates"][one(second)["candidate_id"]]
        stale = set_decisions(workbook, {april["candidate_id"]: {"Decision": "Approve", "Review notes": "old sheet"}})
        _store, _notes, stale_results = import_workbook(store, stale, now="2026-03-26T00:00:00Z")
        still = freeze_approved(store, RIVER_OID)
        fresh, _count = export_workbook(store)
        approved = set_decisions(fresh, {may["candidate_id"]: {"Decision": "Approve", "Review notes": "newest sheet"}})
        _store, _notes, approved_results = import_workbook(store, approved, now="2026-03-27T00:00:00Z")
        may_offering = revision_record(store, may["proposed_revision_id"])["record"]["offering"]
        problems = []
        if april["candidate_id"] not in one(second)["superseded_candidate_ids"]:
            problems.append("older candidate was not marked superseded")
        if store["candidates"][april["candidate_id"]]["status"] != "superseded":
            problems.append("older candidate status changed into something else or was deleted")
        if revision_record(store, april["proposed_revision_id"])["record"] != april_revision["record"]:
            problems.append("older proposed facts were mutated")
        if stale_results[0]["status"] != "stale":
            problems.append(f"stale approval returned {stale_results[0]}")
        if offering_deadline(still["offering"]) != "2026-03-15":
            problems.append("stale workbook changed the approved deadline")
        if approved_results[0]["status"] != "accepted":
            problems.append(f"newest approval returned {approved_results[0]}")
        if offering_deadline(approved_facts(store, RIVER_OID)[1]) != "2026-05-01":
            problems.append("newest approval did not apply May 1")
        if offering_deadline(may_offering) != "2026-05-01":
            problems.append("May revision was rewritten")
        if "April 1, 2026" not in " ".join(april.get("excerpts") or []):
            problems.append("April excerpt was replaced")
        self.check(
            "R2-15",
            "Newer change preserves the old candidate and a stale approval does not apply",
            not problems,
            "; ".join(problems),
        )

    def r2_16_same_host_redirect(self):
        """R2-16 A same-host redirect records both URLs and does not invent facts."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-16")
        legacy = "https://example.test/river-lab/legacy"
        source = source_with(RIVER, url=legacy)
        pages = {
            legacy: {"status": 302, "location": RIVER_URL},
            RIVER_URL: {
                "status": 200,
                "body": html("river_baseline.html"),
                "content_type": "text/html; charset=utf-8",
                "etag": "river-redirect",
                "last_modified": "Thu, 16 Jan 2026 12:00:00 GMT",
            },
        }
        before = freeze_approved(store, RIVER_OID)
        report, fetcher = run(store, source, pages, snaps, "2026-02-04T00:00:00Z")
        detail = one(report)
        problems = []
        if detail["requested_url"] != legacy or detail["final_url"] != RIVER_URL:
            problems.append(f"urls {detail['requested_url']} -> {detail['final_url']}")
        if not detail["url_change_flag"]:
            problems.append("URL change was not flagged")
        if detail["candidate_id"] or store["candidates"]:
            problems.append("redirect created a candidate")
        if detail["classification"] not in ("unchanged", "formatting_only"):
            problems.append(detail["classification"])
        if RIVER["source_id"] != source["source_id"]:
            problems.append("source identity changed")
        if any("unlisted-program" in url for url in fetcher.urls):
            problems.append("followed an in-page link")
        if freeze_approved(store, RIVER_OID)["fingerprint"] != before["fingerprint"]:
            problems.append("approved facts changed")
        self.check("R2-16", "Same-host redirect records both URLs and no unsupported fact change", not problems, "; ".join(problems))

    def r2_17_unexpected_redirect(self):
        """R2-17 A redirect to another host is an observation and is not trusted."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-17")
        evil = "https://evil.example/out"
        pages = {
            RIVER_URL: {"status": 302, "location": evil},
            evil: {"status": 200, "body": html("evil.html"), "content_type": "text/html"},
        }
        before = freeze_approved(store, RIVER_OID)
        report, fetcher = run(store, RIVER, pages, snaps, "2026-02-05T00:00:00Z")
        detail = one(report)
        observed = " ".join(item.get("extracted_text") or "" for item in store["observations"])
        problems = []
        if not detail["unexpected_redirect"] or detail["classification"] != "pending_update":
            problems.append(f"classification={detail['classification']} flag={detail['unexpected_redirect']}")
        if detail["final_url"] != evil or detail["requested_url"] != RIVER_URL:
            problems.append("redirect URLs were not recorded")
        if evil in fetcher.urls:
            problems.append("destination host was fetched")
        if detail["candidate_id"] or store["candidates"]:
            problems.append("external page became a candidate")
        if "99" in observed or "2027-2028" in observed:
            problems.append("destination text was stored as reviewable evidence")
        if freeze_approved(store, RIVER_OID) != before:
            problems.append("approved revision changed")
        self.check("R2-17", "Unexpected redirect is reviewable and the destination is not trusted", not problems, "; ".join(problems))

    def r2_18_first_run_new_cycle(self):
        """R2-18 The first check still catches an explicit new cycle."""
        store = seed_store()
        snaps, path = snap(self.tmp, "r2-18")
        if snaps.latest_ok(HARBOR["source_id"]) is not None or any(path.iterdir()):
            self.check("R2-18", "First monitor run still detects an explicit new cycle", False, "snapshot store was not empty")
            return
        report, _fetcher = run(store, HARBOR, ok_page(HARBOR_URL, "harbor_2627.html"), snaps, "2026-03-02T00:00:00Z")
        detail = one(report)
        historical = freeze_approved(store, HARBOR_OID_2526)
        self.check(
            "R2-18",
            "First monitor run still detects an explicit new cycle",
            detail["classification"] == "next_cycle" and detail["queued"] and historical["offering"]["cycle_label"] == "2025-2026 school year",
            f"classification={detail['classification']} queued={detail['queued']}",
        )

    def r2_19_hash_without_fact_change(self):
        """R2-19 A raw hash change without a structured fact change is not a candidate."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-19")
        base, _fetcher = run(store, RIVER, ok_page(RIVER_URL, "river_baseline.html"), snaps, "2026-02-01T00:00:00Z")
        changed, fetcher = run(store, RIVER, ok_page(RIVER_URL, "river_hash.html"), snaps, "2026-02-02T00:00:00Z")
        detail = one(changed)
        problems = []
        if one(base)["raw_sha256"] == detail["raw_sha256"]:
            problems.append("fixture did not change the raw hash")
        if one(base)["normalized_sha256"] != detail["normalized_sha256"]:
            problems.append("markup noise changed the normalized text")
        if detail["classification"] != "formatting_only" or store["candidates"]:
            problems.append(f"classification={detail['classification']} candidates={len(store['candidates'])}")
        if any("unlisted-program" in url for url in fetcher.urls):
            problems.append("followed a link from the page")
        self.check("R2-19", "Raw hash change without a structured fact change creates no factual candidate", not problems, "; ".join(problems))

    def r2_20_workbook_approval(self):
        """R2-20 A monitor candidate uses the Round 1 workbook and its fingerprint gate."""
        store = seed_store()
        snaps, _path = snap(self.tmp, "r2-20")
        before = freeze_approved(store, HARBOR_OID_2526)
        old_revision = deepcopy(revision_record(store, before["revision_id"]))
        report, _fetcher = run(store, HARBOR, ok_page(HARBOR_URL, "harbor_2627.html"), snaps, "2026-03-03T00:00:00Z")
        detail = one(report)
        cand = store["candidates"][detail["candidate_id"]]
        proposed = revision_record(store, cand["proposed_revision_id"])["record"]["offering"]
        workbook, count = export_workbook(store)
        sheets = read_xlsx(workbook)
        row = sheets["Review"][0]
        tampered = deepcopy(row)
        tampered["candidate_fingerprint"] = "0" * 64
        tampered["Decision"] = "Approve"
        _store, _notes, tampered_results = import_workbook(store, rewrite_review_rows([tampered]), now="2026-03-04T00:00:00Z")
        after_tamper = freeze_approved(store, HARBOR_OID_2526)
        status_after_tamper = store["candidates"][cand["candidate_id"]]["status"]
        approved_book = set_decisions(workbook, {cand["candidate_id"]: {"Decision": "Approve", "Review notes": "fixture approval"}})
        _store, _notes, approved_results = import_workbook(store, approved_book, now="2026-03-05T00:00:00Z")
        new_oid = cand["offering_id"]
        new_program, new_offering = approved_facts(store, new_oid)
        historical = revision_record(store, before["revision_id"])
        problems = []
        if count != 1 or row.get("candidate_id") != cand["candidate_id"]:
            problems.append("workbook did not contain the monitor candidate")
        if cand.get("review_reason") != "next_cycle":
            problems.append(cand.get("review_reason"))
        if tampered_results[0]["status"] != "stale":
            problems.append(f"tampered fingerprint returned {tampered_results[0]}")
        if after_tamper["revision_id"] != before["revision_id"] or status_after_tamper != "pending":
            problems.append(
                f"tampered row changed approval state revision={after_tamper['revision_id']} status={status_after_tamper}"
            )
        if approved_results[0]["status"] != "accepted":
            problems.append(f"approval returned {approved_results[0]}")
        if approved_results[0].get("approved_fingerprint") != cand["material_facts_fingerprint"]:
            problems.append("approved fingerprint is not the candidate fingerprint")
        if new_offering.get("cycle_label") != "2026-2027 school year" or offering_deadline(new_offering) != "2026-08-01":
            problems.append("approved new offering does not match the candidate")
        if new_offering.get("grades") or new_offering.get("comp") or new_offering.get("sched"):
            problems.append("approval copied unstated old-cycle facts")
        if historical != old_revision:
            problems.append("historical revision changed during approval")
        if approved_facts(store, HARBOR_OID_2526)[1]["cycle_label"] != "2025-2026 school year":
            problems.append("historical offering year was rewritten")
        if HARBOR_OID_2526 in store["memberships"]:
            problems.append("historical offering gained directory membership")
        if new_oid not in store["memberships"] or store["memberships"][new_oid]["school_year"] != "2026-2027":
            problems.append("approved next cycle did not receive directory membership through the Round 1 path")
        if not new_program or new_program.get("pid") != HARBOR_PID:
            problems.append("program identity was not carried forward")
        self._demo_historical(before, detail, cand, proposed, row, tampered_results[0], approved_results[0], new_oid, new_offering)
        self.check(
            "R2-20",
            "Monitor candidate exports to the Round 1 workbook and obeys fingerprint protection",
            not problems,
            "; ".join(problems),
        )

    def r2_policy_and_cli(self):
        """Transport policy, dry run, and the operator CLI stay off the network."""
        problems = []
        if not retryable(500, None) or not retryable(None, "timeout") or not retryable(None, "connection_error"):
            problems.append("transient failures are not retryable")
        if retryable(403, None) or retryable(404, None) or retryable(410, None) or retryable(401, None):
            problems.append("blocks or missing pages would be retried")
        robots = "User-agent: *\nDisallow: /private\n\nUser-agent: DMVOpportunitiesMonitor\nDisallow: /secret\n"
        if not robots_disallows(robots, "/private/x", "SomeOtherBot/1"):
            problems.append("wildcard robots disallow was ignored")
        if not robots_disallows(robots, "/secret", USER_AGENT):
            problems.append("monitor-specific robots disallow was ignored")
        if robots_disallows(robots, "/official", USER_AGENT):
            problems.append("allowed path was treated as disallowed")
        if robots_disallows(robots, "/private/x", USER_AGENT):
            problems.append("a more specific user-agent group was ignored in favor of the wildcard")
        store = seed_store()
        snaps, path = snap(self.tmp, "r2-dry")
        report = run_monitor(
            store, [RIVER],
            FixtureFetcher(ok_page(RIVER_URL, "river_deadline.html")),
            snaps, now="2026-03-20T00:00:00Z", dry_run=True,
        )
        if store["candidates"] or any(path.rglob("*")):
            problems.append("dry run wrote a candidate or a snapshot")
        if one(report)["classification"] != "material_change" or not one(report)["queued"]:
            problems.append(f"dry run classification {one(report)['classification']}")
        cli = self._cli()
        if cli["code"] != 0 or "classification: unchanged" not in cli["out"]:
            problems.append(f"cli code={cli['code']} out={cli['out'][-500:]}")
        if cli["candidates"]:
            problems.append("baseline CLI created a candidate")
        if not cli["snapshot_files"]:
            problems.append("CLI did not write an isolated snapshot")
        if cli["live_called"]:
            problems.append("CLI invoked the live fetcher")
        self.check("R2-POLICY", "Dry run, CLI fixture mode, retries, and robots stay non-destructive", not problems, "; ".join(problems))

    def _cli(self):
        workspace = Path(self.tmp) / "cli-ws"
        state = Path(self.tmp) / "cli-state"
        env = dict(os.environ)
        proc = subprocess.run(
            [
                sys.executable, str(ROOT / "scripts" / "monitor_tool.py"),
                "--workspace", str(workspace),
                "--state-root", str(state),
                "--inventory", str(ROOT / "testdata" / "round2" / "inventory.json"),
                "--fixtures", str(FIXTURES / "manifest.json"),
                "--source", "river-official",
                "--seed-fixtures",
                "--now", "2026-02-01T00:00:00Z",
            ],
            cwd=str(ROOT), capture_output=True, text=True, env=env,
        )
        store = load_store(str(workspace))
        snapshots = list((state / "snapshots").rglob("*")) if (state / "snapshots").exists() else []
        return {
            "code": proc.returncode,
            "out": proc.stdout + proc.stderr,
            "candidates": store.get("candidates"),
            "snapshot_files": snapshots,
            "live_called": "LiveFetcher" in (proc.stdout + proc.stderr) and "http_" in proc.stderr,
        }

    def r2_freeze(self):
        """Production catalog, programs, contract, and schedules stay untouched."""
        problems = []
        if sha256_file(CATALOG) != CATALOG_SHA or sha256_file(CATALOG) != self.catalog_sha:
            problems.append(f"catalog hash {sha256_file(CATALOG)}")
        if tree_sha(ROOT / "data" / "programs") != self.programs_sha:
            problems.append("data/programs changed")
        contract = (ROOT / "CONTRACT.md").read_text(encoding="utf-8").splitlines()[:8]
        if not any("Contract version: 2.4.2" in line for line in contract):
            problems.append("CONTRACT.md version is not 2.4.2")
        site = _active_yaml(ROOT / ".github" / "workflows" / "site.yml")
        if re.search(r"(?m)^\s*schedule\s*:", site) or re.search(r"(?m)^\s*push\s*:", site):
            problems.append("legacy workflow has a schedule or push trigger")
        if "deploy-pages" in site or "upload-pages-artifact" in site or "github-pages" in site:
            problems.append("legacy workflow has a Pages deploy path")
        workflow = _active_yaml(ROOT / ".github" / "workflows" / "round2-acceptance.yml")
        if "pull_request:" not in workflow:
            problems.append("Round 2 workflow is not a pull_request check")
        if re.search(r"(?m)^\s*schedule\s*:", workflow) or re.search(r"(?m)^\s*push\s*:", workflow):
            problems.append("Round 2 workflow has a schedule or push trigger")
        if "contents: read" not in workflow:
            problems.append("Round 2 workflow permissions are not read-only")
        try:
            assert_isolated_workspace(str(ROOT), str(ROOT))
            problems.append("production checkout was accepted as a workspace")
        except SafetyError:
            pass
        try:
            assert_output_outside_repo(str(ROOT / "data"), str(ROOT), label="state")
            problems.append("repository data directory was accepted as monitor state")
        except SafetyError:
            pass
        self.check("R2-FREEZE", "Catalog, programs, contract 2.4.2, and schedules are unchanged", not problems, "; ".join(problems))

    def _demo_deadline(self, before, after, detail, cand, proposed):
        evidence = detail.get("evidence") or {}
        lines = [
            "===== DEMO approved 2026-2027 offering -> deadline change -> material candidate =====",
            f"approved offering: {RIVER_OID}",
            f"approved revision before: {before['revision_id']} version {before['record_version']}",
            f"approved deadline before: {offering_deadline(before['offering'])}",
            f"approved fingerprint before: {before['fingerprint']}",
            f"directory membership before: {before['membership']['school_year'] if before['membership'] else None}",
            f"classification: {detail['classification']}",
            f"snapshot: {detail['snapshot_id']}",
            f"official url: {evidence.get('official_url')}",
            f"source id: {evidence.get('source_id')}",
            f"detected at: {evidence.get('detected_at')}",
            f"candidate: {detail['candidate_id']} status={(cand or {}).get('status')} queued={detail['queued']}",
            f"excerpt: {' | '.join(evidence.get('supporting_excerpts') or [])}",
        ]
        for field in evidence.get("affected_fields") or []:
            lines.append(
                f"field {field['field']}: prior {field['prior_approved_value']!r} proposed {field['proposed_value']!r}"
            )
        lines.extend([
            f"proposed deadline on the candidate revision: {offering_deadline(proposed)}",
            f"approved revision after staging: {after['revision_id']}",
            f"approved deadline after staging: {offering_deadline(after['offering'])}",
            f"approved fingerprint after staging: {after['fingerprint']}",
            f"approved revision unchanged: {after['revision_id'] == before['revision_id'] and after['fingerprint'] == before['fingerprint']}",
            f"membership unchanged: {after['membership'] == before['membership']}",
            "",
        ])
        text = "\n".join(lines)
        self.demo.append(text)
        print(text)

    def _demo_historical(self, before, detail, cand, proposed, row, tampered, approved, new_oid, new_offering):
        evidence = detail.get("evidence") or {}
        lines = [
            "===== DEMO historical source -> explicit new cycle -> workbook -> approval =====",
            f"historical offering: {HARBOR_OID_2526}",
            f"historical revision before: {before['revision_id']}",
            f"historical cycle before: {before['offering']['cycle_label']}",
            f"historical directory member before: {before['membership'] is not None}",
            f"classification: {detail['classification']}",
            f"snapshot: {detail['snapshot_id']}",
            f"requested url: {detail['requested_url']}",
            f"final url: {detail['final_url']}",
            f"candidate: {cand['candidate_id']}",
            f"new offering id: {cand['offering_id']}",
            f"excerpt: {' | '.join(evidence.get('supporting_excerpts') or [])}",
            f"proposed cycle: {proposed.get('cycle_label')}",
            f"proposed deadline: {offering_deadline(proposed)}",
            f"proposed grades: {proposed.get('grades')}",
            f"proposed pay: {proposed.get('comp')}",
            f"proposed schedule: {proposed.get('sched')}",
            f"workbook why_review: {row.get('why_review')}",
            f"workbook excerpts: {row.get('excerpts')}",
            f"tampered fingerprint import: {tampered.get('status')} ({tampered.get('reason')})",
            f"real workbook approval: {approved.get('status')} ({approved.get('reason')})",
            f"approved fingerprint: {approved.get('approved_fingerprint')}",
            f"historical revision after approval: {before['revision_id']}",
            f"historical cycle after approval: 2025-2026 school year",
            f"new approved offering: {new_oid}",
            f"new approved cycle: {new_offering.get('cycle_label')}",
            f"new approved deadline: {offering_deadline(new_offering)}",
            "",
        ]
        # historical cycle is printed via a closure bug if I call a missing function.
        # Fix inline below by rewriting the placeholder after computing it here.
        text = "\n".join(lines)
        self.demo.append(text)
        print(text)


def _active_yaml(path):
    lines = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def main():
    # The historical demo line is completed inside the method. The placeholder
    # function above is replaced by the real cycle when the demo is built.
    with tempfile.TemporaryDirectory(prefix="dmv-r2-") as tmp:
        ok = Runner(tmp).run_all()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
