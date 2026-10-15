"""
title: Little Oogway Local Workbench
author: AnyKey Cafe
version: 0.3.0
required_open_webui_version: 0.11.0
description: Admin-only document, OCR, media, archive, transcription, file-search, hashing, duplicate, and bounded Git tools through Oogway Core.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:8094"
TOKEN_FILE = Path.home() / ".config/little-oogway/operator.token"


def _admin(user: dict[str, Any] | None) -> bool:
    return (user or {}).get("role") == "admin"


def _request(path: str, payload: dict) -> dict:
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    request = Request(
        BASE_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=1_200) as response:
        return json.loads(response.read().decode("utf-8"))


def _denied() -> str:
    return "Denied: local workbench tools require an authenticated administrator."


class Tools:
    def inspect_creative_capabilities(self, __user__: dict[str, Any] | None = None) -> str:
        """Inspect installed creative applications and the bounded operations Little Oogway may actually perform."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/creative/capabilities", {}), indent=2, ensure_ascii=False)

    def transcode_media(
        self,
        path: str,
        profile: str,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Create a bounded media derivative using one fixed profile: web-video, web-audio, lossless-audio, thumbnail, or gif-preview."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/creative/transcode", {"path": path, "profile": profile}), indent=2, ensure_ascii=False)

    def render_blender_project(
        self,
        path: str,
        start_frame: int = 1,
        end_frame: int = 1,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Render 1-300 frames from an approved .blend project headlessly with embedded Python disabled; outputs stay in the workbench creative directory."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/creative/render-blender", {"path": path, "start_frame": start_frame, "end_frame": end_frame}), indent=2, ensure_ascii=False)

    def inspect_workbench_capabilities(self, __user__: dict[str, Any] | None = None) -> str:
        """Inspect the live local workbench providers, supported formats, model cache, output boundary, and security exclusions instead of guessing from memory."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/capabilities", {}), indent=2, ensure_ascii=False)

    def read_document(
        self,
        path: str,
        ocr_if_needed: bool = True,
        max_pages: int = 30,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Read modern and legacy documents, spreadsheets, and presentations from an approved local path. Scanned PDFs may fall back to local OCR."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/document/read", {"path": path, "ocr_if_needed": ocr_if_needed, "max_pages": max_pages}), indent=2, ensure_ascii=False)

    def convert_document_to_markdown(
        self,
        path: str,
        ocr_if_needed: bool = True,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Convert a supported local document into provenance-labelled Markdown under the bounded workbench output directory."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/document/convert", {"path": path, "ocr_if_needed": ocr_if_needed}), indent=2, ensure_ascii=False)

    def ocr_document(
        self,
        path: str,
        max_pages: int = 10,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Run local CPU OCR on a scanned PDF or photographed page from an approved path; PDF pages are capped."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/document/ocr", {"path": path, "max_pages": max_pages}), indent=2, ensure_ascii=False)

    def inspect_media(self, path: str, __user__: dict[str, Any] | None = None) -> str:
        """Report codecs, streams, duration, resolution, hashes, and available image EXIF metadata for an approved media file."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/media/inspect", {"path": path}), indent=2, ensure_ascii=False)

    def inspect_archive(self, path: str, __user__: dict[str, Any] | None = None) -> str:
        """Inspect ZIP, 7z, or TAR-family contents and enforce entry, size, traversal, and link limits without extracting."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/archive/inspect", {"path": path}), indent=2, ensure_ascii=False)

    def extract_archive_safely(self, path: str, __user__: dict[str, Any] | None = None) -> str:
        """Extract a validated archive only into the bounded workbench output directory. Absolute paths, traversal, links, and oversized archives are rejected."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/archive/extract", {"path": path}), indent=2, ensure_ascii=False)

    def transcribe_audio(
        self,
        path: str,
        language: str = "",
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Transcribe up to two hours of approved local audio with faster-whisper base on CPU. The model downloads locally on first use."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/audio/transcribe", {"path": path, "language": language}), indent=2, ensure_ascii=False)

    def search_files_advanced(
        self,
        root: str,
        query: str,
        mode: str = "content",
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Search approved roots by ripgrep content, filename, or bounded metadata. Protected credential and browser areas are excluded."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/files/search", {"root": root, "query": query, "mode": mode}), indent=2, ensure_ascii=False)

    def find_duplicate_files(self, root: str, __user__: dict[str, Any] | None = None) -> str:
        """Find duplicate files under an approved root using size grouping and streaming SHA-256, without deleting or moving anything."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/files/duplicates", {"root": root}), indent=2, ensure_ascii=False)

    def hash_file(self, path: str, __user__: dict[str, Any] | None = None) -> str:
        """Calculate a streaming SHA-256 hash for an approved local file."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/files/hash", {"path": path}), indent=2, ensure_ascii=False)

    def git_status(self, repository: str, __user__: dict[str, Any] | None = None) -> str:
        """Inspect bounded Git branch and working-tree status without changing the repository."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/git/status", {"repository": repository}), indent=2, ensure_ascii=False)

    def git_diff(
        self,
        repository: str,
        staged: bool = False,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Inspect a bounded, pager-free Git diff. Set staged=true for the index; no repository state is changed."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/git/diff", {"repository": repository, "staged": staged}), indent=2, ensure_ascii=False)

    def git_run_tests(
        self,
        repository: str,
        profile: str = "all",
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Run only a pre-registered test profile (core, roundtable, or all) for the Little Oogway repository. Arbitrary commands are impossible."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/git/test", {"repository": repository, "profile": profile}), indent=2, ensure_ascii=False)

    def git_propose_commit(self, repository: str, __user__: dict[str, Any] | None = None) -> str:
        """Summarize staged and unstaged Git state as a commit proposal. This never stages, commits, pushes, or executes a shell command."""
        if not _admin(__user__):
            return _denied()
        return json.dumps(_request("/v1/workbench/git/propose-commit", {"repository": repository}), indent=2, ensure_ascii=False)
