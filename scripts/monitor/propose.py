"""Turn explicit extracted statements into a proposed revision, or into no proposal.

Same-cycle updates copy the approved offering and change only the fields the
current source stated differently. A new cycle gets a new offering that
contains only what this source stated. Last year's dates, pay, grades, fees,
and locations are not filled in.
"""
from __future__ import annotations

import re
from copy import deepcopy

from review.facts import datefact_to_date

CYCLE_DEPENDENT_KEYS = (
    "summary", "types", "subjects", "season", "mode", "housing",
    "ann", "loc", "grades", "age", "residency", "school", "citizenship", "work_auth",
    "fee", "comp", "aid", "sched", "app", "reqs", "capacity", "capacity_raw",
)


class Change:
    def __init__(self, field, prior, proposed, excerpt, raw=None):
        self.field = field
        self.prior = prior
        self.proposed = proposed
        self.excerpt = excerpt
        self.raw = raw

    def as_dict(self):
        return {
            "field": self.field,
            "prior_approved_value": self.prior,
            "proposed_value": self.proposed,
            "excerpt": self.excerpt,
        }


def normalize_cycle(label):
    if not label:
        return ""
    text = str(label).lower().replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text).strip()
    years = re.findall(r"20\d{2}", text)
    if "school year" in text and len(years) >= 2:
        return f"{years[0]}-{years[1]} school year"
    season = re.search(r"(summer|fall|winter|spring)\s+(20\d{2})", text)
    if season:
        return f"{season.group(1)} {season.group(2)}"
    if len(years) >= 2:
        return f"{years[0]}-{years[1]}"
    return text


def different_cycle(approved_label, extracted_label):
    proposed = normalize_cycle(extracted_label)
    if not proposed or not re.search(r"20\d{2}", proposed):
        return False
    return proposed != normalize_cycle(approved_label)


def _iso(value):
    parsed = datefact_to_date(value)
    if not parsed:
        return None
    return parsed.isoformat()


def approved_deadline(offering):
    for item in ((offering or {}).get("app") or {}).get("deadlines") or []:
        if item.get("kind") in ("final", None):
            iso = _iso(item)
            if iso:
                return iso
    return None


def approved_opens(offering):
    return _iso(((offering or {}).get("app") or {}).get("opens"))


def approved_pay(offering):
    comp = (offering or {}).get("comp") or {}
    for item in comp.get("items") or []:
        if item.get("min") is not None and item.get("kind") in ("wage", None):
            return float(item["min"]), "provided"
    return None, comp.get("status")


def approved_grades(offering):
    values = ((offering or {}).get("grades") or {}).get("values") or []
    return [str(value) for value in values]


def approved_city(offering):
    locs = (offering or {}).get("loc") or []
    if not locs:
        return None
    city = locs[0].get("city")
    return city.strip() if isinstance(city, str) and city.strip() else None


def _result(classification, *, changes=None, excerpts=None, note=""):
    return {
        "classification": classification,
        "changes": changes or [],
        "excerpts": [item for item in (excerpts or []) if item],
        "note": note,
    }


def assess(offering, extracted, *, raw_changed, normalized_changed, first_run):
    if extracted.ambiguous:
        return _result("pending_update", note="; ".join(extracted.ambiguity_reasons) or "ambiguous source text")
    if offering is None and not extracted.cycle_label:
        return _result("pending_update", note="no approved offering to compare; baseline saved; no invented candidate")
    if extracted.cancelled and extracted.cancellation_excerpt:
        return _result("first_party_cancellation", excerpts=[extracted.cancellation_excerpt])
    if extracted.cancelled:
        return _result("cancellation_report", note="cancellation language had no usable excerpt")
    if extracted.weak_cancellation:
        return _result(
            "cancellation_report",
            excerpts=[extracted.weak_excerpt] if extracted.weak_excerpt else [],
            note="cancellation was not an explicit first-party confirmation",
        )
    if extracted.cycle_label and (offering is None or different_cycle(offering.get("cycle_label"), extracted.cycle_label)):
        excerpts = [extracted.cycle_excerpt]
        if extracted.deadline_excerpt:
            excerpts.append(extracted.deadline_excerpt)
        excerpts = [item for item in excerpts if item]
        if not excerpts:
            return _result("pending_update", note="possible new cycle without a quotable excerpt")
        return _result("next_cycle", excerpts=excerpts, note="explicit new cycle on the known official source")
    changes = diff_material(offering or {}, extracted)
    if changes:
        missing = [item for item in changes if not item.excerpt]
        if missing:
            return _result("pending_update", note="a possible fact change had no supporting excerpt")
        return _result("material_change", changes=changes, excerpts=[item.excerpt for item in changes])
    if first_run and not extracted.any_structured:
        return _result("pending_update", note="baseline saved; structured facts were not extracted; approved revision not changed")
    if raw_changed or normalized_changed:
        return _result("formatting_only", note="source text changed; no structured material fact changed")
    note = "baseline snapshot saved" if first_run else "same meaningful content"
    return _result("unchanged", note=note)


