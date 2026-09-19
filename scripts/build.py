#!/usr/bin/env python3
"""build.py — derive the public catalog from data/programs/*.json.

Implements the Section 7.1 publication gate and the Section 8.1 transformation
mapping of the Data Schema Contract (2.3.0) as a rule engine. The collector's
own `public` flag is advisory only; every decision and its reason is written to
data/meta/gate_report.json so a person can audit it.

Round 1 (contract 2.4.0 / Appendix C) does not activate a new approval path on
this production builder. The isolated approved-membership catalog lives in
scripts/review/catalog.py and writes only to a separate test catalog.
Do not point this script at testdata in a way that overwrites site/data/catalog.json
as part of the unused-approval migration — that needs an explicit owner plan.

Outputs
  site/data/catalog.json   PublicCatalog (what the website reads)
  site/data/zips.json      ZIP -> [lat, lon] for DC, MD, VA, DE, WV (user ZIP lookup)
  data/meta/gate_report.json

Usage: python3 scripts/build.py [--today YYYY-MM-DD]
"""
import json, os, sys, glob, re, datetime, argparse, statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAMS = os.path.join(ROOT, "data", "programs")
SITE_DATA = os.path.join(ROOT, "site", "data")
META = os.path.join(ROOT, "data", "meta")

ap = argparse.ArgumentParser()
ap.add_argument("--today", default=datetime.date.today().isoformat())
args = ap.parse_args()
TODAY = datetime.date.fromisoformat(args.today)
NOW = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

# ----------------------------------------------------------------- ZIP data
try:
    import zipcodes
except ImportError:
    sys.exit("pip install zipcodes  (bundled ZIP centroid data; no network needed at run time)")

STATES = {"DC", "MD", "VA", "DE", "WV"}
ZIPS, CITY_PTS, COUNTY_PTS = {}, {}, {}
for z in zipcodes.list_all():
    if z["state"] not in STATES or not z.get("lat"):
        continue
    pt = (float(z["lat"]), float(z["long"]))
    ZIPS[z["zip_code"]] = pt
    if z["zip_code_type"] == "STANDARD":
        CITY_PTS.setdefault((z["city"].lower(), z["state"]), []).append(pt)
        for alt in z.get("acceptable_cities", []):
            CITY_PTS.setdefault((alt.lower(), z["state"]), []).append(pt)
        if z.get("county"):
            COUNTY_PTS.setdefault((z["county"].lower().replace(" county", ""), z["state"]), []).append(pt)

def centroid(pts):
    return (round(statistics.fmean(p[0] for p in pts), 4), round(statistics.fmean(p[1] for p in pts), 4))

def geocode(loc):
    """ZIP centroid -> city centroid -> county centroid. Precision is honest: none of
    these is a rooftop. Returns (lat, lon, precision, status)."""
    z = (loc.get("zip") or "").strip()[:5]
    if z in ZIPS:
        return (*ZIPS[z], "postal_area", "verified")
    city, st = (loc.get("city") or "").strip().lower(), loc.get("state")
    if city and (city, st) in CITY_PTS:
        return (*centroid(CITY_PTS[(city, st)]), "locality", "verified")
    county = (loc.get("county") or "").strip().lower().replace(" county", "").replace(" city", "")
    if county and (county, st) in COUNTY_PTS:
        return (*centroid(COUNTY_PTS[(county, st)]), "locality", "needs_review")
    return (None, None, "unknown", "failed")

# ----------------------------------------------------------------- dates
SEASON_END = {"summer": (8, 31), "fall": (12, 31), "autumn": (12, 31), "spring": (5, 31), "winter": (2, 28)}

def datefact_to_date(df):
    """A DateFact with day precision and a year becomes a date; anything else is None."""
    if not df or df.get("precision") != "day":
        return None
    if df.get("date"):
        try: return datetime.date.fromisoformat(df["date"][:10])
        except ValueError: return None
    if df.get("year") and df.get("month") and df.get("day"):
        try: return datetime.date(int(df["year"]), int(df["month"]), int(df["day"]))
        except ValueError: return None
    return None

