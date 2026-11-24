"""Known-source inventory.

A source keeps one stable id across checks. This module does not search for
new programs, follow links, or invent URLs.
"""
from __future__ import annotations

import json
from urllib.parse import urlparse


def _host(url):
    return (urlparse(url).hostname or "").lower()


def validate_source(raw):
    if not isinstance(raw, dict):
        raise ValueError("source entry must be an object")
    for key in ("source_id", "program_id", "offering_id", "url"):
        if not str(raw.get(key) or "").strip():
            raise ValueError(f"source is missing {key}")
    source = {
        "source_id": str(raw["source_id"]).strip(),
        "program_id": str(raw["program_id"]).strip(),
        "offering_id": str(raw["offering_id"]).strip(),
        "url": str(raw["url"]).strip(),
        "source_authority": raw.get("source_authority") or "first_party",
        "title": raw.get("title") or "",
        "allowed_hosts": list(raw.get("allowed_hosts") or []),
    }
    host = _host(source["url"])
    if host and host not in {item.lower() for item in source["allowed_hosts"]}:
        source["allowed_hosts"].append(host)
    return source


def load_inventory(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = data.get("sources") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        raise ValueError("inventory has no sources")
    sources = [validate_source(row) for row in rows]
    ids = [item["source_id"] for item in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("inventory has duplicate source ids")
    return sources


def select_sources(sources, only_ids=None, all_listed=False):
    if all_listed and only_ids:
        raise ValueError("pass either --source or --all-listed, not both")
    if all_listed:
        return list(sources)
    wanted = [item.strip() for item in (only_ids or []) if item and item.strip()]
    if not wanted:
        raise ValueError("refusing to run without an explicit source id or --all-listed")
    by_id = {item["source_id"]: item for item in sources}
    missing = [item for item in wanted if item not in by_id]
    if missing:
        raise ValueError("unknown source id: " + ", ".join(missing))
    return [by_id[item] for item in wanted]
