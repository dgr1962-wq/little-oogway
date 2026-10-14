from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from roundtable.procedure import ResumableProcedure


class ScriptedParticipant:
    def __init__(
        self,
        name: str,
        responses: list[object],
        kind: str = "test",
        retry_safe: bool = False,
    ) -> None:
        self.name = name
        self.responses = responses
        self.kind = kind
        self.retry_safe = retry_safe
        self.prompts: list[str] = []

    def respond(self, prompt: str):
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError(f"No scripted response remains for {self.name}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response, {"kind": self.kind}


class ProcedureTests(unittest.TestCase):
    def test_retry_safe_local_participant_gets_one_retry(self) -> None:
        participant = ScriptedParticipant(
            "Local",
            [TimeoutError("temporary"), "SUPPORT — recovered"],
            retry_safe=True,
        )
        result = ResumableProcedure._call(participant, "Review")
        self.assertTrue(result.succeeded)
        self.assertEqual(result.metadata["attempt_count"], 2)
        self.assertEqual(len(result.metadata["recovered_errors"]), 1)
        self.assertEqual(len(participant.prompts), 2)

    def test_amendment_keeps_round_open_and_resume_does_not_repeat_openings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chair = ScriptedParticipant(
                "Little Oogway",
                [
                    "Opening from local memory",
                    "SUPPORT — accept the motion",
                    "DEFERRED — P1-I2 requires an operator ruling",
                    "SUPPORT — the ruling resolves the amendment",
                    "CONSENSUS — final minutes",
                ],
                kind="oogway-core",
            )
            peer = ScriptedParticipant(
                "Peer",
                [
                    "Peer opening",
                    "AMENDMENT — replace the final sentence with safer text",
                    "SUPPORT — the operator adopted the safer text",
                ],
            )
            procedure = ResumableProcedure([chair, peer], transcript_directory=directory)

            first = procedure.start("Adopt the test motion", chair=chair)

            self.assertEqual(first.status, "awaiting_ruling")
            self.assertEqual(first.review_passes[0][1].participant, "Peer")
            status = procedure.status(first.round_id)
            self.assertEqual(status["ledger"][1]["item_id"], "P1-I2")
            self.assertTrue(status["ledger"][1]["requires_ruling"])
            self.assertIn("Withheld from external docket", peer.prompts[1])

            resumed = procedure.resume(
                first.round_id,
                "RULING: P1-I2 is adopted with the exact proposed replacement text.",
                chair=chair,
            )

            self.assertEqual(resumed.status, "completed")
            self.assertEqual(len(resumed.openings), 2)
            self.assertEqual(len(resumed.review_passes), 2)
            self.assertEqual(len(chair.prompts), 5)
            self.assertEqual(len(peer.prompts), 3)
            self.assertIn("Operator ruling", peer.prompts[-1])
            self.assertIn("P1-I2 is adopted", peer.prompts[-1])
            self.assertIn("Withheld from external docket", peer.prompts[-1])
            self.assertIn("P1-I2 is adopted", chair.prompts[-1])
            self.assertIn("full private chair docket", chair.prompts[-1])

            events = [
                json.loads(line)
                for line in Path(resumed.transcript_path).read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(sum(event["event"] == "round_started" for event in events), 1)
            self.assertEqual(sum(event["event"] == "operator_ruling" for event in events), 1)
            self.assertEqual(sum(event["event"] == "round_completed" for event in events), 1)

    def test_clarification_and_point_of_order_require_rulings(self) -> None:
        results = [
            type("Result", (), {
                "participant": "one", "content": "REQUEST FOR CLARIFICATION — define modest",
                "error": None, "succeeded": True,
            })(),
            type("Result", (), {
                "participant": "two", "content": "POINT OF ORDER — no controlling text",
                "error": None, "succeeded": True,
            })(),
            type("Result", (), {
                "participant": "three", "content": "OBJECTION — I disagree",
                "error": None, "succeeded": True,
            })(),
        ]
        ledger = ResumableProcedure._ledger(results, 2)
        self.assertTrue(ledger[0]["requires_ruling"])
        self.assertTrue(ledger[1]["requires_ruling"])
        self.assertFalse(ledger[2]["requires_ruling"])

    def test_unclassified_response_cannot_silently_finalize(self) -> None:
        result = type("Result", (), {
            "participant": "one", "content": "I have several thoughts",
            "error": None, "succeeded": True,
        })()
        ledger = ResumableProcedure._ledger([result], 1)
        self.assertEqual(ledger[0]["disposition"], "UNCLASSIFIED")
        self.assertTrue(ledger[0]["requires_ruling"])

    def test_markdown_disposition_label_is_classified(self) -> None:
        result = type("Result", (), {
            "participant": "one",
            "content": "**Disposition: AMENDMENT**\n\nProposed text",
            "error": None,
            "succeeded": True,
        })()
        ledger = ResumableProcedure._ledger([result], 1)
        self.assertEqual(ledger[0]["disposition"], "AMENDMENT")
        self.assertTrue(ledger[0]["requires_ruling"])

    def test_objection_forces_mixed_final_minutes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chair = ScriptedParticipant(
                "Chair",
                ["Opening", "SUPPORT — yes", "MIXED — final minutes"],
            )
            peer = ScriptedParticipant("Peer", ["Opening", "OBJECTION — dissent"])
            result = ResumableProcedure(
                [chair, peer], transcript_directory=directory
            ).start("A contested motion", chair=chair)
            self.assertEqual(result.status, "completed")
            self.assertIn("The Disposition must be MIXED", chair.prompts[-1])
            self.assertIn("CONSENSUS is permitted only", chair.prompts[-1])

    def test_completed_round_cannot_be_resumed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chair = ScriptedParticipant(
                "Chair",
                ["Opening", "SUPPORT — yes", "CONSENSUS — final"],
            )
            procedure = ResumableProcedure([chair], transcript_directory=directory)
            result = procedure.start("A complete motion", chair=chair)
            self.assertEqual(result.status, "completed")
            with self.assertRaisesRegex(ValueError, "already complete"):
                procedure.resume(result.round_id, "Try another pass", chair=chair)

    def test_failed_chair_requires_chair_only_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chair = ScriptedParticipant(
                "Chair",
                [
                    "Opening",
                    "SUPPORT — yes",
                    RuntimeError("chair unavailable"),
                    "CONSENSUS — recovered minutes",
                ],
            )
            peer = ScriptedParticipant("Peer", ["Opening", "SUPPORT — yes"])
            procedure = ResumableProcedure([chair, peer], transcript_directory=directory)
            first = procedure.start("A motion", chair=chair)
            self.assertEqual(first.status, "awaiting_chair")
            self.assertEqual(len(peer.prompts), 2)

            recovered = procedure.retry_chair(first.round_id, chair=chair)
            self.assertEqual(recovered.status, "completed")
            self.assertEqual(len(peer.prompts), 2)
            self.assertEqual(len(chair.prompts), 4)
            events = [
                json.loads(line)
                for line in Path(recovered.transcript_path).read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(sum(event["event"] == "chair_retry" for event in events), 1)

    def test_saved_round_rejects_different_participant_roster(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            chair = ScriptedParticipant(
                "Chair",
                ["Opening", "AMENDMENT — revise", "DEFERRED — ruling needed"],
            )
            result = ResumableProcedure([chair], transcript_directory=directory).start(
                "A motion", chair=chair
            )
            replacement = ScriptedParticipant("Different", [])
            other = ResumableProcedure([replacement], transcript_directory=directory)
            with self.assertRaisesRegex(ValueError, "participant list"):
                other.status(result.round_id)


if __name__ == "__main__":
    unittest.main()
