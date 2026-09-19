"""Isolated Round 1 fixture programs. Not production records."""
from __future__ import annotations

from copy import deepcopy

from . import DIRECTORY_SCHOOL_YEAR
from .facts import material_fingerprint
from .store import add_revision, assign_membership, empty_store, set_approved

RIVER_PID = "fixture-river-lab-internship"
RIVER_OID = "fixture-river-2026"
HARBOR_PID = "fixture-harbor-museum-docent"
HARBOR_OID_2526 = "fixture-harbor-2025-26"
HARBOR_OID_2627 = "fixture-harbor-2026-27"
PARK_PID = "fixture-green-park-volunteer"
PARK_OID = "fixture-park-continuous"

SEED_AT = "2026-01-15T12:00:00Z"


def _program(pid, name, org, url, **extra):
    rec = {
        "pid": pid,
        "name": name,
        "org": org,
        "org_type": extra.get("org_type", "nonprofit"),
        "host_state": extra.get("host_state", "MD"),
        "program_url": url,
        "status": "active",
        "recurrence": extra.get("recurrence", "annual"),
        "scope": "in_scope",
        "aliases": [],
        "sources": [{
            "sid": f"{pid}-s1",
            "url": url,
            "title": name,
            "publisher": org,
            "auth": "first_party",
            "roles": ["program_detail"],
        }],
        "evidence": extra.get("evidence") or [],
    }
    return rec


def river_offering(*, pay_min=15.0, deadline="2026-03-15", end="2026-08-07"):
    return {
        "oid": RIVER_OID,
        "cycle_kind": "annual",
        "cycle_label": "Summer 2026",
        "ann": "announced",
        "summary": "A paid summer lab internship for high school students along the Anacostia.",
        "types": ["internship", "research"],
        "subjects": ["science_research", "environment_outdoors"],
        "season": "summer",
        "mode": "in_person",
        "housing": "commuter",
        "loc": [{
            "venue": "River Lab",
            "addr": "1000 Water St",
            "city": "Bladensburg",
            "state": "MD",
            "zip": "20710",
            "kind": "activity_site",
            "latitude": 38.939,
            "longitude": -76.934,
        }],
        "grades": {"values": ["10", "11", "12"], "basis": "rising_fall", "raw": "rising grades 10-12"},
        "fee": {"status": "none", "raw": "no fee"},
        "comp": {
            "status": "provided",
            "guaranteed": True,
            "items": [{"kind": "wage", "min": pay_min, "unit": "hour", "raw": f"${pay_min:g}/hour"}],
        },
        "sched": {
            "start": {"date": "2026-06-15", "year": 2026, "month": 6, "day": 15, "precision": "day", "certainty": "confirmed", "raw": "June 15, 2026"},
            "end": {"date": end, "year": int(end[:4]), "month": int(end[5:7]), "day": int(end[8:10]), "precision": "day", "certainty": "confirmed", "raw": "August 7, 2026" if end == "2026-08-07" else end},
        },
        "app": {
            "route": "direct",
            "url": "https://example.test/river-lab/apply",
            "window": "fixed",
            "status": "open",
            "selection": "competitive",
            "deadlines": [{
                "kind": "final",
                "date": deadline,
                "year": int(deadline[:4]),
                "month": int(deadline[5:7]),
                "day": int(deadline[8:10]),
                "precision": "day",
                "certainty": "confirmed",
                "raw": "March 15, 2026",
            }],
        },
    }


def harbor_offering_2025():
    return {
        "oid": HARBOR_OID_2526,
        "cycle_kind": "academic_year",
        "cycle_label": "2025-2026 school year",
        "ann": "announced",
        "summary": "Teen docents at Harbor Museum during the 2025-2026 school year.",
        "types": ["volunteer"],
        "subjects": ["arts_media_humanities"],
        "season": "school_year",
        "mode": "in_person",
        "housing": "commuter",
        "loc": [{"venue": "Harbor Museum", "city": "Baltimore", "state": "MD", "zip": "21202", "kind": "activity_site", "latitude": 39.286, "longitude": -76.609}],
        "grades": {"values": ["9", "10", "11", "12"], "basis": "specified_school_year", "school_year": "2025-2026", "raw": "grades 9-12"},
        "fee": {"status": "none"},
        "comp": {"status": "none", "raw": "unpaid"},
        "sched": {
            "start": {"date": "2025-09-15", "year": 2025, "month": 9, "day": 15, "precision": "day", "certainty": "confirmed", "raw": "September 15, 2025"},
            "end": {"date": "2026-05-30", "year": 2026, "month": 5, "day": 30, "precision": "day", "certainty": "confirmed", "raw": "May 30, 2026"},
        },
        "app": {"route": "direct", "window": "fixed", "status": "closed"},
    }