def cycle_end_from_label(label):
    """'Summer 2026' -> 2026-08-31; '2026-27' -> 2027-06-30; 'Fall 2026' -> 2026-12-31.
    A label with no year gives None (continuous cycles are handled separately)."""
    if not label: return None
    # Academic year "2026-27" / "2026–2027" / "2026/27": second part must be the next year.
    m = re.search(r"(20\d\d)\s*[-–/]\s*(20\d\d|\d\d)(?!\d)", label)
    if m:
        y1 = int(m.group(1)); y2 = int(m.group(2)); y2 = y2 if y2 > 100 else 2000 + y2
        if y2 == y1 + 1:
            return datetime.date(y2, 6, 30)
    m = re.search(r"(20\d\d)", label)
    if not m: return None
    y = int(m.group(1))
    for word, (mo, da) in SEASON_END.items():
        if re.search(r"\b" + word + r"\b", label, re.I):
            return datetime.date(y, mo, da)
    return datetime.date(y, 12, 31)

def fmt_datefact(df):
    """Human label that never adds precision the source did not give."""
    if not df: return None
    MON = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    p = df.get("precision")
    y = df.get("year")
    mo = MON[int(df["month"])] if df.get("month") else None
    if df.get("date") and p == "day":
        try:
            dt = datetime.date.fromisoformat(df["date"][:10]); mo, y = MON[dt.month], dt.year; df = {**df, "day": dt.day}
        except ValueError:
            pass
    if p == "day" and mo and df.get("day"):
        s = f"{mo} {int(df['day'])}" + (f", {y}" if y else "")
    elif p == "part_of_month" and mo:
        s = f"{df.get('part', '').capitalize()} {mo}".strip() + (f" {y}" if y else "")
    elif p == "month" and mo:
        s = f"{mo}" + (f" {y}" if y else "")
    else:
        return None  # unknown precision: the raw wording is shown as a timing note, never as a date
    if df.get("time"): s += f", {df['time']}"
    if df.get("certainty") == "tentative": s += " (tentative)"
    return s

# ----------------------------------------------------------------- gate
def gate(prog, off):
    """Return (publish: bool, reasons: list[str]) per Section 7.1, evaluated today."""
    r = []
    if prog.get("scope") != "in_scope": r.append(f"scope={prog.get('scope')}")
    if prog.get("status") not in (None, "active"): r.append(f"program status={prog.get('status')}")
    if off.get("ann") != "announced": r.append(f"announcement_state={off.get('ann')}")
    kinds = {i[1] for i in off.get("issues", []) if isinstance(i, list) and len(i) > 1}
    if "superseded" in kinds: r.append("offering superseded by a system-wide record")
    if "expired" in kinds: r.append("collector marked cycle expired")
    if off.get("hist"): r.append("historical cycle")
    end = None
    sched = off.get("sched") or {}
    if isinstance(sched.get("end"), dict): end = datefact_to_date(sched["end"])
    elif isinstance(sched.get("end"), str):
        try: end = datetime.date.fromisoformat(sched["end"][:10])
        except ValueError: end = None
    if end is None and off.get("cycle_kind") != "continuous":
        end = cycle_end_from_label(off.get("cycle_label"))
    if end and end < TODAY: r.append(f"cycle ended {end.isoformat()}")
    if off.get("cycle_kind") in ("annual", "session", "academic_year") and not re.search(r"20\d\d", off.get("cycle_label") or ""):
        app_ = off.get("app") or {}
        dated = end is not None or any(datefact_to_date(dd) for dd in app_.get("deadlines", []))
        # A standing recurring intake stated on a live page ("applications open December 1 each year")
        # is publishable as a continuous-style cycle with no invented year (collection guide, rule 2).
        standing = app_.get("window") in ("rolling", "multiple_rounds") and app_.get("status") != "closed"
        if not dated and not standing: r.append("annual cycle without an identifiable year (7.1.2: label must be interpretable)")
    if not off.get("types"): r.append("no opportunity type")
    if not [e for e in prog.get("evidence", []) if e.get("oid") == off["oid"]]: r.append("no evidence for this offering")
    if not any(s.get("auth") == "first_party" for s in prog.get("sources", [])): r.append("no first-party source")
    return (not r), r

