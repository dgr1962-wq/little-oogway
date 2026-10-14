from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ParticipantResult:
    """The recorded outcome of one participant's turn."""

    participant: str
    content: str | None
    error: str | None
    duration_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class RoundResult:
    """The complete result of one deterministic round."""

    round_id: str
    prompt: str
    participants: tuple[ParticipantResult, ...]
    transcript_path: Path
    reviews: tuple[ParticipantResult, ...] = ()
    chair: ParticipantResult | None = None

    @property
    def succeeded(self) -> bool:
        outcomes = (*self.participants, *self.reviews)
        if self.chair is not None:
            outcomes = (*outcomes, self.chair)
        return all(result.succeeded for result in outcomes)
