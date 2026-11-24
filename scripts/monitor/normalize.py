"""Separate a raw source fingerprint from a normalized reviewable-text fingerprint.

Normalization removes markup noise so a stylesheet, script, footer, or
navigation edit is not treated as a new fact. It does not prove that two
pages mean the same thing; fact comparison is a later step.
"""
from __future__ import annotations

import hashlib
import html
import re
from html.parser import HTMLParser

_DROP = {"script", "style", "noscript", "nav", "footer", "header", "svg", "iframe", "template"}
_BREAK = {"p", "div", "li", "h1", "h2", "h3", "h4", "br", "tr", "section", "article", "blockquote"}


class _ReviewableHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._main_depth = 0
        self._saw_main = False
        self._parts = []
        self._main = []

    def handle_starttag(self, tag, attrs):
        self._start(tag)

    def handle_startendtag(self, tag, attrs):
        self._start(tag)
        self._end(tag)

    def _start(self, tag):
        tag = (tag or "").lower()
        if tag in _DROP:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "main":
            self._saw_main = True
            self._main_depth += 1
        if tag in _BREAK:
            self._add("\n")

    def handle_endtag(self, tag):
        self._end(tag)

    def _end(self, tag):
        tag = (tag or "").lower()
        if tag in _DROP and self._skip:
            self._skip -= 1
            return
        if self._skip:
            return
        if tag == "main" and self._main_depth:
            self._main_depth -= 1
            self._add("\n")
        elif tag in _BREAK:
            self._add("\n")

    def handle_data(self, data):
        if self._skip or not data:
            return
        self._add(data)

    def _add(self, text):
        self._parts.append(text)
        if self._main_depth:
            self._main.append(text)

    def reviewable(self):
        raw = "".join(self._main if self._saw_main else self._parts)
        return collapse_reviewable(html.unescape(raw))


def collapse_reviewable(text):
    lines = []
    for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[ \t\f\v]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def reviewable_text(body):
    """Visible text used for comparison. Prefers <main> and drops script/style/nav/footer."""
    if body is None:
        return ""
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="replace")
    else:
        text = str(body)
    stripped = text.lstrip()
    if stripped.startswith("%PDF"):
        return ""
    if "<" not in text and ">" not in text:
        return collapse_reviewable(html.unescape(text))
    parser = _ReviewableHTML()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        return collapse_reviewable(re.sub(r"<[^>]+>", " ", text))
    return parser.reviewable()


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def sha256_bytes(data):
    if data is None:
        data = b""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def as_bytes(body):
    if body is None:
        return b""
    if isinstance(body, bytes):
        return body
    return str(body).encode("utf-8")