# ----------------------------------------------------------------- transforms
def pay_value(comp):
    st = (comp or {}).get("status")
    if st == "none": return "no_pay"
    if st == "provided":
        items = comp.get("items") or []
        if comp.get("guaranteed") or any(i.get("kind") == "wage" for i in items): return "with_pay"
    return "unknown"

def cost_value(fee):
    st = (fee or {}).get("status")
    if st == "none": return "no_program_fee"
    if st == "required" and any(i.get("mandatory", True) for i in (fee.get("items") or [])): return "program_fee"
    return "unknown"

def money_label(block, noun):
    st = (block or {}).get("status")
    if st in (None, "unknown"): return f"{noun}: not stated"
    if st == "not_mentioned": return f"{noun}: not stated"
    if st == "none": return f"No {noun.lower()}"
    items = block.get("items") or []
    raws = [i.get("raw") for i in items if i.get("raw")]
    if raws: return "; ".join(raws[:3])
    if block.get("raw"): return block["raw"]
    return f"{noun}: {st}"

def app_status(off):
    app = off.get("app") or {}
    st = app.get("status") or "unknown"
    opens = datefact_to_date(app.get("opens"))
    dls = [datefact_to_date(d) for d in app.get("deadlines", []) if d.get("kind") in ("final", None)]
    dls = [d for d in dls if d]
    if opens and opens > TODAY: return "not_yet_open"
    if dls and all(d < TODAY for d in dls) and st != "open": return "closed"
    if dls and all(d < TODAY for d in dls) and st == "open" and (app.get("window") == "fixed"): return "closed"
    return st

def primary_deadline(off):
    """Nearest unexpired final deadline first; else the nearest relevant one; label its role."""
    app = off.get("app") or {}
    best = None
    for d in app.get("deadlines", []):
        dt = datefact_to_date(d)
        label = fmt_datefact(d)
        if not label: continue
        cand = {"kind": d.get("kind", "final"), "label": label, "date": dt.isoformat() if dt else None,
                "expired": bool(dt and dt < TODAY), "precision": d.get("precision")}
        if best is None: best = cand; continue
        # prefer unexpired over expired; then earliest
        if best["expired"] and not cand["expired"]: best = cand
        elif best["expired"] == cand["expired"] and cand["date"] and (not best["date"] or cand["date"] < best["date"]): best = cand
    return best

def grade_rule(g):
    if not g or not g.get("values"): return None
    return {"values": g["values"], "basis": g.get("basis") or "unknown", "raw": g.get("raw")}

def public_location(loc):
    lat, lon, prec, status = geocode(loc)
    kind = loc.get("kind") or "not_published"
    eligible = kind in ("activity_site", "confirmed_campus_approximation") and lat is not None
    parts = [loc.get("venue"), loc.get("addr"), ", ".join(x for x in [loc.get("city"), loc.get("state")] if x)]
    label = " · ".join(p for p in parts if p)
    if kind == "to_be_assigned": label = (loc.get("venue") or "Host site") + " — assigned after acceptance"
    if kind == "organization_reference": label = (loc.get("venue") or "") + " (organization address, not necessarily the activity site)"
    return {"venue": loc.get("venue"), "address": loc.get("addr"), "city": loc.get("city"), "county": loc.get("county"),
            "state": loc.get("state"), "zip": loc.get("zip"), "address_kind": kind,
            "latitude": lat, "longitude": lon, "geocode_precision": prec, "distance_eligible": eligible,
            "location_label": label.strip(" ·")}

