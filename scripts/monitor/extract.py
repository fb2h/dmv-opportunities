"""Conservative reading of reviewable source text.

Only explicit statements become structured facts. A copyright year, an
update timestamp, a URL, or a habit of recurring each year is not a new
cycle. Conflicting statements stay ambiguous instead of picking a winner.
"""
from __future__ import annotations

import re

_DATE = r"([A-Za-z]+\s+\d{1,2},\s*\d{4}|\d{4}-\d{2}-\d{2})"
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_SKIP_LINE = re.compile(
    r"copyright|\u00a9|all rights reserved|last updated|page updated|date modified|founded|established|\bsince\b",
    re.I,
)
_NEGATED = re.compile(r"\b(not yet|no longer|not announced|are not|is not|isn't|aren't|will not be announced)\b", re.I)
_SCHOOL = re.compile(r"\b((?:20\d{2})\s*[-–—]\s*(?:20\d{2}))\s+school year\b", re.I)
_SCHOOL_REV = re.compile(r"\bschool year\s+((?:20\d{2})\s*[-–—]\s*(?:20\d{2}))\b", re.I)
_RANGE = re.compile(r"\b((?:20\d{2})\s*[-–—]\s*(?:20\d{2}))\b", re.I)
_SEASON = re.compile(r"\b(summer|fall|winter|spring)\s+(20\d{2})\b", re.I)
_RANGE_CUE = re.compile(r"\b(school year|academic year|program year|application cycle|cycle|announc\w*|now accepting)\b", re.I)
_DUE = re.compile(r"\b(?:applications?\s+due|application\s+deadline|apply\s+by|deadline)\b\s*[:\-]?\s*" + _DATE, re.I)
_OPENS = re.compile(r"\b(?:applications?\s+open|application\s+opens)\b\s*[:\-]?\s*" + _DATE, re.I)
_PAY = re.compile(r"\$\s*(\d+(?:\.\d+)?)\s*(?:/\s*hour|per\s+hour)\b", re.I)
_UNPAID = re.compile(r"\bunpaid\b", re.I)
_GRADES = re.compile(
    r"\b(?:eligible\s+grades|grades)\s*[:\-]?\s*((?:rising\s+)?grades?\s+\d[\d\s,and\-–—]*)",
    re.I,
)
_FEE = re.compile(r"\bfee\s*[:\-]\s*(no fee|none|free|\$\s*\d+(?:\.\d+)?)", re.I)
_MODE = re.compile(r"\b(?:delivery|mode)\s*[:\-]\s*(in[\s-]?person|virtual|online|hybrid)\b", re.I)
_LOC = re.compile(r"\blocation\s*[:\-]\s*(.+)$", re.I)
_RUN = re.compile(
    r"\b(?:program\s+runs|activity\s+dates?)\b\s*[:\-]?\s*" + _DATE + r"\s+(?:to|through)\s+" + _DATE,
    re.I,
)
_STRICT_CANCEL = re.compile(
    r"\b(?:has been|have been|is|was)\s+(?:officially\s+)?(?:cancelled|canceled)\b|\bwill not be offered\b|\bwill not run\b",
    re.I,
)
_WEAK = re.compile(r"\b(?:might|may|possibly|rumou?red|allegedly|said|claimed|reported)\b", re.I)
_MENTIONS_CANCEL = re.compile(r"\b(?:cancelled|canceled|cancellation)\b", re.I)


class Extraction:
    def __init__(self):
        self.cycle_label = None
        self.cycle_excerpt = None
        self.deadline = None
        self.deadline_raw = None
        self.deadline_excerpt = None
        self.opens = None
        self.opens_raw = None
        self.opens_excerpt = None
        self.pay_min = None
        self.pay_unpaid = False
        self.pay_excerpt = None
        self.grades = None
        self.grades_raw = None
        self.grades_excerpt = None
        self.fee_status = None
        self.fee_raw = None
        self.fee_excerpt = None
        self.mode = None
        self.mode_excerpt = None
        self.location_city = None
        self.location_raw = None
        self.location_excerpt = None
        self.start = None
        self.end = None
        self.dates_raw = None
        self.dates_excerpt = None
        self.cancelled = False
        self.cancellation_excerpt = None
        self.weak_cancellation = False
        self.weak_excerpt = None
        self.ambiguous = False
        self.ambiguity_reasons = []

    @property
    def any_structured(self):
        return any([
            self.cycle_label, self.deadline, self.opens, self.pay_min is not None,
            self.pay_unpaid, self.grades, self.fee_status, self.mode,
            self.location_city, self.start, self.end, self.cancelled, self.weak_cancellation,
        ])


