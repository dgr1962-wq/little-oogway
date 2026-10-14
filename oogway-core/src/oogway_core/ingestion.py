from __future__ import annotations

import hashlib
import html
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from .memory import load_transcript


MAX_SOURCE_BYTES = 10 * 1024 * 1024
DEFAULT_ALLOWED_HOSTS = frozenset({"anykeycafe.com", "www.anykeycafe.com"})


@dataclass(frozen=True)
class IngestionSource:
    kind: str
    locator: str
    text: str
    content_sha256: str
    byte_count: int
    metadata: dict[str, object]


class _ReadableHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.main_parts: list[str] = []
        self.ignored_depth = 0
        self.main_depth = 0

    def _append(self, value: str) -> None:
        self.parts.append(value)
        if self.main_depth:
            self.main_parts.append(value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.ignored_depth += 1
            return
        if tag in {"main", "article"}:
            self.main_depth += 1
        if not self.ignored_depth and tag in {
            "p", "div", "section", "article", "main", "header", "footer",
            "h1", "h2", "h3", "h4", "h5", "h6", "li", "br", "tr",
        }:
            self._append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and tag in {"p", "div", "section", "article", "li", "tr"}:
            self._append("\n")
        if tag in {"main", "article"} and self.main_depth:
            self.main_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self._append(data)

    def text(self) -> str:
        selected = self.main_parts if len("".join(self.main_parts).strip()) >= 200 else self.parts
        value = html.unescape("".join(selected)).replace("\r\n", "\n").replace("\r", "\n")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n\s*\n\s*\n+", "\n\n", value)
        return value.strip()


def classify_locator(value: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in {"http", "https"}:
        if not parsed.netloc:
            raise ValueError("URL source has no host")
        return "url", value
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Local source is not a readable file: {path}")
    return "local_file", str(path)


def validate_url(locator: str, allowed_hosts: frozenset[str] = DEFAULT_ALLOWED_HOSTS) -> None:
    parsed = urllib.parse.urlparse(locator)
    if parsed.scheme != "https":
        raise ValueError("Remote ingestion requires HTTPS")
    hostname = (parsed.hostname or "").lower()
    if hostname not in allowed_hosts:
        raise ValueError(
            f"Remote host is not approved for ingestion: {hostname or '(missing)'}"
        )
    if parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError("Remote ingestion URL contains unsupported authority fields")


class _ValidatedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_source(kind: str, locator: str) -> IngestionSource:
    if kind == "local_file":
        path = Path(locator)
        text, digest, byte_count = load_transcript(path)
        if byte_count > MAX_SOURCE_BYTES:
            raise ValueError(f"Source exceeds {MAX_SOURCE_BYTES} byte limit")
        return IngestionSource(
            kind=kind,
            locator=str(path.resolve()),
            text=text,
            content_sha256=digest,
            byte_count=byte_count,
            metadata={"original_filename": path.name},
        )
    if kind != "url":
        raise ValueError(f"Unsupported ingestion source kind: {kind}")
    validate_url(locator)
    request = urllib.request.Request(
        locator,
        headers={"User-Agent": "Little-Oogway-Ingestion/0.1"},
    )
    try:
        opener = urllib.request.build_opener(_ValidatedRedirectHandler())
        with opener.open(request, timeout=30) as response:
            final_url = response.geturl()
            validate_url(final_url)
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > MAX_SOURCE_BYTES:
                raise ValueError(f"Source exceeds {MAX_SOURCE_BYTES} byte limit")
            raw = response.read(MAX_SOURCE_BYTES + 1)
            content_type = response.headers.get_content_type()
            charset = response.headers.get_content_charset() or "utf-8"
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not fetch source: {exc}") from exc
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError(f"Source exceeds {MAX_SOURCE_BYTES} byte limit")
    if content_type not in {"text/html", "text/plain"}:
        raise ValueError(f"Unsupported remote content type: {content_type}")
    decoded = raw.decode(charset, errors="replace")
    if content_type == "text/html":
        parser = _ReadableHTML()
        parser.feed(decoded)
        text = parser.text()
    else:
        text = decoded.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("Source contains no readable text")
    return IngestionSource(
        kind=kind,
        locator=final_url,
        text=text,
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        byte_count=len(raw),
        metadata={"content_type": content_type, "requested_url": locator},
    )
