from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from roundtable.deepseek import DeepSeekMonitor, DeepSeekParticipant


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        events = [
            {"choices": [{"delta": {"content": "Deep"}}]},
            {"choices": [{"delta": {"reasoning_content": "private"}}]},
            {"choices": [{"delta": {"content": "Seek"}}]},
        ]
        return iter([*(f"data: {json.dumps(item)}\n".encode() for item in events), b"data: [DONE]\n"])


class DeepSeekTests(unittest.TestCase):
    @patch("roundtable.deepseek.urllib.request.urlopen", return_value=FakeResponse())
    def test_streams_visible_content_to_monitor(self, urlopen) -> None:
        with tempfile.TemporaryDirectory() as directory:
            monitor = DeepSeekMonitor(Path(directory))
            monitor.open_window = lambda: None
            participant = DeepSeekParticipant(api_key="test-key", monitor=monitor)

            content, metadata = participant.respond("Question")

            self.assertEqual(content, "DeepSeek")
            self.assertEqual(monitor.snapshot()["response"], "DeepSeek")
            self.assertEqual(monitor.snapshot()["status"], "complete")
            self.assertEqual(metadata["model"], "deepseek-flash")
            request = urlopen.call_args.args[0]
            self.assertEqual(request.headers["Authorization"], "Bearer test-key")

    def test_requires_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            participant = DeepSeekParticipant(
                api_key="", monitor=DeepSeekMonitor(Path(directory))
            )
            with self.assertRaisesRegex(RuntimeError, "DEEPSEEK_API_KEY"):
                participant.respond("Question")


if __name__ == "__main__":
    unittest.main()