def diff_material(offering, extracted):
    changes = []
    if extracted.deadline and extracted.deadline != approved_deadline(offering):
        changes.append(Change("app.deadlines", approved_deadline(offering), extracted.deadline, extracted.deadline_excerpt, extracted.deadline_raw))
    if extracted.opens and extracted.opens != approved_opens(offering):
        changes.append(Change("app.opens", approved_opens(offering), extracted.opens, extracted.opens_excerpt, extracted.opens_raw))
    pay_min, pay_status = approved_pay(offering)
    if extracted.pay_min is not None and (pay_min is None or abs(pay_min - extracted.pay_min) > 0.001):
        changes.append(Change("comp", pay_min, extracted.pay_min, extracted.pay_excerpt))
    elif extracted.pay_unpaid and pay_status != "none":
        changes.append(Change("comp", pay_status, "none", extracted.pay_excerpt, "unpaid"))
    if extracted.grades is not None and extracted.grades != approved_grades(offering):
        changes.append(Change("grades", approved_grades(offering), extracted.grades, extracted.grades_excerpt, extracted.grades_raw))
    fee_status = ((offering or {}).get("fee") or {}).get("status")
    if extracted.fee_status and extracted.fee_status != fee_status:
        changes.append(Change("fee", fee_status, extracted.fee_status, extracted.fee_excerpt, extracted.fee_raw))
    if extracted.mode and extracted.mode != (offering or {}).get("mode"):
        changes.append(Change("mode", (offering or {}).get("mode"), extracted.mode, extracted.mode_excerpt))
    city = approved_city(offering)
    if extracted.location_city and extracted.location_city.casefold() != (city or "").casefold():
        changes.append(Change("loc", city, extracted.location_city, extracted.location_excerpt, extracted.location_raw))
    sched = (offering or {}).get("sched") or {}
    if extracted.start and extracted.start != _iso(sched.get("start")):
        changes.append(Change("sched.start", _iso(sched.get("start")), extracted.start, extracted.dates_excerpt, extracted.dates_raw))
    if extracted.end and extracted.end != _iso(sched.get("end")):
        changes.append(Change("sched.end", _iso(sched.get("end")), extracted.end, extracted.dates_excerpt, extracted.dates_raw))
    return changes


def datefact(iso, raw, kind=None):
    year, month, day = [int(part) for part in iso.split("-")]
    record = {
        "date": iso,
        "year": year,
        "month": month,
        "day": day,
        "precision": "day",
        "certainty": "confirmed",
        "raw": raw or iso,
    }
    if kind:
        record["kind"] = kind
    return record