def parse_date(text):
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", text.strip()).strip(" .;")
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", cleaned)
    if iso:
        try:
            year, month, day = int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
            _validate(year, month, day)
            return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            return None
    named = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", cleaned)
    if not named:
        return None
    month = _MONTHS.get(named.group(1).lower())
    if not month:
        return None
    try:
        year, day = int(named.group(3)), int(named.group(2))
        _validate(year, month, day)
        return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return None


def _validate(year, month, day):
    import datetime
    datetime.date(year, month, day)


def _school_label(span):
    years = re.findall(r"20\d{2}", span)
    if len(years) < 2:
        return None
    return f"{years[0]}-{years[1]} school year"


def _season_label(season, year):
    return f"{season.capitalize()} {year}"


def _parse_grades(raw):
    span = re.search(r"(\d{1,2})\s*[-–—]\s*(\d{1,2})", raw or "")
    if span:
        start, end = int(span.group(1)), int(span.group(2))
        if start < 1 or end > 12 or start > end:
            return None
        return [str(n) for n in range(start, end + 1)]
    nums = [int(n) for n in re.findall(r"\d{1,2}", raw or "")]
    nums = [n for n in nums if 1 <= n <= 12]
    if not nums:
        return None
    return [str(n) for n in nums]


def _mode_value(text):
    token = re.sub(r"\s+", " ", text.lower()).replace("-", " ")
    if token == "in person":
        return "in_person"
    if token in ("virtual", "online"):
        return "virtual"
    if token == "hybrid":
        return "hybrid"
    return None


def _city(raw):
    found = re.findall(r",\s*([A-Za-z][A-Za-z .']*?),\s*([A-Z]{2})\b", raw or "")
    if not found:
        return None
    return re.sub(r"\s+", " ", found[-1][0]).strip()


