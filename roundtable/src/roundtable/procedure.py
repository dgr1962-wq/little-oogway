from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from .participants import Participant
from .transcript import JsonlTranscript
from .types import ParticipantResult


DISPOSITIONS = (
    "REQUEST FOR CLARIFICATION",
    "POINT OF ORDER",
    "AMENDMENT",
    "OBJECTION",
    "SUPPORT",
    "PASS",
)
ACTIONABLE_DISPOSITIONS = {
    "REQUEST FOR CLARIFICATION",
    "POINT OF ORDER",
    "AMENDMENT",
    "UNCLASSIFIED",
}
ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class ProceduralRoundResult:
    round_id: str
    motion: str
    openings: tuple[ParticipantResult, ...]
    review_passes: tuple[tuple[ParticipantResult, ...], ...]
    chair_reports: tuple[ParticipantResult, ...]
    status: str
    transcript_path: Path
    state_path: Path

    @property
    def reviews(self) -> tuple[ParticipantResult, ...]:
        return self.review_passes[-1]

    @property
    def chair(self) -> ParticipantResult:
        return self.chair_reports[-1]

    @property
    def succeeded(self) -> bool:
        outcomes: tuple[ParticipantResult, ...] = self.openings
        for review_pass in self.review_passes:
            outcomes += review_pass
        outcomes += self.chair_reports
        return all(result.succeeded for result in outcomes)


