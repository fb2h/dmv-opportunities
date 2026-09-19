#!/usr/bin/env python3
"""Run the 20 Round 1 acceptance scenarios with fixtures and controlled clocks."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from review.catalog import build_catalog_document, write_catalog_atomic
from review.facts import application_status, lifecycle_status, material_fingerprint
from review.fixtures import (
    HARBOR_OID_2526,
    HARBOR_OID_2627,
    HARBOR_PID,
    PARK_OID,
    PARK_PID,
    RIVER_OID,
    RIVER_PID,
    proposed_harbor_next,
    proposed_river,
    river_source_text,
    seed_store,
)
from review.persist import head_sha, save_store_transaction, sync_from_authoritative
from review.publish import publish_test_catalog
from review.stage import stage_observation
from review.store import (
    approved_facts,
    assign_membership,
    load_notes,
    load_store,
    save_notes,
    store_path,
)
from review.workbook import export_workbook, import_workbook, rewrite_review_rows, set_decisions
from review.xlsxutil import read_xlsx
from review.workspace import init_isolated_workspace

PROD_CATALOG = ROOT / "site" / "data" / "catalog.json"
ARTIFACTS = ROOT / "testdata" / "round1"


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(cwd, *args):
    result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def new_workspace(tmp, name, store=None, with_remote=True):
    ws = Path(tmp) / name
    remote = Path(tmp) / f"{name}.git" if with_remote else None
    init_isolated_workspace(str(ws), store or seed_store(), branch="review-r1", remote_path=str(remote) if remote else None)
    return ws, remote


def stage(store, scenario, suffix=""):
    if scenario == "unchanged":
        program, offering = proposed_river("unchanged")
        obs = {"observation_id": f"obs-unchanged{suffix}", "program_id": RIVER_PID, "offering_id": RIVER_OID,
               "source_id": "river-s1", "extracted_text": river_source_text("unchanged"),
               "official_links": [program["program_url"]], "excerpts": [river_source_text("unchanged")]}
        return stage_observation(store, obs, program, offering)
    if scenario == "formatting":
        program, offering = proposed_river("formatting")
        obs = {"observation_id": f"obs-formatting{suffix}", "program_id": RIVER_PID, "offering_id": RIVER_OID,
               "source_id": "river-s1", "extracted_text": river_source_text("formatting"),
               "official_links": [program["program_url"]], "excerpts": [river_source_text("formatting")]}
        return stage_observation(store, obs, program, offering)
    if scenario == "material":
        program, offering = proposed_river("material")
        obs = {"observation_id": f"obs-material{suffix}", "program_id": RIVER_PID, "offering_id": RIVER_OID,
               "source_id": "river-s1", "extracted_text": river_source_text("material"),
               "official_links": [program["program_url"]], "excerpts": ["$18/hour"]}
        return stage_observation(store, obs, program, offering)
    if scenario == "next_cycle":
        program, offering = proposed_harbor_next()
        obs = {"observation_id": f"obs-next{suffix}", "program_id": HARBOR_PID, "offering_id": HARBOR_OID_2526,
               "proposed_offering_id": HARBOR_OID_2627, "source_id": "harbor-s1",
               "extracted_text": "Announcing 2026-2027 school year teen docents.",
               "official_links": [program["program_url"]], "excerpts": ["2026-2027 school year"]}
        return stage_observation(store, obs, program, offering)
    if scenario == "fetch_failed":
        return stage_observation(store, {"observation_id": f"obs-fetch{suffix}", "program_id": RIVER_PID,
                                        "offering_id": RIVER_OID, "source_id": "river-s1", "outcome": "fetch_failed"})
    if scenario == "cancellation":
        return stage_observation(store, {"observation_id": f"obs-cancel{suffix}", "program_id": RIVER_PID,
                                        "offering_id": RIVER_OID, "source_id": "river-s1",
                                        "outcome": "cancellation_report", "extracted_text": "reported cancelled"})
    raise ValueError(scenario)


def offering_in_catalog(catalog, oid):
    for prog in catalog["programs"]:
        for off in prog["offerings"]:
            if off["offering_id"] == oid:
                return off
    return None


def pay_min_from_store(store, oid):
    _p, off = approved_facts(store, oid)
    if not off:
        return None
    return ((off.get("comp") or {}).get("items") or [{}])[0].get("min")


class Runner:
    def __init__(self, tmp):
        self.tmp = tmp
        self.results = []
        self.prod_hash = sha256_file(PROD_CATALOG)

    def check(self, sid, title, cond, detail=""):
        self.results.append({"id": sid, "title": title, "ok": bool(cond), "detail": detail if not cond else (detail or "passed")})
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] {sid} {title}" + ("" if cond else f" — {detail}"))

    def run(self):
        self.r1_01_unchanged()
        self.r1_02_formatting()
        self.r1_03_next_cycle()
        self.r1_04_material()
        self.r1_05_download_approve_upload()
        self.r1_06_deadline_end_status()
        self.r1_07_stale_isolation()
        self.r1_08_idempotent()
        self.r1_09_second_checkout()
        self.r1_10_production_untouched()
        self.r1_11_empty_decision()
        self.r1_12_edited_facts_ignored()
        self.r1_13_reject_hold()
        self.r1_14_no_silent_unpublish()
        self.r1_15_invalid_candidate()
        self.r1_16_fatal_build()
        self.r1_17_unknown_dates()
        self.r1_18_closed_completed_remain()
        self.r1_19_competing_and_concurrent()
        self.r1_20_notes_and_publish_distinct()
        return self.results

    def r1_01_unchanged(self):
        store = seed_store()
        first = stage(store, "unchanged")
        second = stage(store, "unchanged", suffix="-2")
        pending = [c for c in store["candidates"].values() if c["status"] in ("pending", "held")]
        self.check("R1-01", "Unchanged source creates no review",
                   first["outcome"] == "unchanged" and not first["queued"] and not pending,
                   f"{first} pending={len(pending)}")

    def r1_02_formatting(self):
        store = seed_store()
        stage(store, "unchanged")
        result = stage(store, "formatting")
        pending = [c for c in store["candidates"].values() if c["status"] in ("pending", "held")]
        self.check("R1-02", "Harmless formatting creates no review",
                   result["outcome"] == "formatting_only" and not result["queued"] and not pending,
                   f"{result} pending={len(pending)}")

    def r1_03_next_cycle(self):
        store = seed_store()
        result = stage(store, "next_cycle")
        old_p, old_o = approved_facts(store, HARBOR_OID_2526)
        self.check("R1-03", "Next-cycle announcement is a separate candidate; old cycle intact",
                   result["queued"] and result["outcome"] == "next_cycle"
                   and old_o["cycle_label"] == "2025-2026 school year"
                   and HARBOR_OID_2526 not in store["memberships"]
                   and PARK_OID not in store["memberships"]
                   and store["candidates"][result["candidate_id"]]["offering_id"] == HARBOR_OID_2627,
                   f"{result} old={old_o['cycle_label'] if old_o else None}")

    def r1_04_material(self):
        store = seed_store()
        before = pay_min_from_store(store, RIVER_OID)
        result = stage(store, "material")
        after = pay_min_from_store(store, RIVER_OID)
        cand = store["candidates"][result["candidate_id"]]
        self.check("R1-04", "Material change creates a separate candidate; approved facts intact",
                   result["queued"] and before == 15.0 and after == 15.0
                   and cand["material_facts_fingerprint"] != store["approved"][RIVER_OID]["facts_fingerprint"],
                   f"before={before} after={after} queued={result['queued']}")

    def r1_05_download_approve_upload(self):
        ws, _ = new_workspace(self.tmp, "r105")
        store = load_store(str(ws))
        staged = stage(store, "material")
        save_store_transaction(str(ws), store, "stage material")
        xlsx_path = Path(self.tmp) / "r105.xlsx"
        data, n = export_workbook(store, path=str(xlsx_path))
        approved_book = set_decisions(data, {staged["candidate_id"]: {"Decision": "Approve", "Review notes": "ok to publish $18"}})
        Path(self.tmp, "r105-approved.xlsx").write_bytes(approved_book)
        store = load_store(str(ws))
        notes = load_notes(str(ws))
        store, notes, results = import_workbook(store, approved_book, notes=notes)
        save_notes(str(ws), notes)
        save_store_transaction(str(ws), store, "review: apply workbook decisions (decision-saved, not site-published)")
        pub = publish_test_catalog(str(ws), today="2026-02-01")
        catalog = json.loads(Path(pub["output"]).read_text(encoding="utf-8"))
        off = offering_in_catalog(catalog, RIVER_OID)
        self.check("R1-05", "Download → approve → upload yields exact approved version in the test catalog",
                   pub.get("ok") and off and "$18" in (off.get("pay") or {}).get("label", "")
                   and pay_min_from_store(store, RIVER_OID) == 18.0
                   and results[0]["status"] == "accepted"
                   and n == 1,
                   f"pub={pub.get('reason')} pay={off.get('pay') if off else None} results={results}")
        # artifacts
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(xlsx_path, ARTIFACTS / "fixture_review.xlsx")
        (ARTIFACTS / "import_result.json").write_text(json.dumps({"results": results, "counts": {r["status"]: 1 for r in results}}, indent=2) + "\n", encoding="utf-8")

    def r1_06_deadline_end_status(self):
        store = seed_store()
        approval = deepcopy(store["approved"][RIVER_OID])
        membership = deepcopy(store["memberships"][RIVER_OID])
        _p, off = approved_facts(store, RIVER_OID)
        s_open = application_status(off, date(2026, 2, 1))
        s_closed = application_status(off, date(2026, 4, 1))
        life_sched = lifecycle_status(off, date(2026, 2, 1))
        life_prog = lifecycle_status(off, date(2026, 7, 1))
        life_done = lifecycle_status(off, date(2026, 9, 1))
        cat, _ = build_catalog_document(store, date(2026, 9, 1), "2026-09-01T00:00:00Z")
        still = offering_in_catalog(cat, RIVER_OID)
        self.check("R1-06", "Deadline/end-date change status without membership or approval loss",
                   s_open == "open" and s_closed == "closed"
                   and life_sched == "scheduled" and life_prog == "in_progress" and life_done == "completed"
                   and store["approved"][RIVER_OID] == approval
                   and store["memberships"][RIVER_OID]["school_year"] == membership["school_year"]
                   and still is not None,
                   f"app={s_open}/{s_closed} life={life_sched}/{life_prog}/{life_done}")

    def r1_07_stale_isolation(self):
        store = seed_store()
        material = stage(store, "material")
        nxt = stage(store, "next_cycle")
        data, _ = export_workbook(store)
        sheets = read_xlsx(data)
        for rec in sheets["Review"]:
            if rec["candidate_id"] == material["candidate_id"]:
                rec["candidate_fingerprint"] = "deadbeef" * 8
                rec["Decision"] = "Approve"
            if rec["candidate_id"] == nxt["candidate_id"]:
                rec["Decision"] = "Approve"
        tampered = rewrite_review_rows(sheets["Review"])
        store2, _, results = import_workbook(deepcopy(store), tampered)
        by = {r["candidate_id"]: r for r in results}
        self.check("R1-07", "Stale-row isolation: stale rejected, independent valid row applied",
                   by[material["candidate_id"]]["status"] == "stale"
                   and by[nxt["candidate_id"]]["status"] == "accepted"
                   and pay_min_from_store(store2, RIVER_OID) == 15.0
                   and HARBOR_OID_2627 in store2["approved"],
                   results)

    def r1_08_idempotent(self):
        store = seed_store()
        staged = stage(store, "material")
        data, _ = export_workbook(store)
        book = set_decisions(data, {staged["candidate_id"]: {"Decision": "Approve"}})
        store, _, first = import_workbook(store, book)
        store, _, second = import_workbook(store, book)
        self.check("R1-08", "Idempotent re-upload of the same accepted decision",
                   first[0]["status"] == "accepted" and second[0]["status"] == "already_applied"
                   and pay_min_from_store(store, RIVER_OID) == 18.0,
                   f"{first[0]['status']} then {second[0]['status']}")

    def r1_09_second_checkout(self):
        ws, remote = new_workspace(self.tmp, "r109", with_remote=True)
        store = load_store(str(ws))
        staged = stage(store, "material")
        save_store_transaction(str(ws), store, "stage material")
        data, _ = export_workbook(store)
        book = set_decisions(data, {staged["candidate_id"]: {"Decision": "Approve"}})
        store = load_store(str(ws))
        store, notes, _ = import_workbook(store, book, notes=load_notes(str(ws)))
        save_notes(str(ws), notes)
        save_store_transaction(str(ws), store, "review: apply workbook decisions (decision-saved, not site-published)")
        git(ws, "push", "origin", "review-r1")
        second = Path(self.tmp) / "r109-second"
        subprocess.run(["git", "clone", "-b", "review-r1", str(remote), str(second)], check=True, capture_output=True, text=True)
        other = load_store(str(second))
        self.check("R1-09", "Second independent checkout reads accepted decisions",
                   pay_min_from_store(other, RIVER_OID) == 18.0
                   and other["approved"][RIVER_OID]["review_status"] == "passed"
                   and head_sha(str(second)) == head_sha(str(ws)),
                   f"second_pay={pay_min_from_store(other, RIVER_OID)}")

    def r1_10_production_untouched(self):
        now = sha256_file(PROD_CATALOG)
        refused = write_catalog_atomic(str(PROD_CATALOG), {"programs": []}, repo_root=str(ROOT), allow_production=False)
        self.check("R1-10", "Production catalog untouched",
                   now == self.prod_hash and not refused.get("wrote") and PROD_CATALOG.exists(),
                   f"hash {now} refused={refused}")

    def r1_11_empty_decision(self):
        store = seed_store()
        staged = stage(store, "material")
        data, _ = export_workbook(store)
        store2, _, results = import_workbook(store, data)
        self.check("R1-11", "Empty Decision is not approval",
                   results[0]["status"] == "no_decision"
                   and store2["candidates"][staged["candidate_id"]]["status"] == "pending"
                   and pay_min_from_store(store2, RIVER_OID) == 15.0,
                   results)

    def r1_12_edited_facts_ignored(self):
        store = seed_store()
        staged = stage(store, "material")
        data, _ = export_workbook(store)
        sheets = read_xlsx(data)
        for rec in sheets["Review"]:
            rec["Decision"] = "Approve"
            rec["proposed_material_facts"] = "pay: $99/hour (tampered)"
        book = rewrite_review_rows(sheets["Review"])
        store2, _, results = import_workbook(store, book)
        self.check("R1-12", "Edited fact cells are not silent corrections",
                   results[0]["status"] == "accepted"
                   and results[0].get("fact_cells_edited_ignored") is True
                   and pay_min_from_store(store2, RIVER_OID) == 18.0
                   and "$99" not in json.dumps(approved_facts(store2, RIVER_OID)[1].get("comp")),
                   results)

    def r1_13_reject_hold(self):
        store = seed_store()
        staged = stage(store, "material")
        data, _ = export_workbook(store)
        book = set_decisions(data, {staged["candidate_id"]: {"Decision": "Reject", "Review notes": "keep $15"}})
        store, _, rejected = import_workbook(store, book)
        hold_stage = stage(store, "material", suffix="-hold")
        data2, _ = export_workbook(store)
        book2 = set_decisions(data2, {hold_stage["candidate_id"]: {"Decision": "Hold"}})
        store, _, held = import_workbook(store, book2)
        self.check("R1-13", "Reject and Hold leave the existing approved version intact",
                   rejected[0]["status"] == "rejected" and held[0]["status"] == "held"
                   and pay_min_from_store(store, RIVER_OID) == 15.0
                   and store["memberships"][RIVER_OID]["school_year"] == "2026-2027",
                   f"{rejected[0]} {held[0]}")

    def r1_14_no_silent_unpublish(self):
        store = seed_store()
        a = stage(store, "fetch_failed")
        b = stage(store, "cancellation")
        cat, _ = build_catalog_document(store, date(2026, 2, 1), "2026-02-01T00:00:00Z")
        self.check("R1-14", "Failed fetch / cancellation report do not unpublish",
                   not a["unpublished"] and not b["unpublished"]
                   and not a["queued"] and not b["queued"]
                   and offering_in_catalog(cat, RIVER_OID) is not None
                   and store["approved"][RIVER_OID]["review_status"] == "passed",
                   f"{a} {b}")

    def r1_15_invalid_candidate(self):
        store = seed_store()
        store["candidates"]["cand-broken"] = {
            "candidate_id": "cand-broken",
            "program_id": "missing-program",
            "offering_id": "missing-offering",
            "proposed_record_version": 99,
            "proposed_revision_id": "no-such-rev",
            "material_facts_fingerprint": "0" * 64,
            "review_reason": "material_change",
            "status": "pending",
            "official_links": [],
            "excerpts": [],
        }
        cat, skipped = build_catalog_document(store, date(2026, 2, 1), "2026-02-01T00:00:00Z")
        self.check("R1-15", "Invalid new candidates do not block a valid catalog",
                   offering_in_catalog(cat, RIVER_OID) is not None and cat["offering_count"] >= 1,
                   f"count={cat['offering_count']} skipped={skipped}")

    def r1_16_fatal_build(self):
        ws, _ = new_workspace(self.tmp, "r116", with_remote=False)
        pub = publish_test_catalog(str(ws), today="2026-02-01")
        path = Path(pub["output"])
        before = path.read_text(encoding="utf-8")
        empty = {"schema_version": "2.3.0", "programs": [], "offering_count": 0, "program_count": 0}
        refused = write_catalog_atomic(str(path), empty, previous_path=str(path), repo_root=str(ROOT))
        after = path.read_text(encoding="utf-8")
        self.check("R1-16", "Fatal build does not replace a good release with empty output",
                   pub.get("ok") and refused.get("fatal") and not refused.get("wrote") and before == after,
                   refused)

    def r1_17_unknown_dates(self):
        store = seed_store()
        assign_membership(store, PARK_OID, "2026-2027", when="2026-01-15T12:00:00Z")
        _p, park = approved_facts(store, PARK_OID)
        cat, _ = build_catalog_document(store, date(2026, 9, 1), "2026-09-01T00:00:00Z")
        off = offering_in_catalog(cat, PARK_OID)
        seed = seed_store()
        self.check("R1-17", "Unknown dates stay unknown; continuous items get no invented membership",
                   lifecycle_status(park, date(2026, 9, 1)) == "unknown"
                   and application_status(park, date(2026, 9, 1)) == "unknown"
                   and off and off["lifecycle_status"] == "unknown"
                   and off["schedule"]["end"] in (None, "")
                   and PARK_OID not in seed["memberships"],
                   f"life={off.get('lifecycle_status') if off else None} invented_membership={PARK_OID in seed['memberships']}")

    def r1_18_closed_completed_remain(self):
        store = seed_store()
        cat, _ = build_catalog_document(store, date(2026, 9, 1), "2026-09-01T00:00:00Z")
        off = offering_in_catalog(cat, RIVER_OID)
        self.check("R1-18", "Closed/completed approved offerings remain; application ≠ activity status",
                   off is not None
                   and off["application_status"] == "closed"
                   and off["lifecycle_status"] == "completed"
                   and off["application_status"] != off["lifecycle_status"],
                   off)

    def r1_19_competing_and_concurrent(self):
        store = seed_store()
        staged = stage(store, "material")
        data, _ = export_workbook(store)
        book = set_decisions(data, {staged["candidate_id"]: {"Decision": "Approve"}})
        # Simulate a competing baseline: another human already approved a different revision.
        other_p, other_o = proposed_river("unchanged")
        other_o["summary"] = "Completely different approved summary"
        from review.store import add_revision, set_approved
        rev = add_revision(store, entity_id=RIVER_OID, record_version=9, actor_kind="human",
                           change_reason="other reviewer", program=other_p, offering=other_o,
                           role="approved")
        set_approved(store, RIVER_OID, rev)
        store2, _, results = import_workbook(deepcopy(store), book)
        competing = results[0]["status"] == "error" and "competing baseline" in results[0]["reason"]
        # Concurrent store_seq without fingerprint change
        store3 = seed_store()
        staged3 = stage(store3, "material")
        data3, _ = export_workbook(store3)
        book3 = set_decisions(data3, {staged3["candidate_id"]: {"Decision": "Approve"}})
        store3["locks"][RIVER_OID]["store_seq"] = 99
        store4, _, results3 = import_workbook(store3, book3)
        concurrent = results3[0]["status"] == "error" and "concurrent" in results3[0]["reason"]
        self.check("R1-19", "Competing baseline and concurrent same-record changes are detected",
                   competing and concurrent,
                   f"{results[0]} / {results3[0]}")

    def r1_20_notes_and_publish_distinct(self):
        ws, _ = new_workspace(self.tmp, "r120", with_remote=True)
        store = load_store(str(ws))
        staged = stage(store, "material")
        save_store_transaction(str(ws), store, "stage material")
        secret = "PRIVATE-NOTE-DO-NOT-COMMIT-xyzzy"
        data, _ = export_workbook(store)
        book = set_decisions(data, {staged["candidate_id"]: {"Decision": "Approve", "Review notes": secret}})
        store = load_store(str(ws))
        store, notes, _ = import_workbook(store, book, notes=load_notes(str(ws)))
        save_notes(str(ws), notes)
        save_store_transaction(str(ws), store, "review: apply workbook decisions (decision-saved, not site-published)")
        log = git(ws, "log", "-p", "--all")
        stored = Path(store_path(str(ws))).read_text(encoding="utf-8")
        notes_on_disk = secret in json.dumps(load_notes(str(ws)))
        distinct_before_publish = bool(store["publication"]["decision_saved_at"]) and not store["publication"]["last_published_release_id"]
        pub = publish_test_catalog(str(ws), today="2026-02-01")
        after = load_store(str(ws))
        self.check("R1-20", "Review notes stay out of git; decision-saved ≠ site-published",
                   secret not in log and secret not in stored and notes_on_disk
                   and distinct_before_publish and pub.get("published")
                   and after["publication"]["last_published_release_id"]
                   and after["publication"]["decision_saved_at"]
                   and after["publication"]["last_published_at"],
                   f"in_git={secret in log} in_store={secret in stored} notes_on_disk={notes_on_disk} distinct={distinct_before_publish} published={pub.get('published')}")


def write_catalog_artifacts():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    store = seed_store()
    before, _ = build_catalog_document(store, date(2026, 2, 1), "2026-02-01T00:00:00Z", release_id="test-before")
    staged = stage(store, "material")
    data, _ = export_workbook(store)
    book = set_decisions(data, {staged["candidate_id"]: {"Decision": "Approve"}})
    store, _, results = import_workbook(store, book)
    after, _ = build_catalog_document(store, date(2026, 2, 1), "2026-02-01T00:00:00Z", release_id="test-after")
    (ARTIFACTS / "catalog_before.json").write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
    (ARTIFACTS / "catalog_after.json").write_text(json.dumps(after, indent=2) + "\n", encoding="utf-8")
    (ARTIFACTS / "import_result.json").write_text(json.dumps({"results": results}, indent=2) + "\n", encoding="utf-8")
    Path(ARTIFACTS / "fixture_review.xlsx").write_bytes(data)
    old = offering_in_catalog(before, RIVER_OID)
    new = offering_in_catalog(after, RIVER_OID)
    diff = [
        "short catalog diff (fixture-river-2026 only)",
        f"- pay.label: {old['pay']['label']}",
        f"+ pay.label: {new['pay']['label']}",
        f"- application_status @ 2026-02-01: {old['application_status']}",
        f"+ application_status @ 2026-02-01: {new['application_status']}",
        f"membership unchanged: 2026-2027",
        f"program_count before/after: {before['program_count']}/{after['program_count']}",
    ]
    later, _ = build_catalog_document(store, date(2026, 9, 1), "2026-09-01T00:00:00Z", release_id="test-after-closed")
    later_off = offering_in_catalog(later, RIVER_OID)
    diff += [
        f"after deadline/end @ 2026-09-01 application_status={later_off['application_status']} lifecycle_status={later_off['lifecycle_status']} still_present=yes",
    ]
    (ARTIFACTS / "catalog_diff.txt").write_text("\n".join(diff) + "\n", encoding="utf-8")
    (ARTIFACTS / "catalog_after_closed.json").write_text(json.dumps(later, indent=2) + "\n", encoding="utf-8")


def main():
    print("Production catalog HEAD hash:", sha256_file(PROD_CATALOG))
    print("Expected main HEAD around 66da90b — current repo files are on the feature branch.\n")
    with tempfile.TemporaryDirectory(prefix="dmv-r1-") as tmp:
        runner = Runner(tmp)
        try:
            results = runner.run()
        except Exception:
            traceback.print_exc()
            results = runner.results
            results.append({"id": "R1-EXC", "title": "uncaught exception", "ok": False, "detail": traceback.format_exc()})
        write_catalog_artifacts()
        report = {
            "passed": sum(1 for r in results if r["ok"]),
            "failed": sum(1 for r in results if not r["ok"]),
            "results": results,
            "production_catalog_sha256": runner.prod_hash,
        }
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        (ARTIFACTS / "acceptance_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"\n{report['passed']} passed / {report['failed']} failed / {len(results)} scenarios")
        print("artifacts:", ARTIFACTS)
        return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
