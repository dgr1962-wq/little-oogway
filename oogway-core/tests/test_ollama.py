import json
import unittest
from unittest.mock import patch

from oogway_core.ollama import OllamaChatModel


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.body).encode()


class OllamaChatModelTests(unittest.TestCase):
    def test_returns_content_and_usage_metadata(self):
        body = {
            "model": "qwen3:8b",
            "message": {"content": "  Patient progress.  "},
            "done_reason": "stop",
            "eval_count": 7,
        }
        with patch("urllib.request.urlopen", return_value=FakeResponse(body)) as opened:
            result = OllamaChatModel().respond("Question", "System")
        self.assertEqual(result.content, "Patient progress.")
        request = opened.call_args.args[0]
        payload = json.loads(request.data)
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["messages"][1]["content"], "Question")
        self.assertEqual(result.metadata["eval_count"], 7)

    def test_rejects_empty_response(self):
        with patch(
            "urllib.request.urlopen",
            return_value=FakeResponse({"message": {"content": " "}}),
        ):
            with self.assertRaisesRegex(RuntimeError, "no response content"):
                OllamaChatModel().respond("Question", "System")


if __name__ == "__main__":
    unittest.main()
