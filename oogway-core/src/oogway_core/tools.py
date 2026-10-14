from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .ingestion import classify_locator, validate_url
from .operator import PathPolicy


URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
ABSORB_RE = re.compile(r"\babsorb(?:\s+(?:this|it|the\s+(?:file|page|source)))?\b", re.IGNORECASE)


@dataclass(frozen=True)
class ToolResult:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ConversationalTool(Protocol):
    name: str

    def try_execute(self, prompt: str) -> ToolResult | None: ...


class IngestionQueue(Protocol):
    def enqueue_ingestion_job(
        self,
        *,
        source_kind: str,
        source_locator: str,
        options: dict[str, Any] | None = None,
        requested_by: str = "local-user",
        max_attempts: int = 3,
    ) -> tuple[str, bool]: ...


def start_background_worker() -> None:
    try:
        subprocess.run(
            ["systemctl", "--user", "start", "oogway-ingest.service"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _source_candidates(prompt: str) -> list[str]:
    candidates = [match.group(0).rstrip(".,;:!?)]}") for match in URL_RE.finditer(prompt)]
    try:
        tokens = shlex.split(prompt)
    except ValueError:
        tokens = prompt.split()
    for token in tokens:
        cleaned = token.rstrip(".,;:!?)]}")
        if cleaned.startswith(("/", "~/")):
            candidates.append(cleaned)
    return list(dict.fromkeys(candidates))


@dataclass
class AbsorbSourceTool:
    queue: IngestionQueue
    autostart: bool = True
    path_policy: PathPolicy = field(default_factory=PathPolicy)
    name: str = "absorb_source"

    @staticmethod
    def can_handle(prompt: str) -> bool:
        """Return whether this prompt is an explicit bounded ingestion request."""
        if ABSORB_RE.search(prompt) is None:
            return False
        if _source_candidates(prompt):
            return True
        return re.search(r"\babsorb\s+(?:this|it)\b", prompt, re.IGNORECASE) is not None

    def try_execute(self, prompt: str) -> ToolResult | None:
        intent = ABSORB_RE.search(prompt)
        if intent is None:
            return None
        candidates = _source_candidates(prompt)
        if not candidates:
            if re.search(r"\babsorb\s+(?:this|it)\b", prompt, re.IGNORECASE):
                return ToolResult(
                    "Please give me the exact AnyKeyCafe URL or local text-file path to absorb.",
                    {"tool": self.name, "status": "needs_source"},
                )
            return None
        if len(candidates) != 1:
            return ToolResult(
                "Please give me one source at a time so each ingestion job has a clear audit trail.",
                {"tool": self.name, "status": "needs_one_source", "source_count": len(candidates)},
            )
        requested = candidates[0]
        try:
            kind, locator = classify_locator(requested)
            if kind == "url":
                validate_url(locator)
            else:
                locator = str(self.path_policy.resolve(locator))
            job_id, created = self.queue.enqueue_ingestion_job(
                source_kind=kind,
                source_locator=locator,
                options={"chunk_chars": 3000, "overlap": 300},
                requested_by="oogway-conversation-tool",
                max_attempts=3,
            )
            if self.autostart:
                start_background_worker()
        except (OSError, RuntimeError, ValueError) as exc:
            return ToolResult(
                f"I could not queue that source: {exc}",
                {
                    "tool": self.name,
                    "status": "rejected",
                    "requested_source": requested,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        verb = "Queued" if created else "That source already has an active"
        content = f"{verb} ingestion job `{job_id}` for `{locator}`."
        return ToolResult(
            content,
            {
                "tool": self.name,
                "status": "queued" if created else "already_active",
                "job_id": job_id,
                "source_kind": kind,
                "source_locator": locator,
                "worker_start_requested": self.autostart,
            },
        )
