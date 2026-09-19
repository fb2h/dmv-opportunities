"""Build a test catalog from the approved revision + persisted membership.

Never selects the newest unapproved revision. Never invents dates.
Never drops approved closed/completed members. Invalid candidates are
skipped; a fatal build must not replace a good release.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile

from . import DIRECTORY_SCHOOL_YEAR, PUBLICATION_POLICY_VERSION, SCHEMA_VERSION, TAXONOMY_VERSION
from .facts import application_status, fmt_datefact, lifecycle_status, datefact_to_date
from .store import approved_facts, is_removed

PRODUCTION_CATALOG_SUFFIX = os.path.join("site", "data", "catalog.json")


def is_production_catalog_path(path, repo_root=None):
    path = os.path.abspath(path)
    if repo_root:
        prod = os.path.abspath(os.path.join(repo_root, PRODUCTION_CATALOG_SUFFIX))
        if path == prod:
            return True
    return path.endswith(os.path.join("site", "data", "catalog.json")) and "testdata" not in path and "round1" not in path


def pay_value(comp):
    status = (comp or {}).get("status")
    if status == "none":
        return "no_pay"
    if status == "provided":
        items = comp.get("items") or []
        if comp.get("guaranteed") or any(i.get("kind") == "wage" for i in items):
            return "with_pay"
    return "unknown"


def cost_value(fee):
    status = (fee or {}).get("status")
    if status == "none":
        return "no_program_fee"
    if status == "required" and any(i.get("mandatory", True) for i in (fee.get("items") or [])):
        return "program_fee"
    return "unknown"


def money_label(block, noun):
    status = (block or {}).get("status")
    if status in (None, "unknown", "not_mentioned"):
        return f"{noun}: not stated"
    if status == "none":
        return f"No {noun.lower()}"
    items = block.get("items") or []
    raws = [i.get("raw") for i in items if i.get("raw")]
    if raws:
        return "; ".join(raws[:3])
    if block.get("raw"):
        return block["raw"]
    return f"{noun}: {status}"


def primary_deadline(offering, today):
    app = offering.get("app") or {}
    best = None
    for item in app.get("deadlines") or []:
        dt = datefact_to_date(item)
        label = fmt_datefact(item)
        if not label:
            continue
        cand = {
            "kind": item.get("kind", "final"),
            "label": label,
            "date": dt.isoformat() if dt else None,
            "expired": bool(dt and dt < today),
            "precision": item.get("precision"),
        }
        if best is None:
            best = cand
            continue
        if best["expired"] and not cand["expired"]:
            best = cand
        elif best["expired"] == cand["expired"] and cand["date"] and (not best["date"] or cand["date"] < best["date"]):
            best = cand
    return best


def public_location(loc):
    kind = loc.get("kind") or "not_published"
    parts = [loc.get("venue"), loc.get("addr"), ", ".join(x for x in [loc.get("city"), loc.get("state")] if x)]
    label = " · ".join(p for p in parts if p)
    lat = loc.get("latitude")
    lon = loc.get("longitude")
    eligible = kind in ("activity_site", "confirmed_campus_approximation") and lat is not None
    return {
        "venue": loc.get("venue"),
        "address": loc.get("addr"),
        "city": loc.get("city"),
        "county": loc.get("county"),
        "state": loc.get("state"),
        "zip": loc.get("zip"),
        "address_kind": kind,
        "latitude": lat,
        "longitude": lon,
        "geocode_precision": loc.get("geocode_precision") or ("rooftop" if lat is not None else "unknown"),
        "distance_eligible": eligible,
        "location_label": label.strip(" ·"),
    }


def public_offering(program, offering, today, verified_at, published_at):
    app = offering.get("app") or {}
    sched = offering.get("sched") or {}
    locs = [public_location(l) for l in offering.get("loc") or []] if offering.get("mode") != "virtual" else []
    sources = []
    for src in program.get("sources") or []:
        if src.get("url"):
            sources.append({
                "url": src["url"],
                "title": src.get("title"),
                "publisher": src.get("publisher"),
                "role": "program_detail",
                "verified_at": verified_at,
            })
    evidence = []
    for ev in program.get("evidence") or []:
        if ev.get("oid") == offering.get("oid") and ev.get("quote"):
            evidence.append({
                "field_paths": ev.get("fields") or [],
                "cycle_label": ev.get("cycle"),
                "quote": ev["quote"],
                "source_url": next((s.get("url") for s in (program.get("sources") or []) if s.get("sid") == ev.get("sid")), program.get("program_url")),
                "locator": None,
            })
    return {
        "offering_id": offering["oid"],
        "cycle": {"kind": offering.get("cycle_kind"), "label": offering.get("cycle_label")},
        "summary": offering.get("summary"),
        "opportunity_types": [t if t != "job_shadowing" else "shadowing" for t in offering.get("types") or [] if t != "other"],
        "subjects": offering.get("subjects") or [],
        "season": offering.get("season"),
        "delivery_mode": offering.get("mode") or "unknown",
        "housing_mode": offering.get("housing"),
        "locations": locs,
        "location_relation": offering.get("loc_rel") or ("alternatives" if len(locs) > 1 else "single"),
        "eligibility": {
            "grades": {"values": (offering.get("grades") or {}).get("values"), "basis": (offering.get("grades") or {}).get("basis"), "raw": (offering.get("grades") or {}).get("raw")} if offering.get("grades") else None,
            "age": offering.get("age"),
            "residency": offering.get("residency"),
            "school": offering.get("school"),
            "citizenship": offering.get("citizenship"),
            "work_authorization": offering.get("work_auth"),
            "gpa": offering.get("gpa"),
            "prerequisites": offering.get("prereq"),
            "logic": offering.get("logic") or "simple",
            "other": offering.get("other"),
        },
        "requirements": offering.get("reqs") or [],
        "schedule": {
            "start": fmt_datefact(sched.get("start")) if isinstance(sched.get("start"), dict) else sched.get("start"),
            "end": fmt_datefact(sched.get("end")) if isinstance(sched.get("end"), dict) else sched.get("end"),
            "duration": sched.get("dur_raw"),
            "hours_per_week": sched.get("hpw_raw") or sched.get("hours_raw"),
            "schedule": sched.get("schedule_raw"),
            "start_raw": sched.get("start_raw"),
            "end_raw": sched.get("end_raw"),
        },
        "pay": {"filter_value": pay_value(offering.get("comp")), "label": money_label(offering.get("comp"), "Pay")},
        "cost": {"filter_value": cost_value(offering.get("fee")), "label": money_label(offering.get("fee"), "Fee")},
        "aid": offering.get("aid"),
        "application": {
            "route": app.get("route"),
            "window": app.get("window"),
            "selection": app.get("selection"),
            "url": app.get("url"),
            "instructions": app.get("instructions"),
            "opens": fmt_datefact(app.get("opens")),
            "deadlines": [{"kind": d.get("kind"), "label": fmt_datefact(d), "raw": d.get("raw")} for d in app.get("deadlines") or [] if fmt_datefact(d)],
            "timing_notes": [x.get("raw") for x in ([app.get("opens")] if app.get("opens") else []) + (app.get("deadlines") or []) if x and not fmt_datefact(x) and x.get("raw")],
        },
        "application_status": application_status(offering, today),
        "lifecycle_status": lifecycle_status(offering, today),
        "primary_deadline": primary_deadline(offering, today),
        "directory_school_year": DIRECTORY_SCHOOL_YEAR,
        "capacity": offering.get("capacity_raw") or offering.get("capacity"),
        "public_sources": sources,
        "public_evidence": evidence,
        "uncertainties": [],
        "last_verified_at": verified_at,
        "published_at": published_at,
    }


def build_catalog_document(store, today, generated_at, release_id=None):
    skipped = []
    programs = {}
    year = store.get("directory_school_year") or DIRECTORY_SCHOOL_YEAR
    for oid, membership in store.get("memberships", {}).items():
        if membership.get("school_year") != year:
            continue
        if is_removed(store, oid, year):
            skipped.append({"oid": oid, "reason": "explicit_human_removal"})
            continue
        if oid not in store.get("approved", {}):
            skipped.append({"oid": oid, "reason": "membership_without_approval"})
            continue
        program, offering = approved_facts(store, oid)
        if not program or not offering:
            skipped.append({"oid": oid, "reason": "approved_revision_missing"})
            continue
        try:
            verified = (store["approved"][oid].get("reviewed_at") or generated_at)
            pub = public_offering(program, offering, today, verified, generated_at)
            if not pub.get("offering_id"):
                raise ValueError("missing offering_id")
        except Exception as exc:
            skipped.append({"oid": oid, "reason": f"invalid_member_skipped: {exc}"})
            continue
        pid = program["pid"]
        card = programs.setdefault(pid, {
            "program_id": pid,
            "name": program.get("name"),
            "aliases": program.get("aliases") or [],
            "organization": {"name": program.get("org"), "type": program.get("org_type"), "host_state": program.get("host_state")},
            "program_url": program.get("program_url"),
            "recurrence": program.get("recurrence"),
            "offerings": [],
        })
        card["offerings"].append(pub)

    program_list = [programs[k] for k in sorted(programs)]
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "publication_policy_version": PUBLICATION_POLICY_VERSION,
        "release_id": release_id or f"test-release-{today.isoformat()}",
        "generated_at": generated_at,
        "reference_date": today.isoformat(),
        "directory_school_year": year,
        "program_count": len(program_list),
        "offering_count": sum(len(p["offerings"]) for p in program_list),
        "programs": program_list,
    }
    return catalog, skipped


def validate_catalog(catalog):
    errors = []
    if not isinstance(catalog, dict):
        return ["catalog is not an object"]
    if "programs" not in catalog:
        errors.append("missing programs")
    for prog in catalog.get("programs") or []:
        if not prog.get("program_id"):
            errors.append("program missing program_id")
        for off in prog.get("offerings") or []:
            if not off.get("offering_id"):
                errors.append("offering missing offering_id")
            if "application_status" not in off:
                errors.append(f"{off.get('offering_id')} missing application_status")
            if "lifecycle_status" not in off:
                errors.append(f"{off.get('offering_id')} missing lifecycle_status")
    return errors


def catalog_sha256(catalog):
    blob = json.dumps(catalog, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def write_catalog_atomic(path, catalog, previous_path=None, repo_root=None, allow_production=False):
    if is_production_catalog_path(path, repo_root=repo_root) and not allow_production:
        return {
            "ok": False,
            "fatal": True,
            "reason": "refusing to write the production catalog; Round 1 uses a separate test catalog",
            "wrote": False,
        }
    errors = validate_catalog(catalog)
    if errors:
        return {"ok": False, "fatal": True, "reason": "catalog failed validation: " + "; ".join(errors), "wrote": False}

    previous = None
    if previous_path and os.path.exists(previous_path):
        with open(previous_path, encoding="utf-8") as fh:
            previous = json.load(fh)

    # A fatal empty replacement of a good release is refused.
    if previous and previous.get("offering_count", 0) > 0 and catalog.get("offering_count", 0) == 0:
        return {
            "ok": False,
            "fatal": True,
            "reason": "fatal build produced an empty catalog; previous good release retained",
            "wrote": False,
        }

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-catalog-", suffix=".json", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(catalog, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return {"ok": False, "fatal": True, "reason": f"write failed; previous release retained: {exc}", "wrote": False}
    return {"ok": True, "fatal": False, "reason": "catalog written", "wrote": True, "sha256": catalog_sha256(catalog)}