class ResumableProcedure:
    """A resumable, audited deliberation with operator rulings between passes.

    This is deliberately a practical parliamentary workflow, not an attempted
    implementation of Robert's Rules. Amendments, clarification requests, and
    points of order keep the round open. The operator can then supply a ruling
    or missing fact and run another review pass without repeating openings.
    """

    def __init__(
        self,
        participants: Iterable[Participant],
        transcript_directory: Path | str = "transcripts",
    ) -> None:
        self.participants = tuple(participants)
        if not self.participants:
            raise ValueError("At least one participant is required")
        names = [participant.name for participant in self.participants]
        if len(set(names)) != len(names):
            raise ValueError("Participant names must be unique")
        self.private_participants = frozenset(
            participant.name
            for participant in self.participants
            if getattr(participant, "kind", None) == "oogway-core"
        )
        self.transcript_directory = Path(transcript_directory)
        self.state_directory = self.transcript_directory / "state"

    @staticmethod
    def _call(participant: Participant, prompt: str) -> ParticipantResult:
        started = time.perf_counter()
        max_attempts = 2 if getattr(participant, "retry_safe", False) else 1
        errors: list[str] = []
        for attempt in range(1, max_attempts + 1):
            try:
                content, metadata = participant.respond(prompt)
                return ParticipantResult(
                    participant=participant.name,
                    content=content,
                    error=None,
                    duration_ms=round((time.perf_counter() - started) * 1000),
                    metadata={
                        **metadata,
                        "attempt_count": attempt,
                        "recovered_errors": errors,
                    },
                )
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
        return ParticipantResult(
            participant=participant.name,
            content=None,
            error=errors[-1],
            duration_ms=round((time.perf_counter() - started) * 1000),
            metadata={
                "kind": getattr(participant, "kind", "unknown"),
                "attempt_count": max_attempts,
                "attempt_errors": errors,
            },
        )

    @staticmethod
    def _result_dict(result: ParticipantResult) -> dict[str, Any]:
        return asdict(result)

    @staticmethod
    def _result_from_dict(value: dict[str, Any]) -> ParticipantResult:
        return ParticipantResult(**value)

    def _is_private(self, result: ParticipantResult) -> bool:
        # Seat identity is authoritative even when a failed/legacy result has
        # missing or malformed metadata.  Metadata remains a compatibility
        # signal for older state files, but can never make a configured private
        # seat public.
        return (
            result.participant in self.private_participants
            or result.metadata.get("kind") == "oogway-core"
        )

    def _docket(
        self,
        results: Iterable[ParticipantResult],
        *,
        redact_private: bool = False,
        limit: int = 8_000,
    ) -> str:
        sections: list[str] = []
        for result in results:
            if redact_private and self._is_private(result):
                body = "[Withheld from external docket: local memory-informed statement]"
            else:
                body = result.content if result.succeeded else f"Unavailable: {result.error}"
            if body is not None and len(body) > limit:
                body = body[:limit].rstrip() + "\n[truncated for deliberation]"
            sections.append(f"### {result.participant}\n{body}")
        return "\n\n".join(sections)

    @staticmethod
    def _disposition(result: ParticipantResult) -> str:
        if not result.succeeded or not result.content:
            return "UNAVAILABLE"
        first_line = next(
            (line.strip() for line in result.content.splitlines() if line.strip()), ""
        )
        normalized = re.sub(r"^[\s*#]+", "", first_line.upper())
        normalized = re.sub(r"[\s*]+$", "", normalized)
        normalized = re.sub(r"^DISPOSITION\s*:\s*", "", normalized)
        alternatives = "|".join(re.escape(value) for value in DISPOSITIONS)
        found = set(re.findall(rf"(?<![A-Z])({alternatives})(?![A-Z])", normalized))
        leading = re.match(rf"^({alternatives})(?![A-Z])", normalized)
        if leading is None or found != {leading.group(1)}:
            return "UNCLASSIFIED"
        return leading.group(1)

    @staticmethod
    def _required_chair_disposition(
        ledger: list[dict[str, Any]], target_status: str
    ) -> str:
        if target_status == "awaiting_ruling":
            return "DEFERRED"
        return (
            "CONSENSUS"
            if all(entry["disposition"] == "SUPPORT" for entry in ledger)
            else "MIXED"
        )

    @classmethod
    def _validate_chair_report(
        cls,
        result: ParticipantResult,
        *,
        ledger: list[dict[str, Any]],
        target_status: str,
    ) -> ParticipantResult:
        if not result.succeeded or not result.content:
            return result
        expected = cls._required_chair_disposition(ledger, target_status)
        first_line = next(
            (line.strip() for line in result.content.splitlines() if line.strip()), ""
        )
        normalized = re.sub(r"^[\s*#]+", "", first_line.upper())
        normalized = re.sub(r"[\s*]+$", "", normalized)
        match = re.fullmatch(r"DISPOSITION\s*:\s*(CONSENSUS|MIXED|DEFERRED)", normalized)
        actual = match.group(1) if match else "INVALID"
        if actual == expected:
            return result
        return ParticipantResult(
            participant=result.participant,
            content=result.content,
            error=f"Chair disposition mismatch: expected {expected}, received {actual}",
            duration_ms=result.duration_ms,
            metadata={**result.metadata, "required_disposition": expected},
        )

    @classmethod
    def _ledger(
        cls,
        results: Iterable[ParticipantResult],
        pass_number: int,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for position, result in enumerate(results, start=1):
            disposition = cls._disposition(result)
            actionable = disposition in ACTIONABLE_DISPOSITIONS
            entries.append(
                {
                    "item_id": f"P{pass_number}-I{position}",
                    "pass": pass_number,
                    "participant": result.participant,
                    "disposition": disposition,
                    "requires_ruling": actionable,
                    "status": "OPEN" if actionable else "RECORDED",
                }
            )
        return entries

    @staticmethod
    def _notify(callback: ProgressCallback | None, **event: Any) -> None:
        if callback is not None:
            callback(event)

    def _state_path(self, round_id: str) -> Path:
        return self.state_directory / f"{round_id}.json"

    def _save_state(self, state: dict[str, Any]) -> Path:
        path = self._state_path(state["round_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.pending")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return path

    def _load_state(self, round_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f-]{36}", round_id):
            raise ValueError("Invalid round identifier")
        path = self._state_path(round_id)
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"Unknown procedural round: {round_id}") from exc
        expected = [participant.name for participant in self.participants]
        if state.get("participants") != expected:
            raise ValueError("The configured participant list does not match the saved round")
        return state

    def status(self, round_id: str) -> dict[str, Any]:
        state = self._load_state(round_id)
        latest = state["passes"][-1]
        return {
            "round_id": state["round_id"],
            "motion": state["motion"],
            "status": state["status"],
            "chair": state["chair"],
            "participants": state["participants"],
            "review_pass": latest["number"],
            "ledger": latest["ledger"],
        }

    @staticmethod
    def opening_prompt(motion: str) -> str:
        motion = motion.strip()
        if not motion:
            raise ValueError("Motion cannot be empty")
        return (
            "LITTLE OOGWAY ROUNDTABLE — OPENING STATEMENT\n\n"
            f"Motion:\n{motion}\n\n"
            "Give your independent analysis and recommendation. State assumptions, risks, "
            "and missing information. Do not claim consensus or speak for another participant."
        )

    def start(
        self,
        motion: str,
        *,
        chair: Participant | None = None,
        progress: ProgressCallback | None = None,
        round_id: str | None = None,
    ) -> ProceduralRoundResult:
        motion = motion.strip()
        if not motion:
            raise ValueError("Motion cannot be empty")
        chair = chair or self.participants[0]
        if chair not in self.participants:
            raise ValueError("Chair must be one of the configured participants")

        round_id = round_id or str(uuid.uuid4())
        if not re.fullmatch(r"[0-9a-f-]{36}", round_id):
            raise ValueError("Invalid round identifier")
        transcript_path = self.transcript_directory / f"{round_id}.jsonl"
        transcript = JsonlTranscript(transcript_path)
        transcript.write(
            "round_started",
            round_id=round_id,
            mode="resumable_procedure",
            motion=motion,
            chair=chair.name,
            participants=[participant.name for participant in self.participants],
            procedure=["opening", "review", "operator_ruling_if_needed", "review_pass", "chair_disposition"],
        )

        opening_prompt = self.opening_prompt(motion)
        openings: list[ParticipantResult] = []
        for position, participant in enumerate(self.participants, start=1):
            self._notify(progress, phase="opening", participant=participant.name, status="running")
            result = self._call(participant, opening_prompt)
            openings.append(result)
            transcript.write(
                "participant_completed",
                round_id=round_id,
                phase="opening",
                position=position,
                **self._result_dict(result),
            )
            self._notify(progress, phase="opening", participant=participant.name, status="completed" if result.succeeded else "failed")

        reviews, ledger, chair_report, status = self._run_review_pass(
            round_id=round_id,
            motion=motion,
            openings=tuple(openings),
            previous_passes=(),
            ruling=None,
            pass_number=1,
            chair=chair,
            transcript=transcript,
            progress=progress,
        )
        state = {
            "version": 1,
            "round_id": round_id,
            "motion": motion,
            "chair": chair.name,
            "participants": [participant.name for participant in self.participants],
            "status": status,
            "openings": [self._result_dict(result) for result in openings],
            "passes": [{
                "number": 1,
                "operator_ruling": None,
                "reviews": [self._result_dict(result) for result in reviews],
                "ledger": ledger,
                "chair_report": self._result_dict(chair_report),
            }],
        }
        state_path = self._save_state(state)
        transcript.write("procedural_state", round_id=round_id, status=status, state_path=str(state_path))
        return self._to_result(state, transcript_path, state_path)

    def retry_chair(
        self,
        round_id: str,
        *,
        chair: Participant | None = None,
        progress: ProgressCallback | None = None,
    ) -> ProceduralRoundResult:
        """Retry only a failed chair report without repeating participant turns."""
        state = self._load_state(round_id)
        if state["status"] != "awaiting_chair":
            raise ValueError("This procedural round is not awaiting a chair report")
        chair_name = state["chair"]
        chair = chair or next(
            participant for participant in self.participants if participant.name == chair_name
        )
        if chair.name != chair_name:
            raise ValueError("The recovered round must retain its original chair")

        latest = state["passes"][-1]
        openings = tuple(self._result_from_dict(item) for item in state["openings"])
        reviews = [self._result_from_dict(item) for item in latest["reviews"]]
        ledger = latest["ledger"]
        target_status = self._status_from_ledger(ledger)
        chair_prompt = self._chair_prompt(
            motion=state["motion"],
            openings=openings,
            previous_passes=tuple(state["passes"][:-1]),
            ruling=latest["operator_ruling"],
            pass_number=latest["number"],
            chair=chair,
            reviews=reviews,
            ledger=ledger,
            target_status=target_status,
        )
        transcript_path = self.transcript_directory / f"{round_id}.jsonl"
        transcript = JsonlTranscript(transcript_path)
        transcript.write(
            "chair_retry",
            round_id=round_id,
            review_pass=latest["number"],
        )
        self._notify(progress, phase="chair_retry", participant=chair.name, status="running")
        chair_report = self._validate_chair_report(
            self._call(chair, chair_prompt),
            ledger=ledger,
            target_status=target_status,
        )
        status = target_status if chair_report.succeeded else "awaiting_chair"
        transcript.write(
            "chair_report",
            round_id=round_id,
            review_pass=latest["number"],
            procedural_status=status,
            **self._result_dict(chair_report),
        )
        self._notify(
            progress,
            phase="chair_retry",
            participant=chair.name,
            status="completed" if chair_report.succeeded else "failed",
        )
        latest["chair_report"] = self._result_dict(chair_report)
        state["status"] = status
        state_path = self._save_state(state)
        transcript.write(
            "procedural_state", round_id=round_id, status=status, state_path=str(state_path)
        )
        if status == "completed":
            transcript.write(
                "round_completed",
                round_id=round_id,
                mode="resumable_procedure",
                review_passes=latest["number"],
                succeeded=all(result.succeeded for result in (*openings, *reviews, chair_report)),
            )
        return self._to_result(state, transcript_path, state_path)

    def resume(
        self,
        round_id: str,
        ruling: str,
        *,
        chair: Participant | None = None,
        progress: ProgressCallback | None = None,
    ) -> ProceduralRoundResult:
        ruling = ruling.strip()
        if not ruling:
            raise ValueError("A ruling, clarification, or requested fact is required")
        state = self._load_state(round_id)
        if state["status"] == "completed":
            raise ValueError("This procedural round is already complete")
        chair_name = state["chair"]
        chair = chair or next(
            participant for participant in self.participants if participant.name == chair_name
        )
        if chair.name != chair_name:
            raise ValueError("The resumed round must retain its original chair")

        transcript_path = self.transcript_directory / f"{round_id}.jsonl"
        transcript = JsonlTranscript(transcript_path)
        pass_number = len(state["passes"]) + 1
        transcript.write(
            "operator_ruling",
            round_id=round_id,
            before_pass=pass_number,
            content=ruling,
        )
        openings = tuple(self._result_from_dict(item) for item in state["openings"])
        reviews, ledger, chair_report, status = self._run_review_pass(
            round_id=round_id,
            motion=state["motion"],
            openings=openings,
            previous_passes=tuple(state["passes"]),
            ruling=ruling,
            pass_number=pass_number,
            chair=chair,
            transcript=transcript,
            progress=progress,
        )
        state["status"] = status
        state["passes"].append({
            "number": pass_number,
            "operator_ruling": ruling,
            "reviews": [self._result_dict(result) for result in reviews],
            "ledger": ledger,
            "chair_report": self._result_dict(chair_report),
        })
        state_path = self._save_state(state)
        transcript.write("procedural_state", round_id=round_id, status=status, state_path=str(state_path))
        return self._to_result(state, transcript_path, state_path)

    def _run_review_pass(
        self,
        *,
        round_id: str,
        motion: str,
        openings: tuple[ParticipantResult, ...],
        previous_passes: tuple[dict[str, Any], ...],
        ruling: str | None,
        pass_number: int,
        chair: Participant,
        transcript: JsonlTranscript,
        progress: ProgressCallback | None,
    ) -> tuple[list[ParticipantResult], list[dict[str, Any]], ParticipantResult, str]:
        reviews: list[ParticipantResult] = []
        for position, participant in enumerate(self.participants, start=1):
            is_chair = participant is chair
            opening_docket = self._docket(openings, redact_private=not is_chair)
            history_sections: list[str] = []
            for previous in previous_passes:
                previous_reviews = tuple(
                    self._result_from_dict(item) for item in previous["reviews"]
                )
                history_sections.append(
                    f"### Review pass {previous['number']}\n"
                    + self._docket(previous_reviews, redact_private=not is_chair)
                )
            history = "\n\n".join(history_sections) or "[No earlier review pass]"
            ruling_text = ruling or "[No operator ruling yet]"
            review_prompt = (
                f"LITTLE OOGWAY ROUNDTABLE — REVIEW PASS {pass_number}\n\n"
                f"Your identity is {participant.name}.\n\n"
                f"Motion:\n{motion}\n\n"
                f"Opening statements:\n\n{opening_docket}\n\n"
                f"Earlier review record:\n\n{history}\n\n"
                f"Operator ruling or supplied clarification:\n{ruling_text}\n\n"
                "Your first nonempty line must be exactly `Disposition: LABEL`, where LABEL "
                "is SUPPORT, OBJECTION, AMENDMENT, REQUEST FOR CLARIFICATION, POINT OF ORDER, "
                "or PASS. Begin explanation on the next line. An AMENDMENT must "
                "include exact proposed language. A clarification request must identify the "
                "question and who should answer it. A point of order must identify the process "
                "defect and requested remedy. Do not repeat a resolved intervention merely to "
                "preserve it; it remains in the audit record. Preserve substantive dissent."
            )
            self._notify(progress, phase=f"review_{pass_number}", participant=participant.name, status="running")
            result = self._call(participant, review_prompt)
            reviews.append(result)
            transcript.write(
                "participant_completed",
                round_id=round_id,
                phase="review",
                review_pass=pass_number,
                position=position,
                private_material_shared=is_chair,
                **self._result_dict(result),
            )
            self._notify(progress, phase=f"review_{pass_number}", participant=participant.name, status="completed" if result.succeeded else "failed")

        ledger = self._ledger(reviews, pass_number)
        transcript.write(
            "procedural_ledger",
            round_id=round_id,
            review_pass=pass_number,
            entries=ledger,
        )
        target_status = self._status_from_ledger(ledger)
        self._notify(
            progress,
            phase="ledger",
            participant=None,
            status=target_status,
            review_pass=pass_number,
            ledger=ledger,
        )
        chair_prompt = self._chair_prompt(
            motion=motion,
            openings=openings,
            previous_passes=previous_passes,
            ruling=ruling,
            pass_number=pass_number,
            chair=chair,
            reviews=reviews,
            ledger=ledger,
            target_status=target_status,
        )
        self._notify(progress, phase="chair", participant=chair.name, status="running")
        chair_report = self._validate_chair_report(
            self._call(chair, chair_prompt),
            ledger=ledger,
            target_status=target_status,
        )
        status = target_status if chair_report.succeeded else "awaiting_chair"
        transcript.write(
            "chair_report",
            round_id=round_id,
            review_pass=pass_number,
            procedural_status=status,
            **self._result_dict(chair_report),
        )
        self._notify(progress, phase="chair", participant=chair.name, status="completed" if chair_report.succeeded else "failed")
        if status == "completed":
            transcript.write(
                "round_completed",
                round_id=round_id,
                mode="resumable_procedure",
                review_passes=pass_number,
                succeeded=all(result.succeeded for result in (*openings, *reviews, chair_report)),
            )
        return reviews, ledger, chair_report, status

    @staticmethod
    def _status_from_ledger(ledger: list[dict[str, Any]]) -> str:
        return (
            "awaiting_ruling"
            if any(entry["requires_ruling"] for entry in ledger)
            else "completed"
        )

    def _chair_prompt(
        self,
        *,
        motion: str,
        openings: tuple[ParticipantResult, ...],
        previous_passes: tuple[dict[str, Any], ...],
        ruling: str | None,
        pass_number: int,
        chair: Participant,
        reviews: list[ParticipantResult],
        ledger: list[dict[str, Any]],
        target_status: str,
    ) -> str:
        ledger_text = "\n".join(
            f"- {entry['item_id']} {entry['participant']}: {entry['disposition']} ({entry['status']})"
            for entry in ledger
        )
        review_docket = self._docket(reviews)
        required_disposition = self._required_chair_disposition(ledger, target_status)
        if target_status == "awaiting_ruling":
            chair_instruction = (
                "Produce an INTERIM PROCEDURAL REPORT. Your first nonempty line must be "
                "exactly `Disposition: DEFERRED`. "
                "List every open item by its item ID, explain what ruling, answer, or exact "
                "motion text is needed, and preserve all objections. Do not adopt an amendment, "
                "answer a clarification request for someone else, or invent a ruling."
            )
        else:
            chair_instruction = (
                f"Your first nonempty line must be exactly `Disposition: {required_disposition}`. "
                "Then produce FINAL MINUTES under these headings: Controlling motion "
                "or recommendation; Agreements; Objections "
                "and minority views; Resolved procedural history; Unresolved factual questions; "
                "Action items. Do not invent votes, owners, dates, deadlines, tests, or completed "
                f"actions. The Disposition must be {required_disposition}. CONSENSUS is permitted "
                "only when every rostered participant has a recorded SUPPORT disposition; PASS, "
                "OBJECTION, and UNAVAILABLE are not unanimous support. Name every unavailable "
                "seat and preserved objection. Unsupported ownership must be UNASSIGNED."
            )
        chair_openings = self._docket(openings)
        chair_history_sections: list[str] = []
        for previous in previous_passes:
            previous_reviews = tuple(
                self._result_from_dict(item) for item in previous["reviews"]
            )
            chair_history_sections.append(
                f"### Review pass {previous['number']}\n"
                + self._docket(previous_reviews)
            )
        chair_history = "\n\n".join(chair_history_sections) or "[No earlier review pass]"
        ruling_text = ruling or "[No operator ruling yet]"
        return (
            f"LITTLE OOGWAY ROUNDTABLE — CHAIR REPORT AFTER PASS {pass_number}\n\n"
            f"You are {chair.name}, the presiding chair.\n\n"
            f"Motion:\n{motion}\n\n"
            f"Opening statements (full private chair docket):\n\n{chair_openings}\n\n"
            f"Earlier review record (full private chair docket):\n\n{chair_history}\n\n"
            f"Operator ruling or supplied clarification:\n{ruling_text}\n\n"
            f"Latest reviews:\n\n{review_docket}\n\n"
            f"Mechanical procedural ledger:\n{ledger_text}\n\n"
            "The chair docket intentionally contains Little Oogway's local memory-informed "
            "statements. External participants receive a withholding marker instead. Do not "
            "describe private chair material as absent merely because it was withheld externally.\n\n"
            f"{chair_instruction}"
        )

    def _to_result(
        self,
        state: dict[str, Any],
        transcript_path: Path,
        state_path: Path,
    ) -> ProceduralRoundResult:
        return ProceduralRoundResult(
            round_id=state["round_id"],
            motion=state["motion"],
            openings=tuple(self._result_from_dict(item) for item in state["openings"]),
            review_passes=tuple(
                tuple(self._result_from_dict(item) for item in review_pass["reviews"])
                for review_pass in state["passes"]
            ),
            chair_reports=tuple(
                self._result_from_dict(review_pass["chair_report"])
                for review_pass in state["passes"]
            ),
            status=state["status"],
            transcript_path=transcript_path,
            state_path=state_path,
        )
