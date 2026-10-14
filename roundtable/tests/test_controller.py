from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from roundtable.controller import RoundtableController
from roundtable.participants import MockParticipant


class FailingParticipant:
    name = "failing-participant"

    def respond(self, prompt: str):
        raise RuntimeError("deliberate failure")


class TrackingParticipant:
    def __init__(self, name: str, kind: str = "test") -> None:
        self.name = name
        self.kind = kind
        self.prompts: list[str] = []

    def respond(self, prompt: str):
        self.prompts.append(prompt)
        phase = ("opening" if "OPENING STATEMENT" in prompt else
                 "review" if "REVIEW OF THE DOCKET" in prompt else "chair")
        return f"{self.name} {phase}", {"phase": phase, "kind": self.kind}


class ControllerTests(unittest.TestCase):
    def test_records_ordered_round(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = RoundtableController(
                [
                    MockParticipant(name="first", prefix="First saw"),
                    MockParticipant(name="second", prefix="Second saw"),
                ],
                transcript_directory=directory,
            )

            result = controller.run_round("What is next?")

            self.assertTrue(result.succeeded)
            self.assertEqual([item.participant for item in result.participants], ["first", "second"])
            events = [json.loads(line) for line in Path(result.transcript_path).read_text().splitlines()]
            self.assertEqual(
                [event["event"] for event in events],
                ["round_started", "participant_completed", "participant_completed", "round_completed"],
            )
            self.assertEqual(events[0]["participants"], ["first", "second"])
            self.assertTrue(events[-1]["succeeded"])

    def test_isolates_participant_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = RoundtableController(
                [FailingParticipant(), MockParticipant(name="survivor")],
                transcript_directory=directory,
            )

            result = controller.run_round("Continue after a failure")

            self.assertFalse(result.succeeded)
            self.assertIn("deliberate failure", result.participants[0].error or "")
            self.assertTrue(result.participants[1].succeeded)

    def test_rejects_empty_prompt(self) -> None:
        controller = RoundtableController([MockParticipant()])
        with self.assertRaises(ValueError):
            controller.run_round("   ")

    def test_deliberation_shares_docket_and_records_chair_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chair = TrackingParticipant("Little Oogway", kind="oogway-core")
            peer = TrackingParticipant("Peer")
            controller = RoundtableController([chair, peer], transcript_directory=directory)

            result = controller.run_deliberation("Choose a safe next step", chair=chair)

            self.assertTrue(result.succeeded)
            self.assertEqual(len(result.participants), 2)
            self.assertEqual(len(result.reviews), 2)
            self.assertEqual(result.chair.participant, "Little Oogway")
            self.assertEqual(len(chair.prompts), 3)
            self.assertEqual(len(peer.prompts), 2)
            self.assertIn("Your identity in this proceeding is Peer", peer.prompts[1])
            self.assertNotIn("Little Oogway opening", peer.prompts[1])
            self.assertIn("Withheld from external docket", peer.prompts[1])
            self.assertIn("Peer opening", peer.prompts[1])
            self.assertIn("Little Oogway opening", chair.prompts[1])
            self.assertIn("Little Oogway review", chair.prompts[2])
            self.assertIn("Peer review", chair.prompts[2])
            self.assertIn("Little Oogway: UNCLASSIFIED", chair.prompts[2])
            self.assertIn("Peer: UNCLASSIFIED", chair.prompts[2])
            self.assertEqual(
                result.chair.metadata["procedural_ledger"],
                [
                    {"participant": "Little Oogway", "disposition": "UNCLASSIFIED"},
                    {"participant": "Peer", "disposition": "UNCLASSIFIED"},
                ],
            )

            events = [json.loads(line) for line in Path(result.transcript_path).read_text().splitlines()]
            self.assertEqual(
                [event["event"] for event in events],
                [
                    "round_started",
                    "participant_completed", "participant_completed",
                    "participant_completed", "participant_completed",
                    "procedural_ledger",
                    "chair_disposition", "round_completed",
                ],
            )
            self.assertEqual(events[1]["phase"], "opening")
            self.assertEqual(events[3]["phase"], "review")
            self.assertEqual(events[-1]["mode"], "deliberation")

    def test_deliberation_rejects_empty_prompt(self) -> None:
        controller = RoundtableController([MockParticipant()])
        with self.assertRaises(ValueError):
            controller.run_deliberation("   ")

    def test_procedural_ledger_classifies_markdown_dispositions(self) -> None:
        from roundtable.types import ParticipantResult

        results = [
            ParticipantResult("one", "**AMENDMENT** — change it", None, 1),
            ParticipantResult("two", "SUPPORT — agreed", None, 1),
            ParticipantResult("three", None, "offline", 1),
        ]
        self.assertEqual(
            RoundtableController._procedural_ledger(results),
            [
                {"participant": "one", "disposition": "AMENDMENT"},
                {"participant": "two", "disposition": "SUPPORT"},
                {"participant": "three", "disposition": "UNAVAILABLE"},
            ],
        )

    def test_deliberation_completes_when_nonchair_participant_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chair = TrackingParticipant("Little Oogway", kind="oogway-core")
            controller = RoundtableController(
                [chair, FailingParticipant()],
                transcript_directory=directory,
            )

            result = controller.run_deliberation("Continue without an unavailable peer", chair=chair)

            self.assertFalse(result.succeeded)
            self.assertTrue(result.participants[0].succeeded)
            self.assertFalse(result.participants[1].succeeded)
            self.assertTrue(result.reviews[0].succeeded)
            self.assertFalse(result.reviews[1].succeeded)
            self.assertTrue(result.chair.succeeded)
            self.assertIn("Unavailable: RuntimeError: deliberate failure", chair.prompts[-1])
            self.assertEqual(
                result.chair.metadata["procedural_ledger"][1],
                {"participant": "failing-participant", "disposition": "UNAVAILABLE"},
            )


if __name__ == "__main__":
    unittest.main()
