"""Source retrieval.

Fixture fetches never open a socket. The live fetcher exists for an explicit
manual allowlist run and is not used by acceptance tests, schedules, or the
default CLI. A blocked, timed-out, or TLS-failed response is a fetch failure,
not evidence that an opportunity disappeared.
"""
from __future__ import annotations

import socket
import ssl
from urllib.parse import urlparse, urljoin

USER_AGENT = "DMVOpportunitiesMonitor/2 (+known-source; not a crawler; no discovery)"
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 5
DEFAULT_TIMEOUT = 20
MAX_RETRIES = 2


def retryable(status, error):
    """Retry only transient transport failures. Never retry a block, a missing page, or a 4xx."""
    if error in ("timeout", "connection_error", "tls_error"):
        return True
    if status in (500, 502, 503, 504):
        return True
    return False


def robots_disallows(robots_txt, path, user_agent):
    """Minimal robots.txt check: longest matching Disallow for * or our agent.

    This is not a crawler policy. It only refuses a known URL that the site
    already disallows. An unreadable robots.txt does not invent a disallow.
    """
    if not robots_txt:
        return False
    groups = []
    current = None
    for raw in robots_txt.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            current = None
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if current is None or current.get("rules"):
                current = {"agents": [], "rules": []}
                groups.append(current)
            current["agents"].append(value.lower())
        elif key == "disallow" and current is not None:
            current["rules"].append(value)
    agent = (user_agent or "").split("/", 1)[0].lower()
    chosen = None
    for group in groups:
        agents = group["agents"]
        if agent and any(a == agent or a == user_agent.lower() for a in agents):
            chosen = group
            break
    if chosen is None:
        for group in groups:
            if "*" in group["agents"]:
                chosen = group
                break
    if chosen is None:
        return False
    path = path or "/"
    for rule in chosen["rules"]:
        if not rule:
            continue
        if path.startswith(rule):
            return True
    return False


