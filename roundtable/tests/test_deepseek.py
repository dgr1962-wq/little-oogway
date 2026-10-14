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
            {"choices": [], "usage": {
                "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
            }},
        ]
        return iter([*(f"data: {json.dumps(item)}\n".encode() for item in events), b"data: [DONE]\n"])


class DeepSeekTests(unittest.TestCase):
    def test_monitor_tracks_round_progress_and_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            monitor = DeepSeekMonitor(Path(directory))
            monitor.round_begin("round-1", "Test motion")
            monitor.round_progress(
                phase="review_1",
                participant="Claude",
                status="running",
                ledger=[{
                    "item_id": "P1-I1", "participant": "ChatGPT",
                    "disposition": "SUPPORT", "status": "RECORDED",
                }],
            )
            snapshot = monitor.snapshot()
            self.assertEqual(snapshot["phase"], "review_1")
            self.assertEqual(snapshot["participant"], "Claude")
            self.assertEqual(snapshot["ledger"][0]["disposition"], "SUPPORT")
            monitor.round_finish("completed")
            self.assertEqual(monitor.snapshot()["status"], "complete")

    @patch("roundtable.deepseek.urllib.request.urlopen", return_value=FakeResponse())
    def test_streams_visible_content_to_monitor(self, urlopen) -> None:
        with tempfile.TemporaryDirectory() as directory:
            monitor = DeepSeekMonitor(Path(directory))
            monitor.open_window = lambda: None
            participant = DeepSeekParticipant(api_key="test-key", monitor=monitor)

            content, metadata = participant.respond("Question")

            self.assertEqual(content, "DeepSeek")
            self.assertEqual(monitor.snapshot()["deepseek"]["response"], "DeepSeek")
            self.assertEqual(monitor.snapshot()["deepseek"]["status"], "complete")
            self.assertEqual(metadata["model"], "deepseek-flash")
            self.assertEqual(metadata["usage"]["total_tokens"], 120)
            self.assertEqual(
                metadata["estimated_cost_usd"], {"min": 0.000027, "max": 0.000054}
            )
            request = urlopen.call_args.args[0]
            self.assertEqual(request.headers["Authorization"], "Bearer test-key")

    def test_requires_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            participant = DeepSeekParticipant(
                api_key="", monitor=DeepSeekMonitor(Path(directory))
            )
            with self.assertRaisesRegex(RuntimeError, "DEEPSEEK_API_KEY"):
                participant.respond("Question")

    def test_null_prompt_token_details_do_not_discard_usage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            participant = DeepSeekParticipant(
                api_key="test", monitor=DeepSeekMonitor(Path(directory))
            )
            cost = participant._estimated_cost({
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "prompt_tokens_details": None,
            })
            self.assertEqual(cost, {"min": 0.000027, "max": 0.000054})


if __name__ == "__main__":
    unittest.main()