def _apply_change(offering, change, extracted):
    if change.field == "app.deadlines":
        app = deepcopy(offering.get("app") or {})
        app["deadlines"] = [datefact(change.proposed, change.raw or change.excerpt, "final")]
        offering["app"] = app
    elif change.field == "app.opens":
        app = deepcopy(offering.get("app") or {})
        app["opens"] = datefact(change.proposed, change.raw or change.excerpt)
        offering["app"] = app
    elif change.field == "comp" and isinstance(change.proposed, float):
        offering["comp"] = {
            "status": "provided",
            "guaranteed": True,
            "items": [{
                "kind": "wage",
                "min": change.proposed,
                "unit": "hour",
                "raw": change.excerpt or f"${change.proposed:g}/hour",
            }],
        }
    elif change.field == "comp":
        offering["comp"] = {"status": "none", "raw": change.raw or "unpaid"}
    elif change.field == "grades":
        raw = change.raw or ""
        basis = "rising_fall" if "rising" in raw.lower() else "unknown"
        offering["grades"] = {"values": list(change.proposed), "basis": basis, "raw": raw}
    elif change.field == "fee":
        offering["fee"] = {"status": change.proposed, "raw": change.raw}
    elif change.field == "mode":
        offering["mode"] = change.proposed
    elif change.field == "loc":
        offering["loc"] = [{
            "city": change.proposed,
            "kind": "activity_site",
            "raw": change.raw or change.excerpt,
        }]
    elif change.field in ("sched.start", "sched.end"):
        sched = deepcopy(offering.get("sched") or {})
        key = "start" if change.field.endswith("start") else "end"
        sched[key] = datefact(change.proposed, change.raw or change.excerpt)
        offering["sched"] = sched
    return offering


def apply_material_changes(program, offering, changes, extracted):
    proposed_program = deepcopy(program)
    proposed_offering = deepcopy(offering)
    for change in changes:
        _apply_change(proposed_offering, change, extracted)
    return proposed_program, proposed_offering


def next_offering_id(source_offering_id, cycle_label):
    label = normalize_cycle(cycle_label)
    years = re.findall(r"20\d{2}", label)
    if len(years) >= 2:
        slug = f"{years[0]}-{years[1]}"
    else:
        season = re.search(r"(summer|fall|winter|spring)\s+(20\d{2})", label)
        slug = f"{season.group(1)}-{season.group(2)}" if season else "next"
    return f"{source_offering_id}--{slug}"


def stable_program(program):
    """Carry identity forward. Drop prior-cycle evidence quotes."""
    kept = deepcopy(program)
    kept.pop("evidence", None)
    return kept


def build_next_offering(extracted, new_oid):
    label = extracted.cycle_label
    offering = {
        "oid": new_oid,
        "offering_id": new_oid,
        "cycle_kind": "academic_year" if "school year" in (label or "").lower() else "annual",
        "cycle_label": label,
        "ann": "announced" if extracted.cycle_excerpt else None,
    }
    if extracted.deadline:
        offering["app"] = {"deadlines": [datefact(extracted.deadline, extracted.deadline_raw or extracted.deadline_excerpt, "final")]}
    if extracted.opens:
        offering.setdefault("app", {})["opens"] = datefact(extracted.opens, extracted.opens_raw or extracted.opens_excerpt)
    if extracted.pay_min is not None:
        offering["comp"] = {
            "status": "provided",
            "guaranteed": True,
            "items": [{"kind": "wage", "min": extracted.pay_min, "unit": "hour", "raw": extracted.pay_excerpt}],
        }
    elif extracted.pay_unpaid:
        offering["comp"] = {"status": "none", "raw": "unpaid"}
    if extracted.grades:
        raw = extracted.grades_raw or ""
        offering["grades"] = {
            "values": list(extracted.grades),
            "basis": "rising_fall" if "rising" in raw.lower() else "unknown",
            "raw": raw,
        }
    if extracted.fee_status:
        offering["fee"] = {"status": extracted.fee_status, "raw": extracted.fee_raw}
    if extracted.mode:
        offering["mode"] = extracted.mode
    if extracted.location_city:
        offering["loc"] = [{"city": extracted.location_city, "kind": "activity_site", "raw": extracted.location_raw}]
    if extracted.start or extracted.end:
        sched = {}
        if extracted.start:
            sched["start"] = datefact(extracted.start, extracted.dates_raw or extracted.start)
        if extracted.end:
            sched["end"] = datefact(extracted.end, extracted.dates_raw or extracted.end)
        offering["sched"] = sched
    return offering


def unstated_cycle_fields(prior_offering, proposed_offering):
    """Fields the new cycle page did not state. They stay off the candidate."""
    rows = []
    for key in CYCLE_DEPENDENT_KEYS:
        if proposed_offering.get(key) not in (None, {}, []):
            continue
        prior = (prior_offering or {}).get(key)
        if prior in (None, {}, [], ""):
            continue
        rows.append({
            "field": key,
            "prior_approved_value": prior,
            "proposed_value": None,
            "note": "not stated on the current source; not copied from the prior cycle",
        })
    return rows
