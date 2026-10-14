from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TextChunk:
    ordinal: int
    content: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class RedactedText:
    content: str
    counts: dict[str, int]


_SECRET_PATTERNS = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "assigned_secret",
        re.compile(
            r"(?im)\b(api[_ -]?key|access[_ -]?token|password|secret)\b"
            r"(\s*[:=]\s*)(?!\[REDACTED)([^\s,;]{8,})"
        ),
    ),
)


def redact_secrets(text: str) -> RedactedText:
    counts: dict[str, int] = {}
    content = text
    for label, pattern in _SECRET_PATTERNS:
        if label == "assigned_secret":
            content, count = pattern.subn(
                lambda match: f"{match.group(1)}{match.group(2)}[REDACTED:{label}]",
                content,
            )
        else:
            content, count = pattern.subn(f"[REDACTED:{label}]", content)
        if count:
            counts[label] = count
    return RedactedText(content=content, counts=counts)


def chunk_text(text: str, *, max_chars: int = 3000, overlap: int = 300) -> list[TextChunk]:
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be non-negative and smaller than max_chars")
    chunks: list[TextChunk] = []
    start = 0
    length = len(text)
    while start < length:
        while start < length and text[start].isspace():
            start += 1
        if start >= length:
            break
        hard_end = min(start + max_chars, length)
        end = hard_end
        if hard_end < length:
            minimum = start + max_chars // 2
            paragraph_break = text.rfind("\n\n", minimum, hard_end)
            line_break = text.rfind("\n", minimum, hard_end)
            space_break = text.rfind(" ", minimum, hard_end)
            end = max(paragraph_break + 2, line_break + 1, space_break + 1, minimum)
        content = text[start:end].strip()
        if content:
            chunks.append(
                TextChunk(
                    ordinal=len(chunks),
                    content=content,
                    char_start=start,
                    char_end=end,
                )
            )
        if end >= length:
            break
        next_start = max(end - overlap, start + 1)
        boundary = text.find("\n", next_start, end)
        start = boundary + 1 if boundary >= 0 else next_start
    return chunks


def load_transcript(path: Path) -> tuple[str, str, int]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n"), digest, len(raw)