def _host(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def host_allowed(final_url, source, requested_url):
    final_host = _host(final_url)
    requested_host = _host(requested_url or source.get("url") or "")
    if not final_host:
        return False
    if final_host == requested_host:
        return True
    allowed = {h.lower() for h in (source.get("allowed_hosts") or [])}
    return final_host in allowed


def _result(**kwargs):
    base = {
        "ok": False,
        "kind": "fetch_failed",
        "requested_url": "",
        "final_url": "",
        "status": None,
        "content_type": "",
        "body": b"",
        "error": None,
        "etag": None,
        "last_modified": None,
        "redirect_chain": [],
        "user_agent": USER_AGENT,
        "reason": "",
    }
    base.update(kwargs)
    return base


class FixtureFetcher:
    """Resolve URLs from an in-memory map. Unknown URLs are connection errors, not searches."""

    def __init__(self, pages, user_agent=USER_AGENT):
        self.pages = pages or {}
        self.user_agent = user_agent
        self.urls = []

    def fetch(self, source, timeout=DEFAULT_TIMEOUT):
        del timeout  # fixtures do not sleep or dial out
        requested = source["url"]
        chain = [requested]
        url = requested
        seen = set()
        for _ in range(MAX_REDIRECTS + 1):
            if url in seen:
                return _result(
                    requested_url=requested, final_url=url, redirect_chain=chain,
                    error="redirect_loop", reason="redirect loop", user_agent=self.user_agent,
                )
            seen.add(url)
            self.urls.append(url)
            spec = self.pages.get(url)
            if spec is None:
                return _result(
                    requested_url=requested, final_url=url, redirect_chain=chain,
                    error="connection_error", reason="fixture has no page for this URL",
                    user_agent=self.user_agent,
                )
            if spec.get("error"):
                return _result(
                    requested_url=requested, final_url=url, redirect_chain=chain,
                    error=spec["error"], reason=spec["error"], status=spec.get("status"),
                    user_agent=self.user_agent,
                )
            status = int(spec.get("status") or 200)
            if status in (301, 302, 303, 307, 308):
                location = spec.get("location") or ""
                if not location:
                    return _result(
                        requested_url=requested, final_url=url, status=status, redirect_chain=chain,
                        error="redirect_missing_location", reason="redirect without a location",
                        user_agent=self.user_agent,
                    )
                location = urljoin(url, location)
                if not host_allowed(location, source, requested):
                    chain.append(location)
                    return _result(
                        ok=False, kind="unexpected_redirect",
                        requested_url=requested, final_url=location, status=status,
                        redirect_chain=chain, reason="redirect left the first-party host allowlist; destination was not retrieved",
                        user_agent=self.user_agent,
                    )
                chain.append(location)
                url = location
                continue
            content_type = spec.get("content_type") or ""
            body = spec.get("body") or b""
            if isinstance(body, str):
                body = body.encode("utf-8")
            if status in (404, 410):
                return _result(
                    ok=False, kind="missing_page",
                    requested_url=requested, final_url=url, status=status,
                    content_type=content_type, body=body, redirect_chain=chain,
                    reason=f"HTTP {status}", user_agent=self.user_agent,
                    etag=spec.get("etag"), last_modified=spec.get("last_modified"),
                )
            if status != 200:
                return _result(
                    requested_url=requested, final_url=url, status=status,
                    content_type=content_type, body=body, redirect_chain=chain,
                    error=f"http_{status}", reason=f"HTTP {status} is a fetch failure, not a disappearance",
                    user_agent=self.user_agent,
                )
            if content_type and not _supported_type(content_type) and not body.lstrip().startswith(b"%PDF"):
                return _result(
                    requested_url=requested, final_url=url, status=status,
                    content_type=content_type, body=body, redirect_chain=chain,
                    error="unsupported_content_type", reason=f"unsupported content type {content_type}",
                    user_agent=self.user_agent,
                )
            return _result(
                ok=True, kind="ok",
                requested_url=requested, final_url=url, status=status,
                content_type=content_type or "text/html",
                body=body, redirect_chain=chain, reason="fetched",
                etag=spec.get("etag"), last_modified=spec.get("last_modified"),
                user_agent=self.user_agent,
            )
        return _result(
            requested_url=requested, final_url=url, redirect_chain=chain,
            error="too_many_redirects", reason="too many redirects", user_agent=self.user_agent,
        )


def _supported_type(content_type):
    ct = content_type.lower()
    return any(token in ct for token in ("html", "xml", "text", "json", "pdf"))


def load_fixture_manifest(path):
    """Load a URL map whose bodies live next to the manifest. No network."""
    import json
    import os
    base = os.path.dirname(os.path.abspath(path))
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, dict) or not pages:
        raise ValueError("fixture manifest has no pages")
    loaded = {}
    for url, spec in pages.items():
        if not isinstance(spec, dict):
            raise ValueError(f"fixture page for {url} must be an object")
        item = dict(spec)
        filename = item.pop("file", None)
        if filename:
            with open(os.path.join(base, filename), "rb") as fh:
                item["body"] = fh.read()
        loaded[url] = item
    return loaded


