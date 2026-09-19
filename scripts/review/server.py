"""Loopback reviewer: stdlib http.server on 127.0.0.1.

Chosen as the lowest-dependency secure local utility: no Flask, no Node,
no public bind. State-changing requests require POST + CSRF. Writes stay
inside the isolated workspace review tree. GitHub tokens are never read
or sent to the browser.
"""
from __future__ import annotations

import json
import os
import secrets
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .persist import PersistError, head_sha, save_store_transaction, sync_from_authoritative
from .publish import publish_test_catalog
from .store import load_notes, load_store, save_notes
from .workbook import export_workbook, import_workbook, summarize_results

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
FORBIDDEN_ENV = ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT", "CURSOR_API_KEY")


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = "DMVReview/1.0"

    def log_message(self, fmt, *args):
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("[review-loopback] " + (fmt % args) + "\n")

    def _workspace(self):
        return self.server.workspace

    def _csrf_ok(self):
        token = self.headers.get("X-CSRF-Token") or ""
        if not token:
            length = int(self.headers.get("Content-Length") or 0)
            # token may be in multipart; checked later
            return None
        return secrets.compare_digest(token, self.server.csrf)

    def _send(self, code, body, content_type="text/html; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'")
        self.send_header("X-Frame-Options", "DENY")
        for key in FORBIDDEN_ENV:
            if key in os.environ:
                # never copy secrets into headers or body
                pass
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, payload):
        # Strip any accidental secret-looking keys.
        text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        for key in FORBIDDEN_ENV:
            text = text.replace(os.environ.get(key, "___never___"), "[redacted]")
        self._send(code, text, "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            page = open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8").read()
            page = page.replace("{{CSRF}}", self.server.csrf)
            page = page.replace("{{WORKSPACE}}", os.path.abspath(self._workspace()))
            self._send(200, page)
            return
        if self.path == "/status":
            store = load_store(self._workspace())
            outstanding = [c for c in store.get("candidates", {}).values() if c.get("status") in ("pending", "held")]
            pub = store.get("publication") or {}
            self._json(200, {
                "workspace": os.path.abspath(self._workspace()),
                "head": head_sha(self._workspace()),
                "outstanding": len(outstanding),
                "approved_offerings": list(store.get("approved", {})),
                "memberships": list(store.get("memberships", {})),
                "decision_saved_at": pub.get("decision_saved_at"),
                "last_published_release_id": pub.get("last_published_release_id"),
                "decision_saved_is_not_published": pub.get("decision_saved_at") and pub.get("last_published_at") != pub.get("decision_saved_at"),
            })
            return
        if self.path == "/download":
            store = load_store(self._workspace())
            data, n = export_workbook(store)
            extra = {"Content-Disposition": 'attachment; filename="dmv-review.xlsx"'}
            self._send(200, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", extra)
            return
        if self.path == "/app.js":
            self._send(200, open(os.path.join(STATIC_DIR, "app.js"), encoding="utf-8").read(), "text/javascript; charset=utf-8")
            return
        self._send(404, "not found")

    def do_POST(self):
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self._json(403, {"ok": False, "reason": "loopback only"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > 8_000_000:
            self._json(413, {"ok": False, "reason": "upload too large"})
            return
        raw = self.rfile.read(length) if length else b""
        ctype = self.headers.get("Content-Type") or ""
        token = self.headers.get("X-CSRF-Token") or ""
        fields, files = {}, {}
        if ctype.startswith("multipart/form-data"):
            fields, files = _parse_multipart(ctype, raw)
            token = token or fields.get("csrf", "")
        elif ctype.startswith("application/x-www-form-urlencoded"):
            fields = {k: v[0] for k, v in parse_qs(raw.decode("utf-8")).items()}
            token = token or fields.get("csrf", "")
        if not token or not secrets.compare_digest(token, self.server.csrf):
            self._json(403, {"ok": False, "reason": "CSRF token missing or invalid"})
            return

        if self.path == "/upload":
            data = files.get("workbook")
            if not data:
                self._json(400, {"ok": False, "reason": "missing workbook file"})
                return
            try:
                payload = self._import_bytes(data)
                self._json(200, payload)
            except PersistError as exc:
                self._json(409 if exc.concurrent else 400, {"ok": False, "reason": str(exc), "concurrent": exc.concurrent})
            except Exception as exc:
                self._json(400, {"ok": False, "reason": str(exc)})
            return
        if self.path == "/publish":
            today = fields.get("today") or None
            try:
                result = publish_test_catalog(self._workspace(), today=today, repo_root=self.server.repo_root)
                self._json(200 if result.get("ok") else 400, result)
            except PersistError as exc:
                self._json(409 if exc.concurrent else 400, {"ok": False, "reason": str(exc)})
            return
        self._json(404, {"ok": False, "reason": "unknown action"})

    def _import_bytes(self, data):
        sync = sync_from_authoritative(self._workspace())
        if not sync.get("ok"):
            return {"ok": False, "step": "sync", **sync}
        store = load_store(self._workspace())
        notes = load_notes(self._workspace())
        expected = head_sha(self._workspace())
        store, notes, results = import_workbook(store, data, notes=notes)
        save_notes(self._workspace(), notes)
        commit = save_store_transaction(
            self._workspace(), store,
            "review: apply workbook decisions (decision-saved, not site-published)",
            expected_head=expected,
        )
        return {
            "ok": True,
            "sync": sync,
            "commit": commit,
            "counts": summarize_results(results),
            "results": results,
            "decision_saved": True,
            "site_published": False,
            "note": "Accepted decisions are saved in the isolated workspace. Publish is a separate action. Review notes were not committed.",
        }


def _parse_multipart(content_type, raw):
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part.split("=", 1)[1].strip().strip('"')
    fields, files = {}, {}
    if not boundary:
        return fields, files
    marker = b"--" + boundary.encode("utf-8")
    for chunk in raw.split(marker):
        if not chunk or chunk in (b"--\r\n", b"--"):
            continue
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        header_blob, _, body = chunk.partition(b"\r\n\r\n")
        headers = header_blob.decode("utf-8", "replace")
        name = ""
        filename = None
        for line in headers.split("\r\n"):
            if line.lower().startswith("content-disposition:"):
                for item in line.split(";"):
                    item = item.strip()
                    if item.startswith("name="):
                        name = item.split("=", 1)[1].strip().strip('"')
                    if item.startswith("filename="):
                        filename = item.split("=", 1)[1].strip().strip('"')
        if filename:
            files[name] = body
        else:
            fields[name] = body.decode("utf-8", "replace")
    return fields, files


def serve(workspace, host="127.0.0.1", port=8765, repo_root=None):
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("review server binds to loopback only (127.0.0.1)")
    httpd = ThreadingHTTPServer((host, port), ReviewHandler)
    httpd.workspace = os.path.abspath(workspace)
    httpd.repo_root = repo_root
    httpd.csrf = secrets.token_urlsafe(32)
    print(f"Round 1 reviewer on http://{host}:{port}/  workspace={httpd.workspace}")
    print("Loopback only. GitHub tokens are not loaded into this process's responses.")
    httpd.serve_forever()