def harbor_offering_2026():
    off = harbor_offering_2025()
    off["oid"] = HARBOR_OID_2627
    off["cycle_label"] = "2026-2027 school year"
    off["summary"] = "Teen docents at Harbor Museum during the 2026-2027 school year."
    off["grades"] = {"values": ["9", "10", "11", "12"], "basis": "specified_school_year", "school_year": "2026-2027", "raw": "grades 9-12"}
    off["sched"] = {
        "start": {"date": "2026-09-14", "year": 2026, "month": 9, "day": 14, "precision": "day", "certainty": "confirmed", "raw": "September 14, 2026"},
        "end": {"date": "2027-05-28", "year": 2027, "month": 5, "day": 28, "precision": "day", "certainty": "confirmed", "raw": "May 28, 2027"},
    }
    off["app"] = {
        "route": "direct",
        "url": "https://example.test/harbor/apply-2026",
        "window": "fixed",
        "status": "open",
        "deadlines": [{
            "kind": "final", "date": "2026-08-01", "year": 2026, "month": 8, "day": 1,
            "precision": "day", "certainty": "confirmed", "raw": "August 1, 2026",
        }],
    }
    return off


def park_offering():
    return {
        "oid": PARK_OID,
        "cycle_kind": "continuous",
        "cycle_label": "Ongoing volunteer shifts",
        "ann": "announced",
        "summary": "Weekend trail stewardship with Green Park. Dates are not published.",
        "types": ["volunteer"],
        "subjects": ["environment_outdoors", "community_service"],
        "season": "year_round",
        "mode": "in_person",
        "housing": "commuter",
        "loc": [{"venue": "Green Park", "city": "Rockville", "state": "MD", "zip": "20850", "kind": "activity_site", "latitude": 39.084, "longitude": -77.153}],
        "grades": {"values": ["9", "10", "11", "12"], "basis": "unknown", "raw": "high school students"},
        "fee": {"status": "not_mentioned"},
        "comp": {"status": "none", "raw": "unpaid"},
        "sched": {"schedule_raw": "weekends; exact dates not published"},
        "app": {"route": "direct", "window": "rolling", "status": "unknown"},
    }


def seed_store():
    store = empty_store()
    river_p = _program(
        RIVER_PID, "River Lab Summer Internship", "River Lab Alliance",
        "https://example.test/river-lab",
        evidence=[{"sid": f"{RIVER_PID}-s1", "oid": RIVER_OID, "fields": ["/costs/compensation"], "cycle": "Summer 2026", "quote": "$15/hour"}],
    )
    river_o = river_offering()
    harbor_p = _program(
        HARBOR_PID, "Harbor Museum Teen Docents", "Harbor Museum",
        "https://example.test/harbor",
        host_state="MD", org_type="museum",
        evidence=[{"sid": f"{HARBOR_PID}-s1", "oid": HARBOR_OID_2526, "fields": ["/cycle"], "cycle": "2025-2026 school year", "quote": "2025-2026 school year"}],
    )
    harbor_o = harbor_offering_2025()
    park_p = _program(
        PARK_PID, "Green Park Trail Stewards", "Green Park Conservancy",
        "https://example.test/green-park",
        recurrence="continuous",
        evidence=[{"sid": f"{PARK_PID}-s1", "oid": PARK_OID, "fields": ["/cycle"], "cycle": "Ongoing volunteer shifts", "quote": "weekends; exact dates not published"}],
    )
    park_o = park_offering()

    for program, offering, approve, member in (
        (river_p, river_o, True, True),
        (harbor_p, harbor_o, True, False),
        (park_p, park_o, True, False),
    ):
        store["programs"][program["pid"]] = deepcopy(program)
        store["offerings"][offering["oid"]] = {**deepcopy(offering), "program_id": program["pid"]}
        rev = add_revision(
            store, entity_id=offering["oid"], record_version=1, actor_kind="human",
            change_reason="fixture seed", program=program, offering=offering,
            role="approved", when=SEED_AT,
        )
        if approve:
            set_approved(store, offering["oid"], rev, when=SEED_AT)
        if member:
            assign_membership(store, offering["oid"], DIRECTORY_SCHOOL_YEAR, when=SEED_AT)

    store["locks"][RIVER_OID]["store_seq"] = 1
    return store


def river_source_text(variant="unchanged"):
    base = "River Lab Summer Internship. $15/hour. Applications due March 15, 2026. Program runs June 15, 2026 to August 7, 2026."
    if variant == "unchanged":
        return base
    if variant == "formatting":
        return "River Lab Summer Internship.\n\n  $15/hour.  Applications due March 15, 2026.  Program runs June 15, 2026 to August 7, 2026.\n"
    if variant == "material":
        return "River Lab Summer Internship. $18/hour. Applications due March 15, 2026. Program runs June 15, 2026 to August 7, 2026."
    raise ValueError(variant)


def proposed_river(variant="unchanged"):
    program = _program(RIVER_PID, "River Lab Summer Internship", "River Lab Alliance", "https://example.test/river-lab")
    if variant == "unchanged":
        return program, river_offering()
    if variant == "formatting":
        off = river_offering()
        off["summary"] = "A  paid summer lab internship for high school students along the Anacostia."
        return program, off
    if variant == "material":
        return program, river_offering(pay_min=18.0)
    raise ValueError(variant)


def proposed_harbor_next():
    program = _program(HARBOR_PID, "Harbor Museum Teen Docents", "Harbor Museum", "https://example.test/harbor", org_type="museum")
    return program, harbor_offering_2026()


def fingerprint_pair(program, offering):
    return material_fingerprint(program, offering)
