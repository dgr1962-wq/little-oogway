from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime


_TOKEN = re.compile(r"[\w']+")
_CONVERSATION_TIMESTAMP = re.compile(
    r"\[(?:[^\]\n]{1,80}?\s-\s)?"
    r"(20\d{2}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?)\]"
)


@dataclass(frozen=True)
class CanonicalCandidate:
    memory_id: str
    content: str
    source_locator: str
    source_ordinal: int
    source_modified_at: datetime | None = None


@dataclass(frozen=True)
class CanonicalDecision:
    preferred: CanonicalCandidate
    alternate: CanonicalCandidate
    reason: str
    conversation_timestamp: datetime | None = None


def normalized_tokens(content: str) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(content.casefold()))


def shingle_containment(left: str, right: str, *, width: int = 5) -> float:
    """Measure how fully the smaller passage is contained in the larger passage."""
    left_tokens = normalized_tokens(left)
    right_tokens = normalized_tokens(right)
    if min(len(left_tokens), len(right_tokens)) < max(width * 2, 20):
        return 0.0
    left_shingles = {
        left_tokens[index : index + width]
        for index in range(len(left_tokens) - width + 1)
    }
    right_shingles = {
        right_tokens[index : index + width]
        for index in range(len(right_tokens) - width + 1)
    }
    denominator = min(len(left_shingles), len(right_shingles))
    return len(left_shingles & right_shingles) / denominator if denominator else 0.0


def conversation_timestamp(content: str) -> datetime | None:
    timestamps = []
    for value in _CONVERSATION_TIMESTAMP.findall(content):
        try:
            timestamps.append(datetime.fromisoformat(value.replace(" ", "T")))
        except ValueError:
            continue
    return max(timestamps, default=None)


def choose_canonical(
    left: CanonicalCandidate, right: CanonicalCandidate
) -> CanonicalDecision:
    left_timestamp = conversation_timestamp(left.content)
    right_timestamp = conversation_timestamp(right.content)
    if left_timestamp != right_timestamp and (left_timestamp or right_timestamp):
        if right_timestamp is not None and (
            left_timestamp is None or right_timestamp > left_timestamp
        ):
            return CanonicalDecision(right, left, "explicit_conversation_timestamp", right_timestamp)
        return CanonicalDecision(left, right, "explicit_conversation_timestamp", left_timestamp)

    left_length = len(" ".join(left.content.split()))
    right_length = len(" ".join(right.content.split()))
    if left_length != right_length:
        preferred, alternate = (left, right) if left_length > right_length else (right, left)
        return CanonicalDecision(preferred, alternate, "more_complete_passage")

    if left.source_modified_at != right.source_modified_at:
        if right.source_modified_at is not None and (
            left.source_modified_at is None
            or right.source_modified_at > left.source_modified_at
        ):
            return CanonicalDecision(right, left, "newer_source_export")
        return CanonicalDecision(left, right, "newer_source_export")

    left_key = (left.source_locator, left.source_ordinal, left.memory_id)
    right_key = (right.source_locator, right.source_ordinal, right.memory_id)
    preferred, alternate = (left, right) if left_key <= right_key else (right, left)
    return CanonicalDecision(preferred, alternate, "stable_source_order")
