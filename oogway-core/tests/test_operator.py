import tempfile
import unittest
from pathlib import Path

from oogway_core.operator import OperatorRuntime, PathPolicy
from oogway_core.operator_api import dashboard
from oogway_core.operator_store import OperatorAction


class FakeStore:
    def __init__(self):
        self.proposals = []

    def propose(self, **values):
        self.proposals.append(values)
        return OperatorAction(
            id="00000000-0000-0000-0000-000000000001",
            action_type=values["action_type"],
            risk_level=values["risk_level"],
            status="pending",
            arguments=values["arguments"],
            reason=values["reason"],
            requested_by=values["requested_by"],
            requested_via=values["requested_via"],
            result={},
            error=None,
            created_at="2026-10-14T00:00:00+00:00",
        )


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = FakeStore()
        self.runtime = OperatorRuntime(self.store, PathPolicy((self.root,)))

    def tearDown(self):
        self.temporary.cleanup()

    def test_reads_bounded_text_and_reports_hash(self):
        path = self.root / "note.txt"
        path.write_text("hello operator", encoding="utf-8")
        result = self.runtime.read_file(str(path))
        self.assertEqual(result["content"], "hello operator")
        self.assertEqual(len(result["sha256"]), 64)

    def test_denies_credentials_and_paths_outside_roots(self):
        secret = self.root / ".env"
        secret.write_text("PASSWORD=nope", encoding="utf-8")
        with self.assertRaises(PermissionError):
            self.runtime.read_file(str(secret))
        with self.assertRaises(PermissionError):
            self.runtime.read_file("/etc/passwd")

    def test_command_is_persisted_not_executed(self):
        action = self.runtime.propose_command(
            "git", ["status", "--short"], str(self.root), "Inspect project state"
        )
        self.assertEqual(action.status, "pending")
        self.assertEqual(self.store.proposals[0]["arguments"]["argv"], ["git", "status", "--short"])

    def test_blocks_shell_and_privilege_entry_points(self):
        for executable in ("sudo", "bash", "rm", "pkexec"):
            with self.subTest(executable=executable):
                with self.assertRaises(PermissionError):
                    self.runtime.propose_command(
                        executable, [], str(self.root), "Should be rejected"
                    )

    def test_privileged_command_is_red_and_requires_allowlist(self):
        action = self.runtime.propose_privileged_command(
            "/usr/bin/systemctl",
            ["status", "oogway-operator.service"],
            str(self.root),
            "Inspect a system service",
        )
        self.assertEqual(action.risk_level, "red")
        self.assertTrue(action.arguments["privileged"])
        self.assertEqual(action.arguments["authentication"], "graphical-policykit")
        with self.assertRaises(PermissionError):
            self.runtime.propose_privileged_command(
                "/usr/bin/python3", ["-c", "print('no')"], str(self.root), "Denied"
            )

    def test_dashboard_escapes_untrusted_arguments(self):
        action = self.runtime.propose_command(
            "printf", ["<script>alert(1)</script>"], str(self.root), "Show output"
        )
        page = dashboard([action.__dict__], "csrf-token").decode()
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)


if __name__ == "__main__":
    unittest.main()
