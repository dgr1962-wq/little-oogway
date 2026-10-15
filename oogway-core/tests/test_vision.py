import json
import unittest
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from oogway_core.models import ModelResponse
from oogway_core.operator import PathPolicy
from oogway_core.vision import VisionRuntime


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/json"):
        self.body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def read(self, limit: int = -1) -> bytes:
        return self.body if limit < 0 else self.body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class VisionTests(unittest.TestCase):
    def test_local_webp_is_normalized_before_vision_request(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.webp"
            source.write_bytes(b"webp-source")
            runtime = VisionRuntime(policy=PathPolicy((Path(directory),)))

            def normalized(_raw):
                return b"jpeg-normalized"

            reply = json.dumps({"message": {"content": "a workshop"}}).encode()
            with patch.object(runtime, "_normalized_jpeg", side_effect=normalized):
                with patch("oogway_core.vision.urllib.request.urlopen", return_value=FakeResponse(reply)) as opened:
                    result = runtime.inspect(str(source))

            payload = json.loads(opened.call_args.args[0].data)
            self.assertEqual(payload["messages"][0]["images"], ["anBlZy1ub3JtYWxpemVk"])
            self.assertEqual(result["normalized_format"], "image/jpeg")
            self.assertEqual(result["observation"], "a workshop")

    def test_variation_uses_observation_then_text_prompt_model(self):
        model = Mock()
        model.respond.return_value = ModelResponse(
            content=json.dumps({"sdxl_prompt": "new scene", "negative_prompt": "bad text"}),
            metadata={"model": "qwen3:8b"},
        )
        runtime = VisionRuntime(text_model=model)
        with patch.object(runtime, "inspect", return_value={"observation": "verified scene"}):
            result = runtime.variation_prompt("ignored", "add a small turtle")
        self.assertIn("verified scene", model.respond.call_args.kwargs["prompt"])
        self.assertEqual(result["sdxl_prompt"], "new scene")
        self.assertEqual(result["negative_prompt"], "bad text")


if __name__ == "__main__":
    unittest.main()
