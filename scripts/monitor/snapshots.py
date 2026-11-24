"""Snapshot storage rooted at a caller-chosen directory.

The repository is not a snapshot root. Tests pass a temporary directory.
A future production monitor can pass a different root without changing callers.
"""
from __future__ import annotations

import json
import os
import re

from review.store import atomic_write_json


def snapshot_id_for(source_id, kind, status, raw_sha256):
    safe_source = re.sub(r"[^A-Za-z0-9._-]+", "_", source_id or "source")
    status_part = "none" if status is None else str(status)
    digest = (raw_sha256 or "0")[:12]
    return f"snap-{safe_source}-{kind}-{status_part}-{digest}"


class SnapshotStore:
    def __init__(self, root):
        self.root = os.path.abspath(root) if root else None
        self._index = None
        self._cache = {}

    def _index_path(self):
        return os.path.join(self.root, "index.json")

    def _load_index(self):
        if self._index is not None:
            return
        self._index = {}
        if not self.root:
            return
        path = self._index_path()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self._index = data.get("sources") or {}

    def _write_index(self):
        if not self.root:
            return
        os.makedirs(self.root, exist_ok=True)
        atomic_write_json(self._index_path(), {"sources": self._index})

    def history(self, source_id):
        self._load_index()
        records = []
        for sid in self._index.get(source_id) or []:
            rec = self._load_record(sid)
            if rec:
                records.append(rec)
        return records

    def latest(self, source_id):
        hist = self.history(source_id)
        return hist[-1] if hist else None

    def latest_ok(self, source_id):
        for rec in reversed(self.history(source_id)):
            if rec.get("kind") == "ok":
                return rec
        return None

    def _load_record(self, snapshot_id):
        if snapshot_id in self._cache:
            return self._cache[snapshot_id]
        if not self.root:
            return None
        path = os.path.join(self.root, snapshot_id + ".json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        self._cache[snapshot_id] = rec
        return rec

    def save(self, record):
        self._load_index()
        snapshot_id = record["snapshot_id"]
        source_id = record["source_id"]
        existing = self._load_record(snapshot_id)
        ids = self._index.setdefault(source_id, [])
        if existing and snapshot_id in ids:
            return existing
        if self.root:
            os.makedirs(self.root, exist_ok=True)
            body = record.get("body") or b""
            if isinstance(body, str):
                body = body.encode("utf-8")
            stored = dict(record)
            stored.pop("body", None)
            stored["body_bytes"] = len(body)
            atomic_write_json(os.path.join(self.root, snapshot_id + ".json"), stored)
            if body:
                body_path = os.path.join(self.root, snapshot_id + ".body")
                with open(body_path, "wb") as fh:
                    fh.write(body)
            self._cache[snapshot_id] = stored
            if snapshot_id not in ids:
                ids.append(snapshot_id)
                self._write_index()
            return stored
        self._cache[snapshot_id] = record
        if snapshot_id not in ids:
            ids.append(snapshot_id)
        return record


class EphemeralSnapshots:
    """Read-through wrapper that does not write the inner store. Used for dry runs."""

    def __init__(self, inner):
        self.inner = inner
        self._extra = {}

    def history(self, source_id):
        return list(self.inner.history(source_id)) + list(self._extra.get(source_id) or [])

    def latest(self, source_id):
        hist = self.history(source_id)
        return hist[-1] if hist else None

    def latest_ok(self, source_id):
        for rec in reversed(self.history(source_id)):
            if rec.get("kind") == "ok":
                return rec
        return None

    def save(self, record):
        source_id = record["source_id"]
        snapshot_id = record["snapshot_id"]
        for rec in self.history(source_id):
            if rec.get("snapshot_id") == snapshot_id:
                return rec
        self._extra.setdefault(source_id, []).append(record)
        return record