class LiveFetcher:
    """Manual allowlisted fetch. Disabled unless a caller constructs it on purpose.

    Does not send credentials, does not disable TLS verification, and does not
    follow a redirect onto a host outside the source allowlist.
    """

    def __init__(self, user_agent=USER_AGENT, timeout=DEFAULT_TIMEOUT, max_retries=MAX_RETRIES):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries

    def fetch(self, source, timeout=None):
        requested = source["url"]
        timeout = self.timeout if timeout is None else timeout
        if self._blocked_by_robots(requested, timeout):
            return _result(
                requested_url=requested, final_url=requested,
                error="robots_disallow",
                reason="robots.txt disallows this known URL; the page was not retrieved",
                user_agent=self.user_agent,
            )
        chain = [requested]
        url = requested
        seen = set()
        hops = 0
        while hops <= MAX_REDIRECTS:
            hops += 1
            if url in seen:
                return _result(requested_url=requested, final_url=url, redirect_chain=chain,
                               error="redirect_loop", reason="redirect loop", user_agent=self.user_agent)
            seen.add(url)
            if not host_allowed(url, source, requested) and url != requested:
                return _result(kind="unexpected_redirect", requested_url=requested, final_url=url,
                               redirect_chain=chain, status=302,
                               reason="redirect left the first-party host allowlist; destination was not retrieved",
                               user_agent=self.user_agent)
            status, headers, body, error = self._get(url, timeout)
            if error:
                return _result(requested_url=requested, final_url=url, redirect_chain=chain,
                               error=error, reason=error, user_agent=self.user_agent)
            if status in (301, 302, 303, 307, 308):
                location = headers.get("location") or ""
                if not location:
                    return _result(requested_url=requested, final_url=url, status=status, redirect_chain=chain,
                                   error="redirect_missing_location", reason="redirect without a location",
                                   user_agent=self.user_agent)
                location = urljoin(url, location)
                chain.append(location)
                if not host_allowed(location, source, requested):
                    return _result(kind="unexpected_redirect", requested_url=requested, final_url=location,
                                   status=status, redirect_chain=chain,
                                   reason="redirect left the first-party host allowlist; destination was not retrieved",
                                   user_agent=self.user_agent)
                url = location
                continue
            content_type = headers.get("content-type") or ""
            etag = headers.get("etag")
            last_modified = headers.get("last-modified")
            if status in (404, 410):
                return _result(kind="missing_page", requested_url=requested, final_url=url, status=status,
                               content_type=content_type, body=body, redirect_chain=chain,
                               etag=etag, last_modified=last_modified, reason=f"HTTP {status}",
                               user_agent=self.user_agent)
            if status != 200:
                return _result(requested_url=requested, final_url=url, status=status,
                               content_type=content_type, body=body, redirect_chain=chain,
                               error=f"http_{status}", reason=f"HTTP {status} is a fetch failure, not a disappearance",
                               user_agent=self.user_agent)
            return _result(ok=True, kind="ok", requested_url=requested, final_url=url, status=status,
                           content_type=content_type or "application/octet-stream", body=body,
                           redirect_chain=chain, etag=etag, last_modified=last_modified,
                           reason="fetched", user_agent=self.user_agent)
        return _result(requested_url=requested, final_url=url, redirect_chain=chain,
                       error="too_many_redirects", reason="too many redirects", user_agent=self.user_agent)

    def _blocked_by_robots(self, url, timeout):
        parts = urlparse(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return False
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        status, _headers, body, error = self._get(robots_url, min(timeout, 10))
        if error or status != 200 or not body:
            return False
        return robots_disallows(body.decode("utf-8", errors="replace"), parts.path or "/", self.user_agent)

    def _get(self, url, timeout):
        import http.client

        parts = urlparse(url)
        if parts.scheme not in ("http", "https"):
            return None, {}, b"", "unsupported_scheme"
        path = parts.path or "/"
        if parts.query:
            path = path + "?" + parts.query
        attempts = self.max_retries + 1
        last_error = "connection_error"
        for attempt in range(attempts):
            conn = None
            try:
                if parts.scheme == "https":
                    conn = http.client.HTTPSConnection(parts.hostname, parts.port, timeout=timeout)
                else:
                    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
                conn.request("GET", path, headers={
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
                })
                resp = conn.getresponse()
                status = resp.status
                headers = {k.lower(): v for k, v in resp.getheaders()}
                body = resp.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    return None, headers, b"", "response_too_large"
                if retryable(status, None) and attempt < attempts - 1:
                    continue
                return status, headers, body, None
            except socket.timeout:
                last_error = "timeout"
            except ssl.SSLError:
                last_error = "tls_error"
            except (socket.gaierror, ConnectionError, OSError):
                last_error = "connection_error"
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
            if not retryable(None, last_error) or attempt >= attempts - 1:
                break
        return None, {}, b"", last_error
