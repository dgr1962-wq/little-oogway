from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from oogway_core.image_workspace_control import control_service, service_state


class ImageWorkspaceControlTests(unittest.TestCase):
    @patch("oogway_core.image_workspace_control.urlopen")
    @patch("oogway_core.image_workspace_control.subprocess.run")
    def test_service_state_reports_unit_and_api(self, run: Mock, open_url: Mock) -> None:
        run.return_value = Mock(stdout="active\n")
        open_url.return_value.__enter__.return_value.status = 200
        self.assertEqual(
            service_state(),
            {
                "service": "active",
                "api_ready": True,
                "workspace": "stable-diffusion",
            },
        )

    @patch("oogway_core.image_workspace_control.service_state")
    @patch("oogway_core.image_workspace_control.subprocess.run")
    def test_control_service_allows_only_fixed_actions(self, run: Mock, state: Mock) -> None:
        run.return_value = Mock(returncode=0, stderr="")
        state.return_value = {"service": "active", "api_ready": True}
        result = control_service("start")
        self.assertTrue(result["accepted"])
        run.assert_called_once_with(
            ["systemctl", "--user", "start", "stable-diffusion.service"],
            capture_output=True,
            check=False,
            text=True,
            timeout=45,
        )

    def test_control_service_rejects_arbitrary_commands(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported"):
            control_service("shell")