def uncertainties(off):
    out = []
    for i in off.get("issues", []):
        if not isinstance(i, list) or len(i) < 2: continue
        path, reason = i[0], i[1]
        note = i[2] if len(i) > 2 else ""
        if reason in ("superseded", "needs_review", "expired", "closed"): continue
        label = {"/eligibility/age": "Age requirement not stated on the page",
                 "/eligibility/grades": "Grade eligibility not stated on the page",
                 "/costs/compensation_status": "Pay not stated on the page",
                 "/costs/fee_status": "Fees not stated on the page",
                 "/cycle": "Next cycle not yet announced",
                 "/application/deadlines": "Deadline not published",
                 "/locations": "Exact location not published"}.get(path.split("/0")[0], None)
        if not label and note: label = note[:140]
        if label: out.append({"field_path": path, "reason": reason, "label": label})
    return out[:6]

def public_offering(prog, off):
    app = off.get("app") or {}
    ev = [e for e in prog.get("evidence", []) if e.get("oid") == off["oid"]]
    src_by = {s["sid"]: s for s in prog.get("sources", [])}
    pub_ev = []
    for e in ev:
        s = src_by.get(e.get("sid"))
        if not s or not s.get("url"): continue
        pub_ev.append({"field_paths": e.get("fields", []), "cycle_label": e.get("cycle"), "quote": e.get("quote"), "source_url": s["url"], "locator": None})
    pub_src = [{"url": s["url"], "title": s.get("title"), "publisher": s.get("publisher"),
                "role": (s.get("roles") or ["program_detail"])[0] if (s.get("roles") or ["program_detail"])[0] in ("program_detail", "application", "attachment", "organization") else "program_detail",
                "verified_at": prog["imported_from"]["submitted_at"]} for s in prog.get("sources", []) if s.get("url")]
    locs = [public_location(l) for l in off.get("loc", [])] if off.get("mode") != "virtual" else []
    sched = off.get("sched") or {}
    return {
        "offering_id": off["oid"],
        "cycle": {"kind": off.get("cycle_kind"), "label": off.get("cycle_label")},
        "summary": off.get("summary"),
        "opportunity_types": [t if t != "job_shadowing" else "shadowing" for t in off.get("types", []) if t != "other"],
        "subjects": off.get("subjects", []),
        "season": off.get("season"),
        "delivery_mode": off.get("mode") or "unknown",
        "housing_mode": off.get("housing"),
        "locations": locs,
        "location_relation": off.get("loc_rel") or ("alternatives" if len(locs) > 1 else "single"),
        "eligibility": {
            "grades": grade_rule(off.get("grades")),
            "age": {k: off["age"].get(k) for k in ("min", "max", "basis", "raw")} if off.get("age") else None,
            "residency": off.get("residency"), "school": off.get("school"), "citizenship": off.get("citizenship"),
            "work_authorization": off.get("work_auth"), "gpa": off.get("gpa"), "prerequisites": off.get("prereq"),
            "logic": off.get("logic") or "simple", "other": off.get("other"),
        },
        "requirements": off.get("reqs") or [],
        "schedule": {"start": fmt_datefact(sched.get("start")) if isinstance(sched.get("start"), dict) else sched.get("start"),
                     "end": fmt_datefact(sched.get("end")) if isinstance(sched.get("end"), dict) else sched.get("end"),
                     "duration": sched.get("dur_raw"), "hours_per_week": sched.get("hpw_raw") or sched.get("hours_raw"),
                     "schedule": sched.get("schedule_raw"), "start_raw": sched.get("start_raw"), "end_raw": sched.get("end_raw")},
        "pay": {"filter_value": pay_value(off.get("comp")), "label": money_label(off.get("comp"), "Pay")},
        "cost": {"filter_value": cost_value(off.get("fee")), "label": money_label(off.get("fee"), "Fee")},
        "aid": off.get("aid"),
        "application": {
            "route": app.get("route"), "window": app.get("window"), "selection": app.get("selection"),
            "url": app.get("url"), "instructions": app.get("instructions"),
            "opens": fmt_datefact(app.get("opens")),
            "deadlines": [{"kind": d.get("kind"), "label": fmt_datefact(d), "raw": d.get("raw")} for d in app.get("deadlines", []) if fmt_datefact(d)],
            "timing_notes": [x.get("raw") for x in ([app.get("opens")] if app.get("opens") else []) + app.get("deadlines", []) if x and not fmt_datefact(x) and x.get("raw")],
        },
        "application_status": app_status(off),
        "primary_deadline": primary_deadline(off),
        "capacity": off.get("capacity_raw") or off.get("capacity"),
        "public_sources": pub_src,
        "public_evidence": pub_ev,
        "uncertainties": uncertainties(off),
        "last_verified_at": prog["imported_from"]["submitted_at"],
        "published_at": NOW,
    }

