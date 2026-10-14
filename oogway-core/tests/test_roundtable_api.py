import tempfile
import unittest
from pathlib import Path

from oogway_core.roundtable_api import (
    RoundtableRuntime,
    latest_user_prompt,
    parse_roundtable_command,
)


class RoundtableApiTests(unittest.TestCase):
    def test_uses_latest_user_message(self):
        self.assertEqual(
            latest_user_prompt([
                {"role": "user", "content": "old"},
                {"role": "assistant", "content": "reply"},
                {"role": "user", "content": "new"},
            ]),
            "new",
        )

    def test_rejects_missing_user_message(self):
        with self.assertRaisesRegex(ValueError, "No nonempty user"):
            latest_user_prompt([{"role": "system", "content": "hello"}])

    def test_parses_confirm_command(self):
        round_id = "11111111-2222-3333-4444-555555555555"
        self.assertEqual(
            parse_roundtable_command(f"/roundtable confirm {round_id}"),
            ("confirm", round_id, ""),
        )

    def test_parses_multiline_resume_command(self):
        round_id = "11111111-2222-3333-4444-555555555555"
        self.assertEqual(
            parse_roundtable_command(
                f"/roundtable resume {round_id}\nRULING: adopt P1-I2"
            ),
            ("resume", round_id, "RULING: adopt P1-I2"),
        )

    def test_ordinary_prompt_is_not_a_command(self):
        self.assertIsNone(parse_roundtable_command("Please discuss the next motion"))

    def test_parses_chair_and_recovery_commands(self):
        identifier = "11111111-2222-3333-4444-555555555555"
        self.assertEqual(
            parse_roundtable_command(f"/roundtable chair {identifier}"),
            ("chair", identifier, ""),
        )
        self.assertEqual(
            parse_roundtable_command(f"/roundtable recover {identifier}"),
            ("recover", identifier, ""),
        )

    def test_active_preflight_lease_cannot_be_recovered_by_other_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RoundtableRuntime()
            runtime.transcript_directory = Path(directory)
            runtime.preflight_directory = Path(directory, "preflight")
            _, created = runtime._create_preflight("Test recovery")
            old_id = created["preflight_id"]
            record = runtime._load_preflight(old_id)
            record.update({
                "status": "running",
                "runtime_instance": "dead-runtime",
                "lease_expires_at": 9999999999,
            })
            runtime._write_json(runtime._preflight_path(old_id), record)

            with self.assertRaisesRegex(ValueError, "active execution lease"):
                runtime._recover_preflight(old_id)

    def test_expired_preflight_recovers_to_fresh_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RoundtableRuntime()
            runtime.transcript_directory = Path(directory)
            runtime.preflight_directory = Path(directory, "preflight")
            _, created = runtime._create_preflight("Test recovery")
            old_id = created["preflight_id"]
            record = runtime._load_preflight(old_id)
            record.update({
                "status": "running",
                "runtime_instance": "dead-runtime",
                "lease_expires_at": 0,
            })
            runtime._write_json(runtime._preflight_path(old_id), record)

            content, recovered = runtime._recover_preflight(old_id)

            self.assertNotEqual(recovered["preflight_id"], old_id)
            self.assertEqual(recovered["recovered_from"], old_id)
            self.assertIn("safely replaces interrupted preflight", content)
            self.assertEqual(runtime._load_preflight(old_id)["status"], "recovered")
            self.assertEqual(
                runtime._load_preflight(recovered["preflight_id"])["status"], "pending"
            )


if __name__ == "__main__":
    unittest.main()
