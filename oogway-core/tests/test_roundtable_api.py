import unittest

from oogway_core.roundtable_api import latest_user_prompt


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


if __name__ == "__main__":
    unittest.main()
