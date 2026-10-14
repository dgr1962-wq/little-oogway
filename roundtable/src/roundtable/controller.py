from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Iterable

from .participants import Participant
from .transcript import JsonlTranscript
from .types import ParticipantResult, RoundResult


class RoundtableController:
    """Runs participants in declared order and records every outcome."""

    def __init__(
        self,
        participants: Iterable[Participant],
        transcript_directory: Path | str = "transcripts",
    ) -> None:
        self.participants = tuple(participants)
        if not self.participants:
            raise ValueError("At least one participant is required")
        self.transcript_directory = Path(transcript_directory)

    @staticmethod
    def _call(participant: Participant, prompt: str) -> ParticipantResult:
        started = time.perf_counter()
        try:
            content, metadata = participant.respond(prompt)
            return ParticipantResult(
                participant=participant.name,
                content=content,
                error=None,
                duration_ms=round((time.perf_counter() - started) * 1000),
                metadata=metadata,
            )
        except Exception as exc:
            return ParticipantResult(
                participant=participant.name,
                content=None,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=round((time.perf_counter() - started) * 1000),
            )

    @staticmethod
    def _docket(
        results: Iterable[ParticipantResult],
        *,
        limit: int = 8_000,
        redact_private: bool = False,
    ) -> str:
        sections: list[str] = []
        for result in results:
            private = result.metadata.get("kind") == "oogway-core"
            if redact_private and private:
                body = "[Withheld from external docket: local memory-informed statement]"
            else:
                body = result.content if result.succeeded else f"Unavailable: {result.error}"
            if body is not None and len(body) > limit:
                body = body[:limit].rstrip() + "\n[truncated for deliberation]"
            sections.append(f"### {result.participant}\n{body}")
        return "\n\n".join(sections)

    @staticmethod
    def _procedural_ledger(results: Iterable[ParticipantResult]) -> list[dict[str, str]]:
        recognized = (
            "REQUEST FOR CLARIFICATION",
            "POINT OF ORDER",
            "AMENDMENT",
            "OBJECTION",
            "SUPPORT",
            "PASS",
        )
        ledger: list[dict[str, str]] = []
        for result in results:
            disposition = "UNCLASSIFIED"
            if result.succeeded and result.content:
                normalized = re.sub(r"^[\s*#:_-]+", "", result.content).upper()
                disposition = next(
                    (item for item in recognized if normalized.startswith(item)),
                    "UNCLASSIFIED",
                )
            elif not result.succeeded:
                disposition = "UNAVAILABLE"
            ledger.append({"participant": result.participant, "disposition": disposition})
        return ledger

    def run_deliberation(
        self,
        prompt: str,
        *,
        chair: Participant | None = None,
    ) -> RoundResult:
        """Run opening, review, and chaired disposition phases.

        This is a compact deliberative protocol rather than a simulation of a
        legislature. It gives every participant the same agenda and a docket
        appropriate to that participant's privacy boundary,
        recognizes common procedural interventions, preserves dissent, and
        gives the chair the final task of recording the outcome.
        """
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Round prompt cannot be empty")

        chair = chair or self.participants[0]
        round_id = str(uuid.uuid4())
        transcript_path = self.transcript_directory / f"{round_id}.jsonl"
        transcript = JsonlTranscript(transcript_path)
        transcript.write(
            "round_started",
            round_id=round_id,
            mode="deliberation",
            prompt=prompt,
            chair=chair.name,
            participants=[participant.name for participant in self.participants],
            procedure=["opening", "review", "chair_disposition"],
        )

        opening_prompt = (
            "LITTLE OOGWAY ROUNDTABLE — OPENING STATEMENT\n\n"
            f"Agenda:\n{prompt}\n\n"
            "Give your independent analysis and recommendation. State key assumptions, "
            "risks, and any information the group still needs. Be concise. Do not claim "
            "to speak for another participant or report consensus before review."
        )
        openings: list[ParticipantResult] = []
        for position, participant in enumerate(self.participants, start=1):
            result = self._call(participant, opening_prompt)
            openings.append(result)
            transcript.write(
                "participant_completed",
                round_id=round_id,
                phase="opening",
                position=position,
                participant=result.participant,
                content=result.content,
                error=result.error,
                duration_ms=result.duration_ms,
                metadata=result.metadata,
            )

        opening_docket = self._docket(openings)
        reviews: list[ParticipantResult] = []
        for position, participant in enumerate(self.participants, start=1):
            participant_is_chair = participant is chair
            participant_docket = (
                opening_docket if participant_is_chair
                else self._docket(openings, redact_private=True)
            )
            review_prompt = (
                "LITTLE OOGWAY ROUNDTABLE — REVIEW OF THE DOCKET\n\n"
                f"Your identity in this proceeding is {participant.name}. Do not describe "
                f"{participant.name} as a different participant. Your review is your newest "
                "position and supersedes any conflicting wording in your opening.\n\n"
                f"Agenda:\n{prompt}\n\n"
                f"Opening statements:\n\n{participant_docket}\n\n"
                "Review the other statements as well as your own. Begin with exactly one "
                "procedural disposition: SUPPORT, OBJECTION, AMENDMENT, REQUEST FOR "
                "CLARIFICATION, POINT OF ORDER, or PASS. Then give the specific reason. "
                "If proposing an amendment, state exact replacement or additional language. "
                "A point of order must identify a process problem. Address ideas by "
                "participant name. Preserve material disagreement; do not manufacture consensus."
            )
            result = self._call(participant, review_prompt)
            reviews.append(result)
            transcript.write(
                "participant_completed",
                round_id=round_id,
                phase="review",
                position=position,
                private_openings_shared=participant_is_chair,
                participant=result.participant,
                content=result.content,
                error=result.error,
                duration_ms=result.duration_ms,
                metadata=result.metadata,
            )

        procedural_ledger = self._procedural_ledger(reviews)
        transcript.write(
            "procedural_ledger",
            round_id=round_id,
            entries=procedural_ledger,
        )
        review_docket = self._docket(reviews)
        ledger_text = "\n".join(
            f"- {entry['participant']}: {entry['disposition']}"
            for entry in procedural_ledger
        )
        chair_prompt = (
            "LITTLE OOGWAY ROUNDTABLE — CHAIR'S DISPOSITION\n\n"
            f"You are {chair.name}, the presiding chair.\n\n"
            f"Agenda:\n{prompt}\n\n"
            f"Opening statements:\n\n{opening_docket}\n\n"
            f"Review statements and procedural interventions:\n\n{review_docket}\n\n"
            f"Mechanically classified procedural ledger:\n{ledger_text}\n\n"
            "You are the presiding chair. Produce accurate minutes under these headings: "
            "Disposition (CONSENSUS, MIXED, or DEFERRED); Recommendation; Agreements; "
            "Objections and minority views; Unresolved questions; Action items. Resolve "
            "each amendment, clarification request, and point of order explicitly. A review "
            "is that participant's controlling position when it conflicts with their opening. "
            "Use only the participant names in this docket. Assign an action to a participant "
            "only if that participant explicitly volunteered; otherwise write UNASSIGNED. "
            "Do not invent teams, people, votes, dates, deadlines, tests, or completed actions. "
            "Do not use placeholders. If two statements remain ambiguous or contradictory, "
            "record the ambiguity as unresolved instead of guessing. Retrieved memories are "
            "context, not evidence that a present-day capability or test is complete."
        )
        chair_result = self._call(chair, chair_prompt)
        chair_result = ParticipantResult(
            participant=chair_result.participant,
            content=chair_result.content,
            error=chair_result.error,
            duration_ms=chair_result.duration_ms,
            metadata={**chair_result.metadata, "procedural_ledger": procedural_ledger},
        )
        transcript.write(
            "chair_disposition",
            round_id=round_id,
            participant=chair_result.participant,
            content=chair_result.content,
            error=chair_result.error,
            duration_ms=chair_result.duration_ms,
            metadata=chair_result.metadata,
        )

        all_results = (*openings, *reviews, chair_result)
        succeeded = all(result.succeeded for result in all_results)
        transcript.write(
            "round_completed",
            round_id=round_id,
            mode="deliberation",
            succeeded=succeeded,
            successful_turns=sum(result.succeeded for result in all_results),
            failed_turns=sum(not result.succeeded for result in all_results),
        )
        return RoundResult(
            round_id=round_id,
            prompt=prompt,
            participants=tuple(openings),
            reviews=tuple(reviews),
            chair=chair_result,
            transcript_path=transcript_path,
        )

    def run_round(self, prompt: str) -> RoundResult:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Round prompt cannot be empty")

        round_id = str(uuid.uuid4())
        transcript_path = self.transcript_directory / f"{round_id}.jsonl"
        transcript = JsonlTranscript(transcript_path)
        transcript.write(
            "round_started",
            round_id=round_id,
            prompt=prompt,
            participants=[participant.name for participant in self.participants],
        )

        results: list[ParticipantResult] = []
        for position, participant in enumerate(self.participants, start=1):
            result = self._call(participant, prompt)

            results.append(result)
            transcript.write(
                "participant_completed",
                round_id=round_id,
                position=position,
                participant=result.participant,
                content=result.content,
                error=result.error,
                duration_ms=result.duration_ms,
                metadata=result.metadata,
            )

        succeeded = all(result.succeeded for result in results)
        transcript.write(
            "round_completed",
            round_id=round_id,
            succeeded=succeeded,
            successful_participants=sum(result.succeeded for result in results),
            failed_participants=sum(not result.succeeded for result in results),
        )
        return RoundResult(
            round_id=round_id,
            prompt=prompt,
            participants=tuple(results),
            transcript_path=transcript_path,
        )
