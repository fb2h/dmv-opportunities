"""Material facts, fingerprints, and deterministic status.

Reuses contract meanings: record_version changes only with factual content;
application_status and lifecycle_status are derived display states and are
not themselves an editorial inclusion decision.
"""
from __future__ import annotations

import datetime
import hashlib
import html
import json
import re
import unicodedata
from copy import deepcopy

MATERIAL_PROGRAM_KEYS = (
    "name", "org", "org_type", "host_state", "program_url",
    "status", "recurrence", "scope",
)
MATERIAL_OFFERING_KEYS = (
    "summary", "types", "subjects", "season", "mode", "housing",
    "cycle_kind", "cycle_label", "ann",
    "loc", "grades", "age", "residency", "school", "citizenship", "work_auth",
    "fee", "comp", "aid", "sched", "app", "reqs", "capacity", "capacity_raw",
)

_CURLY = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u00a0": " ",
})


def normalize_text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    text = html.unescape(unicodedata.normalize("NFC", value)).translate(_CURLY)
    text = re.sub(r"[ \t\r\n]+", " ", text).strip()
    return text


def normalize_value(value):
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        return [normalize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize_value(v) for k, v in sorted(value.items(), key=lambda kv: kv[0])}
    return value


def material_slice(program, offering):
    """Canonical material facts used for fingerprints and workbook display."""
    prog = {k: deepcopy(program.get(k)) for k in MATERIAL_PROGRAM_KEYS}
    off = {k: deepcopy(offering.get(k)) for k in MATERIAL_OFFERING_KEYS}
    return normalize_value({"program": prog, "offering": off})


def material_fingerprint(program, offering):
    canonical = json.dumps(material_slice(program, offering), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def content_sha256(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def format_material_facts(program, offering):
    """Human-readable old-vs-proposed block. Not applied from the workbook."""
    lines = [
        f"name: {program.get('name')}",
        f"org: {program.get('org')}",
        f"cycle: {offering.get('cycle_kind')} / {offering.get('cycle_label')}",
        f"summary: {offering.get('summary')}",
        f"types: {', '.join(offering.get('types') or [])}",
        f"pay: {json.dumps(offering.get('comp'), ensure_ascii=False, sort_keys=True)}",
        f"fee: {json.dumps(offering.get('fee'), ensure_ascii=False, sort_keys=True)}",
        f"schedule: {json.dumps(offering.get('sched'), ensure_ascii=False, sort_keys=True)}",
        f"application: {json.dumps(offering.get('app'), ensure_ascii=False, sort_keys=True)}",
        f"grades: {json.dumps(offering.get('grades'), ensure_ascii=False, sort_keys=True)}",
        f"official_url: {program.get('program_url')}",
    ]
    return "\n".join(lines)


def datefact_to_date(df):
    """Known day-precision dates only. Month-only and labels stay unknown."""
    if not df:
        return None
    if isinstance(df, str):
        try:
            return datetime.date.fromisoformat(df[:10])
        except ValueError:
            return None
    if not isinstance(df, dict):
        return None
    if df.get("precision") and df.get("precision") != "day":
        return None
    if df.get("date"):
        try:
            return datetime.date.fromisoformat(str(df["date"])[:10])
        except ValueError:
            return None
    if df.get("year") and df.get("month") and df.get("day"):
        try:
            return datetime.date(int(df["year"]), int(df["month"]), int(df["day"]))
        except ValueError:
            return None
    return None


def parse_explicit_date(value):
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value[:10])
        except ValueError:
            return None
    if isinstance(value, dict):
        return datefact_to_date(value)
    return None


def application_status(offering, today):
    """Keep official application status distinct from activity lifecycle."""
    app = offering.get("app") or {}
    official = app.get("status") or "unknown"
    opens = datefact_to_date(app.get("opens"))
    finals = []
    for item in app.get("deadlines") or []:
        if item.get("kind") in ("final", None):
            dt = datefact_to_date(item)
            if dt:
                finals.append(dt)
    if opens and opens > today:
        return "not_yet_open"
    if finals and all(d < today for d in finals):
        return "closed"
    return official


def lifecycle_status(offering, today):
    """Activity status from explicit start/end only. Do not invent dates from labels."""
    sched = offering.get("sched") or {}
    start = parse_explicit_date(sched.get("start"))
    end = parse_explicit_date(sched.get("end"))
    if end and end < today:
        return "completed"
    if start and start > today:
        return "scheduled"
    if start and start <= today and (end is None or end >= today):
        return "in_progress"
    if end and start is None and end >= today:
        return "in_progress"
    return "unknown"


def looks_like_next_cycle(approved_offering, proposed_offering):
    """A new announced cycle is a separate offering, never a year rewrite."""
    if proposed_offering.get("offering_id") and approved_offering.get("oid"):
        if proposed_offering.get("offering_id") != approved_offering.get("oid"):
            if (proposed_offering.get("cycle_label") or "") != (approved_offering.get("cycle_label") or ""):
                return True
    a = approved_offering.get("cycle_label") or ""
    b = proposed_offering.get("cycle_label") or ""
    if a != b and re.search(r"20\d\d", a) and re.search(r"20\d\d", b):
        return True
    return False


def classify_observation(approved_program, approved_offering, proposed_program, proposed_offering, raw_changed):
    if approved_program is None or approved_offering is None:
        if looks_like_next_cycle({"oid": None, "cycle_label": ""}, proposed_offering):
            return "next_cycle"
        return "material_change"
    same = material_fingerprint(approved_program, approved_offering) == material_fingerprint(proposed_program, proposed_offering)
    if same:
        return "formatting_only" if raw_changed else "unchanged"
    if looks_like_next_cycle(approved_offering, proposed_offering):
        return "next_cycle"
    return "material_change"


def fmt_datefact(df):
    """Display helper that never adds precision the source did not give."""
    if not df:
        return None
    if isinstance(df, str):
        return df
    months = ["", "January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    precision = df.get("precision")
    year = df.get("year")
    month = months[int(df["month"])] if df.get("month") else None
    if df.get("date") and precision == "day":
        try:
            dt = datetime.date.fromisoformat(str(df["date"])[:10])
            month, year = months[dt.month], dt.year
            df = {**df, "day": dt.day}
        except ValueError:
            pass
    if precision == "day" and month and df.get("day"):
        text = f"{month} {int(df['day'])}" + (f", {year}" if year else "")
    elif precision == "part_of_month" and month:
        text = f"{str(df.get('part') or '').capitalize()} {month}".strip() + (f" {year}" if year else "")
    elif precision == "month" and month:
        text = f"{month}" + (f" {year}" if year else "")
    else:
        return None
    if df.get("time"):
        text += f", {df['time']}"
    if df.get("certainty") == "tentative":
        text += " (tentative)"
    return text
