from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .session import ConversationSession


@dataclass
class RoundtableParticipantAdapter:
    """Adapts an Oogway session to Roundtable's name/respond protocol."""

    session: ConversationSession

    @property
    def name(self) -> str:
        return self.session.participant_name

    def respond(self, prompt: str) -> tuple[str, dict[str, Any]]:
        response = self.session.ask(prompt)
        metadata = dict(response.metadata)
        metadata.update(
            {
                "kind": "oogway-core",
                "conversation_id": response.conversation_id,
                "round_id": response.round_id,
                "response_turn_id": response.response_turn_id,
            }
        )
        return response.content, metadata
