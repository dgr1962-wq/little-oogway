import unittest

from oogway_core.cli import development_dsn


class DevelopmentDsnTests(unittest.TestCase):
    def test_builds_only_the_isolated_development_target(self):
        dsn = development_dsn({"TOKENSPACE_PASSWORD": "space and/slash"})
        self.assertEqual(
            dsn,
            "postgresql://tokenspace_dev:space%20and%2Fslash@127.0.0.1:55432/tokenspace_v2_dev",
        )

    def test_rejects_a_different_database_target(self):
        with self.assertRaisesRegex(ValueError, "only targets"):
            development_dsn(
                {
                    "TOKENSPACE_PASSWORD": "secret",
                    "TOKENSPACE_DATABASE": "tokenspace",
                }
            )

    def test_requires_password(self):
        with self.assertRaisesRegex(ValueError, "TOKENSPACE_PASSWORD"):
            development_dsn({})


if __name__ == "__main__":
    unittest.main()
