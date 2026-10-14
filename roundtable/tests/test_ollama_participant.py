from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from roundtable.participants import OllamaParticipant


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(
            {
                "model": "qwen3:8b",
                "message": {"role": "assistant", "content": "A local answer."},
                "done_reason": "stop",
                "prompt_eval_count": 42,
                "eval_count": 4,
                "total_duration": 123,
            }
        ).encode("utf-8")


class OllamaParticipantTests(unittest.TestCase):
    @patch("roundtable.participants.urllib.request.urlopen", return_value=FakeResponse())
    def test_parses_ollama_response(self, urlopen) -> None:
        participant = OllamaParticipant()

        content, metadata = participant.respond("Question")

        self.assertEqual(content, "A local answer.")
        self.assertEqual(metadata["model"], "qwen3:8b")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["messages"][-1]["content"], "Question")
        self.assertFalse(payload["stream"])


if __name__ == "__main__":
    unittest.main()
