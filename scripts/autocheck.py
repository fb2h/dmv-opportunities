#!/usr/bin/env python3
"""autocheck.py — invariant checks over data/programs/*.json.

These are the mechanical defences the contract relies on. A rule written in a
document prevents nothing; a check that fails the build does.

Checks (each is a code you can grep for in the report):
  DATE_NOT_IN_SOURCE   a day-precision date whose month and day do not appear in the
                       DateFact's own raw text or in any evidence quote for that offering
  YEAR_FROM_PATTERN    raw wording like "usually", "typically", "generally", "each year"
                       attached to a date that carries a year — a pattern dressed as a fact
  NO_EVIDENCE          an announced offering with no evidence entry
  NO_FIRST_PARTY       a program with no first-party source
  MIN_GT_MAX           age or duration minimum exceeds maximum
  PAID_TYPE_NO_PAY     opportunity type includes paid_job but compensation is not "provided"
  ZIP_UNKNOWN          a location ZIP that is not a DC/MD/VA/DE/WV ZIP
  BAD_ENUM             a value outside the contract vocabulary
  ANNUAL_NO_YEAR       annual/session cycle label without a year and without a dated deadline
  DEAD_LINK            (only with --links) a source URL that does not answer 2xx/3xx

Exit code 1 when any ERROR-level finding exists, so a workflow can fail on it.
Usage: python3 scripts/autocheck.py [--links] [--json data/meta/autocheck_report.json]
"""
import json, os, glob, re, sys, argparse, datetime, concurrent.futures

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAMS = os.path.join(ROOT, "data", "programs")

ap = argparse.ArgumentParser()
ap.add_argument("--links", action="store_true", help="also check that every source URL answers")
ap.add_argument("--json", default=os.path.join(ROOT, "data", "meta", "autocheck_report.json"))
args = ap.parse_args()

SUBJECTS = {"health_medicine", "science_research", "computing_technology", "engineering_trades", "environment_outdoors",
            "business_law_government", "arts_media_humanities", "education_working_with_kids", "community_service"}
