from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Callable

from .ingestion import DEFAULT_ALLOWED_HOSTS, validate_url


DEFAULT_SITE = "https://anykeycafe.com"
WORDPRESS_TYPES = frozenset({"post", "page", "ak_book", "ak_conversation", "envira"})
USER_AGENT = "Little-Oogway-Archive-Controller/0.1"


@dataclass(frozen=True)
class ArchiveItem:
    url: str
    discovered_by: tuple[str, ...]


@dataclass(frozen=True)
class ArchiveQueueResult:
    discovered: int
    selected: int
    queued: int
    already_active: int
    job_ids: tuple[str, ...]
    urls: tuple[str, ...]


def canonical_url(value: str) -> str:
    value = value.strip()
    validate_url(value)
    parsed = urllib.parse.urlsplit(value)
    host = (parsed.hostname or "").lower()
    path = urllib.parse.unquote(parsed.path or "/")
    path = "/" + "/".join(part for part in path.split("/") if part)
    if path != "/":
        path += "/"
    return urllib.parse.urlunsplit(("https", host, path, parsed.query, ""))


class AnyKeyArchiveController:
    """Discover published AnyKeyCafe pages and submit them to the existing queue."""

    def __init__(
        self,
        queue: Any,
        *,
        site: str = DEFAULT_SITE,
        opener: Callable[[str], tuple[bytes, dict[str, str]]] | None = None,
    ) -> None:
        self.queue = queue
        self.site = site.rstrip("/")
        self._opener = opener or self._open

    @staticmethod
    def _open(url: str) -> tuple[bytes, dict[str, str]]:
        validate_url(url)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            final_url = response.geturl()
            validate_url(final_url)
            raw = response.read(10 * 1024 * 1024 + 1)
            if len(raw) > 10 * 1024 * 1024:
                raise ValueError("Archive discovery response exceeds 10 MiB")
            headers = {key.lower(): value for key, value in response.headers.items()}
        return raw, headers

    def _json(self, url: str) -> tuple[Any, dict[str, str]]:
        raw, headers = self._opener(url)
        return json.loads(raw.decode("utf-8")), headers

    def _xml_locations(self, url: str) -> tuple[str, list[str]]:
        raw, _ = self._opener(url)
        root = ET.fromstring(raw)
        return root.tag.rsplit("}", 1)[-1], [
            node.text.strip()
            for node in root.findall(".//{*}loc")
            if node.text and node.text.strip()
        ]

    @staticmethod
    def _eligible_page(url: str) -> bool:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in DEFAULT_ALLOWED_HOSTS:
            return False
        path = parsed.path.lower()
        return not any(
            marker in path
            for marker in ("/wp-admin/", "/wp-json/", "/feed/", "/author/")
        ) and not path.endswith((".xml", ".xsl"))

    def discover(self) -> list[ArchiveItem]:
        discovered: dict[str, set[str]] = {}

        def add(value: str, source: str) -> None:
            try:
                url = canonical_url(value)
            except ValueError:
                return
            if self._eligible_page(url):
                discovered.setdefault(url, set()).add(source)

        types_url = f"{self.site}/wp-json/wp/v2/types"
        types, _ = self._json(types_url)
        for type_name in sorted(WORDPRESS_TYPES.intersection(types)):
            detail = types[type_name]
            rest_base = detail.get("rest_base")
            namespace = detail.get("rest_namespace", "wp/v2")
            if not isinstance(rest_base, str) or "(?P<" in rest_base:
                continue
            page = 1
            while True:
                query = urllib.parse.urlencode({
                    "status": "publish",
                    "per_page": 100,
                    "page": page,
                    "_fields": "id,link,status,slug,type,modified_gmt",
                })
                endpoint = f"{self.site}/wp-json/{namespace}/{rest_base}?{query}"
                entries, headers = self._json(endpoint)
                if not isinstance(entries, list):
                    raise ValueError(f"WordPress returned a non-list for {type_name}")
                for entry in entries:
                    if isinstance(entry, dict) and entry.get("status") == "publish":
                        link = entry.get("link")
                        if isinstance(link, str):
                            add(link, f"wordpress:{type_name}")
                total_pages = int(headers.get("x-wp-totalpages", page))
                if page >= total_pages:
                    break
                page += 1

        for sitemap_url in (
            f"{self.site}/wp-sitemap.xml",
            f"{self.site}/ai/sitemap.xml",
        ):
            root_kind, locations = self._xml_locations(sitemap_url)
            if root_kind == "sitemapindex":
                child_maps = [
                    value for value in locations
                    if "/wp-sitemap-posts-" in urllib.parse.urlsplit(value).path
                ]
                for child in child_maps:
                    _, child_locations = self._xml_locations(child)
                    for value in child_locations:
                        add(value, f"sitemap:{urllib.parse.urlsplit(child).path.rsplit('/', 1)[-1]}")
            else:
                for value in locations:
                    add(value, f"sitemap:{urllib.parse.urlsplit(sitemap_url).path}")

        return [
            ArchiveItem(url=url, discovered_by=tuple(sorted(sources)))
            for url, sources in sorted(discovered.items())
        ]

    def enqueue(
        self,
        *,
        sample: int | None = None,
        chunk_chars: int = 3000,
        overlap: int = 300,
        max_attempts: int = 3,
    ) -> ArchiveQueueResult:
        inventory = self.discover()
        selected = inventory if sample is None else inventory[:sample]
        queued = 0
        already_active = 0
        job_ids: list[str] = []
        for item in selected:
            job_id, created = self.queue.enqueue_ingestion_job(
                source_kind="url",
                source_locator=item.url,
                options={
                    "chunk_chars": chunk_chars,
                    "overlap": overlap,
                    "archive_discovered_by": list(item.discovered_by),
                },
                requested_by="oogway-core-archive-controller",
                max_attempts=max_attempts,
            )
            job_ids.append(job_id)
            if created:
                queued += 1
            else:
                already_active += 1
        return ArchiveQueueResult(
            discovered=len(inventory),
            selected=len(selected),
            queued=queued,
            already_active=already_active,
            job_ids=tuple(job_ids),
            urls=tuple(item.url for item in selected),
        )
