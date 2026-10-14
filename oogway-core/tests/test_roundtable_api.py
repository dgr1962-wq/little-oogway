import unittest

from oogway_core.roundtable_api import latest_user_prompt, parse_roundtable_command


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


if __name__ == "__main__":
    unittest.main()