def interpretation_text(reviewable):
    kept = []
    for line in (reviewable or "").splitlines():
        if _SKIP_LINE.search(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def extract(reviewable):
    found = Extraction()
    text = interpretation_text(reviewable)
    lines = text.splitlines()
    _cycles(found, lines)
    _cancellations(found, lines)
    _dates(found, text, lines)
    _pay(found, text, lines)
    _grades(found, text, lines)
    _fee(found, text, lines)
    _delivery(found, text, lines)
    _location(found, lines)
    return found


def _line_for(lines, needle):
    if not needle:
        return None
    for line in lines:
        if needle in line:
            return line.strip()
    return None


def _cycles(found, lines):
    labels = []
    for line in lines:
        if _NEGATED.search(line):
            continue
        for matcher, builder in (
            (_SCHOOL, _school_label),
            (_SCHOOL_REV, _school_label),
        ):
            match = matcher.search(line)
            if match:
                label = builder(match.group(1))
                if label:
                    labels.append((label, line.strip()))
        if _RANGE_CUE.search(line):
            for match in _RANGE.finditer(line):
                label = _school_label(match.group(1))
                if label:
                    labels.append((label, line.strip()))
        for match in _SEASON.finditer(line):
            labels.append((_season_label(match.group(1), match.group(2)), line.strip()))
    unique = []
    seen = set()
    for label, line in labels:
        if label in seen:
            continue
        seen.add(label)
        unique.append((label, line))
    if len(unique) > 1:
        found.ambiguous = True
        found.ambiguity_reasons.append("page states more than one cycle")
        return
    if len(unique) == 1:
        found.cycle_label = unique[0][0]
        found.cycle_excerpt = unique[0][1]


def _cancellations(found, lines):
    strict = []
    weak = []
    for line in lines:
        if not _MENTIONS_CANCEL.search(line) and not _STRICT_CANCEL.search(line):
            continue
        if _STRICT_CANCEL.search(line) and not _WEAK.search(line):
            strict.append(line.strip())
        else:
            weak.append(line.strip())
    if len(strict) > 1 and len(set(strict)) > 1:
        found.ambiguous = True
        found.ambiguity_reasons.append("conflicting cancellation statements")
        return
    if strict:
        found.cancelled = True
        found.cancellation_excerpt = strict[0]
        return
    if weak:
        found.weak_cancellation = True
        found.weak_excerpt = weak[0]


def _mark_ambiguous(found, reason):
    found.ambiguous = True
    found.ambiguity_reasons.append(reason)


def _dates(found, text, lines):
    dues = []
    for match in _DUE.finditer(text):
        iso = parse_date(match.group(1))
        if not iso:
            _mark_ambiguous(found, "application deadline was not a full date")
            continue
        dues.append((iso, match.group(1).strip(), _line_for(lines, match.group(1).strip()) or match.group(0).strip()))
    distinct = {item[0] for item in dues}
    if len(distinct) > 1:
        _mark_ambiguous(found, "page states more than one application deadline")
    elif len(distinct) == 1:
        found.deadline, found.deadline_raw, found.deadline_excerpt = dues[0]
    opens = []
    for match in _OPENS.finditer(text):
        iso = parse_date(match.group(1))
        if iso:
            opens.append((iso, match.group(1).strip(), _line_for(lines, match.group(1).strip()) or match.group(0).strip()))
    if len({item[0] for item in opens}) > 1:
        _mark_ambiguous(found, "page states more than one application opening date")
    elif len(opens) == 1:
        found.opens, found.opens_raw, found.opens_excerpt = opens[0]
    runs = []
    for match in _RUN.finditer(text):
        start = parse_date(match.group(1))
        end = parse_date(match.group(2))
        if start and end:
            runs.append((start, end, match.group(0).strip()))
    if len({(item[0], item[1]) for item in runs}) > 1:
        _mark_ambiguous(found, "page states more than one activity date range")
    elif len(runs) == 1:
        found.start, found.end, found.dates_raw = runs[0][0], runs[0][1], runs[0][2]
        found.dates_excerpt = runs[0][2]


def _pay(found, text, lines):
    amounts = []
    for match in _PAY.finditer(text):
        amounts.append((float(match.group(1)), _line_for(lines, match.group(0)) or match.group(0).strip()))
    unpaid = []
    for line in lines:
        if _UNPAID.search(line):
            unpaid.append(line.strip())
    distinct = {item[0] for item in amounts}
    if len(distinct) > 1 or (distinct and unpaid):
        _mark_ambiguous(found, "pay statements conflict")
        return
    if distinct:
        found.pay_min = amounts[0][0]
        found.pay_excerpt = amounts[0][1]
    elif unpaid:
        found.pay_unpaid = True
        found.pay_excerpt = unpaid[0]


def _grades(found, text, lines):
    parsed = []
    for match in _GRADES.finditer(text):
        raw = re.sub(r"\s+", " ", match.group(1)).strip(" .;")
        values = _parse_grades(raw)
        if not values:
            _mark_ambiguous(found, "grade statement could not be read")
            continue
        excerpt = _line_for(lines, match.group(1).strip()) or match.group(0).strip()
        parsed.append((values, raw, excerpt))
    distinct = {tuple(item[0]) for item in parsed}
    if len(distinct) > 1:
        _mark_ambiguous(found, "page states more than one grade range")
    elif len(distinct) == 1:
        found.grades, found.grades_raw, found.grades_excerpt = parsed[0]


def _fee(found, text, lines):
    hits = []
    for match in _FEE.finditer(text):
        raw = match.group(1).strip()
        status = "none" if raw.lower() in ("no fee", "none", "free") else "provided"
        excerpt = _line_for(lines, match.group(0)) or match.group(0).strip()
        hits.append((status, raw, excerpt))
    if len({item[0] for item in hits}) > 1:
        _mark_ambiguous(found, "fee statements conflict")
    elif hits:
        found.fee_status, found.fee_raw, found.fee_excerpt = hits[0]


def _delivery(found, text, lines):
    hits = []
    for match in _MODE.finditer(text):
        value = _mode_value(match.group(1))
        if not value:
            continue
        excerpt = _line_for(lines, match.group(0)) or match.group(0).strip()
        hits.append((value, excerpt))
    if len({item[0] for item in hits}) > 1:
        _mark_ambiguous(found, "delivery mode statements conflict")
    elif hits:
        found.mode, found.mode_excerpt = hits[0]


def _location(found, lines):
    cities = []
    for line in lines:
        match = _LOC.search(line.strip())
        if not match:
            continue
        raw = match.group(1).strip()
        city = _city(raw)
        if not city:
            continue
        cities.append((city, raw, line.strip()))
    if len({item[0].casefold() for item in cities}) > 1:
        _mark_ambiguous(found, "page states more than one location")
    elif cities:
        found.location_city, found.location_raw, found.location_excerpt = cities[0]
