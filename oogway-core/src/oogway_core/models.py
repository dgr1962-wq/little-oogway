from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelResponse:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionResponse:
    conversation_id: str
    round_id: str
    prompt_turn_id: str
    response_turn_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