# ----------------------------------------------------------------- main
programs, report = [], []
files = sorted(glob.glob(os.path.join(PROGRAMS, "*.json")))
for fp in files:
    prog = json.load(open(fp, encoding="utf-8"))
    pub_offs = []
    for off in prog.get("offerings", []):
        ok, reasons = gate(prog, off)
        report.append({"pid": prog["pid"], "oid": off["oid"], "publish": ok, "reasons": reasons,
                       "collector_public_flag": bool(off.get("public")), "agrees_with_collector": ok == bool(off.get("public"))})
        if ok: pub_offs.append(public_offering(prog, off))
    if pub_offs:
        programs.append({"program_id": prog["pid"], "name": prog["name"], "aliases": prog.get("aliases", []),
                         "organization": {"name": prog.get("org"), "type": prog.get("org_type"), "host_state": prog.get("host_state")},
                         "program_url": prog.get("program_url"), "recurrence": prog.get("recurrence"), "offerings": pub_offs})

catalog = {"schema_version": "2.3.0", "taxonomy_version": "2.1.0", "publication_policy_version": "2.3.0",
           "release_id": f"release-{TODAY.isoformat()}", "generated_at": NOW, "reference_date": TODAY.isoformat(),
           "program_count": len(programs), "offering_count": sum(len(p["offerings"]) for p in programs), "programs": programs}

os.makedirs(SITE_DATA, exist_ok=True); os.makedirs(META, exist_ok=True)
json.dump(catalog, open(os.path.join(SITE_DATA, "catalog.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
json.dump({z: [round(p[0], 4), round(p[1], 4)] for z, p in ZIPS.items()}, open(os.path.join(SITE_DATA, "zips.json"), "w"), separators=(",", ":"))
json.dump({"generated_at": NOW, "reference_date": TODAY.isoformat(), "published_offerings": sum(1 for r in report if r["publish"]),
           "withheld_offerings": sum(1 for r in report if not r["publish"]),
           "disagreements_with_collector_flag": [r for r in report if not r["agrees_with_collector"]],
           "decisions": report}, open(os.path.join(META, "gate_report.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)

dis = [r for r in report if not r["agrees_with_collector"]]
print(f"programs read: {len(files)}   published: {catalog['program_count']} programs / {catalog['offering_count']} offerings")
print(f"withheld offerings: {sum(1 for r in report if not r['publish'])}   disagreements with collector flag: {len(dis)}")
loc_total = sum(len(o["locations"]) for p in programs for o in p["offerings"])
loc_elig = sum(1 for p in programs for o in p["offerings"] for l in o["locations"] if l["distance_eligible"])
print(f"locations in public data: {loc_total}, distance-eligible (geocoded activity sites): {loc_elig}")
print(f"wrote site/data/catalog.json ({os.path.getsize(os.path.join(SITE_DATA,'catalog.json'))//1024} KB), site/data/zips.json, data/meta/gate_report.json")
