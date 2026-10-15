from __future__ import annotations

import json
import unittest
from pathlib import Path


class PreflightConfigurationTests(unittest.TestCase):
    def test_only_explicit_browser_helper_is_nonblocking(self) -> None:
        config = json.loads(
            (Path(__file__).resolve().parents[1] / "configuration/workspace.json").read_text()
        )
        markers = config["preflight"]["nonblocking_process_substrings"]
        self.assertIn("/opt/google/chrome/chrome --type=gpu-process", markers)
        self.assertFalse(any("python" in marker or "ollama" in marker for marker in markers))


if __name__ == "__main__":
    unittest.main()
