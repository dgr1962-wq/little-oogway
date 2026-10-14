import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def list(self, **_values):
        return []


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
        token = self.root / "operator.token"
        token.write_text("secret", encoding="utf-8")
        with self.assertRaises(PermissionError):
            self.runtime.read_file(str(token))

    def test_search_does_not_follow_symlinks_outside_root(self):
        with tempfile.TemporaryDirectory() as outside:
            Path(outside, "secret.txt").write_text("needle-secret", encoding="utf-8")
            (self.root / "escape").symlink_to(outside, target_is_directory=True)
            result = self.runtime.search_files(str(self.root), "needle-secret")
        self.assertEqual(result["matches"], [])

    def test_command_is_persisted_not_executed(self):
        destination = self.root / "created-later.txt"
        action = self.runtime.propose_command(
            "/usr/bin/touch", [str(destination)], str(self.root), "Create a file"
        )
        self.assertEqual(action.status, "pending")
        self.assertEqual(
            self.store.proposals[0]["arguments"]["argv"],
            ["/usr/bin/touch", str(destination)],
        )

    def test_rejects_every_command_outside_path_aware_allowlist(self):
        for executable in (
            "/usr/bin/python3", "/usr/bin/env", "/usr/bin/find", "/usr/bin/git",
            "/usr/bin/bash", "/usr/bin/rm",
        ):
            with self.subTest(executable=executable):
                with self.assertRaises(PermissionError):
                    self.runtime.propose_command(
                        executable, [], str(self.root), "Should be rejected"
                    )

    def test_privileged_commands_fail_closed_without_argument_profile(self):
        with self.assertRaises(PermissionError):
            self.runtime.propose_privileged_command(
                "/usr/bin/systemctl", ["status", "oogway-operator.service"],
                str(self.root), "Denied until profiled"
            )

    def test_command_arguments_cannot_read_outside_policy(self):
        with self.assertRaises(PermissionError):
            self.runtime.propose_command(
                "/usr/bin/cp", ["/etc/passwd", str(self.root / "copy")],
                str(self.root), "Attempt escape"
            )

    def test_execution_uses_minimal_environment(self):
        destination = self.root / "created.txt"
        action = self.runtime.propose_command(
            "/usr/bin/touch", [str(destination)], str(self.root), "Create file"
        )
        with patch("oogway_core.operator.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = ""
            run.return_value.stderr = ""
            self.runtime._execute(action)
        environment = run.call_args.kwargs["env"]
        self.assertNotIn("TOKENSPACE_PASSWORD", environment)
        self.assertNotIn("POSTGRES_PASSWORD", environment)

    def test_dashboard_escapes_untrusted_arguments(self):
        destination = self.root / "<script>alert(1).txt"
        action = self.runtime.propose_command(
            "/usr/bin/touch", [str(destination)], str(self.root), "Show output"
        )
        page = dashboard([action.__dict__], "csrf-token").decode()
        self.assertNotIn("<script>alert(1).txt", page)
        self.assertIn("&lt;script&gt;alert(1).txt", page)


if __name__ == "__main__":
    unittest.main()