TYPES = {"internship", "research", "volunteer", "paid_job", "apprenticeship", "shadowing", "trainee", "job_shadowing", "other"}
SEASONS = {"summer", "school_year", "year_round", "both", None}
MODES = {"in_person", "virtual", "hybrid", "unknown", None}
LOC_KINDS = {"activity_site", "confirmed_campus_approximation", "organization_reference", "to_be_assigned", "not_published"}
PATTERN_WORDS = re.compile(r"\b(usually|typically|generally|normally|each year|every year|annually|historically|in past years|traditionally)\b", re.I)
MON = ["", "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]

try:
    import zipcodes
    ZIPSET = {z["zip_code"] for z in zipcodes.list_all() if z["state"] in {"DC", "MD", "VA", "DE", "WV"}}
except ImportError:
    ZIPSET = None

findings = []
def F(level, code, pid, oid, msg):
    findings.append({"level": level, "code": code, "pid": pid, "oid": oid, "msg": msg})

def month_day_in_text(df, texts):
    """True if the DateFact's month (name or number) and day appear together in any text."""
    mo, da = df.get("month"), df.get("day")
    if df.get("date") and not mo:
        try:
            d = datetime.date.fromisoformat(df["date"][:10]); mo, da = d.month, d.day
        except ValueError:
            return True  # can't parse; not this check's job
    if not mo or not da: return True  # only day-precision dates are checked
    mname = MON[int(mo)][:3]
    for t in texts:
        if not t: continue
        low = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", t.lower())          # "1st" -> "1"
        # "May 1", "Dec. 8-19", "March 16 to 19", "8 May"
        for m in re.finditer(mname + r"\w*\.?\s+(\d{1,2})(?:\s*(?:-|–|to|through|and)\s*(\d{1,2}))?", low):
            days = {int(m.group(1))} | ({int(m.group(2))} if m.group(2) else set())
            if int(da) in days: return True
        if re.search(rf"\b{int(da)}\s+" + mname + r"\w*", low): return True
        if re.search(rf"\b{int(mo)}/{int(da)}\b", low): return True
    return False

files = sorted(glob.glob(os.path.join(PROGRAMS, "*.json")))
urls = set()
for fp in files:
    p = json.load(open(fp, encoding="utf-8"))
    pid = p["pid"]
    srcs = p.get("sources", [])
    if not any(s.get("auth") == "first_party" for s in srcs):
        F("ERROR", "NO_FIRST_PARTY", pid, None, "no first-party source")
    for s in srcs:
        if s.get("url"): urls.add(s["url"])
    if p.get("program_url"): urls.add(p["program_url"])
    ev_by = {}
    for e in p.get("evidence", []):
        ev_by.setdefault(e.get("oid"), []).append(e.get("quote") or "")
    for o in p.get("offerings", []):
        oid = o["oid"]; quotes = ev_by.get(oid, [])
        if o.get("ann") == "announced" and not quotes:
            F("ERROR", "NO_EVIDENCE", pid, oid, "announced offering has no evidence")
        for t in o.get("types", []):
            if t not in TYPES: F("ERROR", "BAD_ENUM", pid, oid, f"type {t!r}")
        for sx in o.get("subjects", []):
            if sx not in SUBJECTS: F("ERROR", "BAD_ENUM", pid, oid, f"subject {sx!r}")
        if o.get("season") not in SEASONS: F("ERROR", "BAD_ENUM", pid, oid, f"season {o.get('season')!r}")
        if o.get("mode") not in MODES: F("ERROR", "BAD_ENUM", pid, oid, f"mode {o.get('mode')!r}")
        if "paid_job" in o.get("types", []) and (o.get("comp") or {}).get("status") != "provided":
            F("WARN", "PAID_TYPE_NO_PAY", pid, oid, f"type paid_job but compensation status is {(o.get('comp') or {}).get('status')!r}")
        age = o.get("age") or {}
        if age.get("min") and age.get("max") and age["min"] > age["max"]:
            F("ERROR", "MIN_GT_MAX", pid, oid, f"age min {age['min']} > max {age['max']}")
        sch = o.get("sched") or {}
        if sch.get("hpw_min") and sch.get("hpw_max") and sch["hpw_min"] > sch["hpw_max"]:
            F("ERROR", "MIN_GT_MAX", pid, oid, "hours per week min > max")
        for l in o.get("loc", []):
            if l.get("kind") not in LOC_KINDS: F("ERROR", "BAD_ENUM", pid, oid, f"location kind {l.get('kind')!r}")
            z = (l.get("zip") or "").strip()
            if z and ZIPSET is not None and z[:5] not in ZIPSET: F("WARN", "ZIP_UNKNOWN", pid, oid, f"ZIP {z} not in DC/MD/VA/DE/WV")
        app = o.get("app") or {}
        dates = [("opens", app.get("opens"))] + [("deadline", d) for d in app.get("deadlines", [])]
        if isinstance(sch.get("start"), dict): dates.append(("start", sch["start"]))
        if isinstance(sch.get("end"), dict): dates.append(("end", sch["end"]))
        for role, df in dates:
            if not df: continue
            raw = df.get("raw") or ""
            if df.get("precision") == "day" and not month_day_in_text(df, [raw] + quotes):
                F("ERROR", "DATE_NOT_IN_SOURCE", pid, oid, f"{role} {df.get('month')}/{df.get('day')} not found in its raw text or any evidence quote")
            if df.get("year") and PATTERN_WORDS.search(raw):
                F("ERROR", "YEAR_FROM_PATTERN", pid, oid, f"{role} carries year {df['year']} but the wording is a pattern: {raw[:90]!r}")
        if o.get("cycle_kind") in ("annual", "session", "academic_year") and o.get("ann") == "announced":
            if not re.search(r"20\d\d", o.get("cycle_label") or "") and not any(d.get("year") or d.get("date") for d in app.get("deadlines", [])) \
               and app.get("window") not in ("rolling", "multiple_rounds"):
                F("WARN", "ANNUAL_NO_YEAR", pid, oid, f"cycle label {o.get('cycle_label')!r} has no year and no dated deadline")

if args.links:
    import urllib.request, urllib.error, ssl
    ctx = ssl.create_default_context()
    def check(u):
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (dmv-opportunities link check)"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                return u, r.status, None
        except urllib.error.HTTPError as e:
            return u, e.code, str(e)
        except Exception as e:
            return u, None, type(e).__name__ + ": " + str(e)[:80]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for u, status, err in ex.map(check, sorted(urls)):
            if status is None or status >= 400:
                F("WARN" if status in (403, 429, 999) else "ERROR", "DEAD_LINK", None, None, f"{u} -> {status or err}")

errors = [f for f in findings if f["level"] == "ERROR"]
os.makedirs(os.path.dirname(args.json), exist_ok=True)
json.dump({"checked_at": datetime.datetime.utcnow().isoformat() + "Z", "programs": len(files), "urls": len(urls),
           "links_checked": args.links, "errors": len(errors), "warnings": len(findings) - len(errors), "findings": findings},
          open(args.json, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
by = {}
for f in findings: by[(f["level"], f["code"])] = by.get((f["level"], f["code"]), 0) + 1
print(f"checked {len(files)} programs, {len(urls)} URLs{' (links checked)' if args.links else ''}")
for (lvl, code), n in sorted(by.items()): print(f"  {lvl:5} {code:20} {n}")
for f in errors[:40]: print(f"  ! {f['code']} {f['pid']} {f['oid'] or ''}: {f['msg']}")
print(f"report: {os.path.relpath(args.json, ROOT)}")
sys.exit(1 if errors else 0)
