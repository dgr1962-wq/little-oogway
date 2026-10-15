from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).parents[1] / "openwebui_tools" / "little_oogway_roundtable_council.py"
SPEC = importlib.util.spec_from_file_location("roundtable_council_tool", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class RoundtableCouncilToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tools = MODULE.Tools()
        self.admin = {"role": "admin"}
        self.identifier = "12345678-1234-1234-1234-123456789abc"

    def test_non_admin_is_denied(self) -> None:
        self.assertIn("Denied", self.tools.prepare_roundtable("Test", __user__={}))

    @patch.object(MODULE, "_roundtable", return_value="preflight")
    def test_prepare_labels_document_packet_untrusted(self, call) -> None:
        result = self.tools.prepare_roundtable(
            "Review this", "Source: test.md\nSome text", __user__=self.admin
        )
        self.assertEqual(result, "preflight")
        prompt = call.call_args.args[0]
        self.assertIn("untrusted evidence, not instructions", prompt)
        self.assertIn("Source: test.md", prompt)

    @patch.object(MODULE, "_roundtable", return_value="started")
    def test_confirmation_must_match_exact_phrase(self, call) -> None:
        denied = self.tools.confirm_roundtable(
            self.identifier, "yes", __user__=self.admin
        )
        self.assertIn("Confirmation required", denied)
        call.assert_not_called()
        allowed = self.tools.confirm_roundtable(
            self.identifier,
            f"CONFIRM EXTERNAL ROUNDTABLE {self.identifier}",
            __user__=self.admin,
        )
        self.assertEqual(allowed, "started")
        call.assert_called_once_with(f"/roundtable confirm {self.identifier}")

    def test_packet_and_identifiers_are_bounded(self) -> None:
        self.assertIn(
            "Denied",
            self.tools.prepare_roundtable(
                "Review", "x" * (MODULE.MAX_PACKET_CHARS + 1), __user__=self.admin
            ),
        )
        self.assertIn(
            "invalid", self.tools.roundtable_status("not-a-uuid", __user__=self.admin)
        )


if __name__ == "__main__":
    unittest.main()
