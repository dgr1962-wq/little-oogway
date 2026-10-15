from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from oogway_core.image_workspace_control import (
    build_video_graph,
    control_service,
    service_state,
    validate_video_request,
)


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
    def test_control_service_allows_only_fixed_actions(
        self, run: Mock, state: Mock
    ) -> None:
        run.side_effect = [Mock(stdout="inactive\n"), Mock(returncode=0, stderr="")]
        state.return_value = {"service": "active", "api_ready": True}
        result = control_service("start")
        self.assertTrue(result["accepted"])
        self.assertEqual(run.call_count, 2)
        run.assert_called_with(
            ["systemctl", "--user", "start", "stable-diffusion.service"],
            capture_output=True,
            check=False,
            text=True,
            timeout=45,
        )

    def test_control_service_rejects_arbitrary_commands(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported"):
            control_service("shell")

    @patch("oogway_core.image_workspace_control.urlopen")
    @patch("oogway_core.image_workspace_control.subprocess.run")
    def test_video_state_uses_only_fixed_video_unit(
        self, run: Mock, open_url: Mock
    ) -> None:
        run.return_value = Mock(stdout="active\n")
        open_url.return_value.__enter__.return_value.status = 200
        self.assertEqual(
            service_state("video"),
            {"service": "active", "api_ready": True, "workspace": "wan-video-generation"},
        )
        run.assert_called_once_with(
            ["systemctl", "--user", "is-active", "main-desk-video-generation.service"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )

    def test_rejects_unknown_workspace(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported workspace"):
            service_state("../../shell")

    @patch("oogway_core.image_workspace_control.subprocess.run")
    def test_refuses_simultaneous_gpu_workspaces(self, run: Mock) -> None:
        run.return_value = Mock(stdout="active\n")
        with self.assertRaisesRegex(RuntimeError, "stop it before starting"):
            control_service("start", "video")
        run.assert_called_once()

    def test_video_request_is_bounded_and_graph_is_fixed(self) -> None:
        settings = validate_video_request({"prompt": "A small turtle waves."})
        self.assertEqual(settings["width"], 640)
        self.assertEqual(settings["frames"], 49)
        graph = build_video_graph(settings)
        self.assertEqual(graph["1"]["class_type"], "UNETLoader")
        self.assertEqual(graph["11"]["class_type"], "SaveVideo")
        self.assertEqual(graph["11"]["inputs"]["filename_prefix"], "Little-Oogway/video")

    def test_video_request_rejects_arbitrary_nodes_and_unsafe_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            validate_video_request({"prompt": "hello", "nodes": {"shell": "oops"}})
        with self.assertRaisesRegex(ValueError, "safe 12 GB"):
            validate_video_request({"prompt": "hello", "width": 1024, "height": 1024})
        with self.assertRaisesRegex(ValueError, "4n\\+1"):
            validate_video_request({"prompt": "hello", "frames": 50})
