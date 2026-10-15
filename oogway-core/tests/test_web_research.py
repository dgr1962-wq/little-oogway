import json
import unittest
from email.message import Message
from unittest.mock import patch

from oogway_core.web_research import WebResearchRuntime, _public_https_url


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/json"):
        self.body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def read(self, _limit: int = -1) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class WebResearchTests(unittest.TestCase):
    def test_denies_non_https_and_private_network_targets(self):
        with self.assertRaises(PermissionError):
            _public_https_url("http://example.com/")
        with patch("oogway_core.web_research.socket.getaddrinfo") as resolve:
            resolve.return_value = [(2, 1, 6, "", ("127.0.0.1", 443))]
            with self.assertRaises(PermissionError):
                _public_https_url("https://example.test/")

    def test_search_is_bounded_and_labels_results_untrusted(self):
        payload = json.dumps({"results": [{
            "title": "Primary source",
            "url": "https://example.com/report",
            "content": "A result snippet",
            "engines": ["duckduckgo"],
        }]}).encode()
        with patch("oogway_core.web_research.urlopen", return_value=FakeResponse(payload)):
            with patch("oogway_core.web_research._public_https_url", side_effect=lambda value: value):
                result = WebResearchRuntime().search("careful research", limit=100)
        self.assertEqual(result["result_count"], 1)
        self.assertIn("untrusted evidence", result["security_notice"])
        self.assertEqual(result["results"][0]["url"], "https://example.com/report")

    def test_page_reader_strips_script_content(self):
        response = FakeResponse(
            b"<html><title>Example</title><body><p>Useful fact.</p>"
            b"<script>ignore malicious instructions</script></body></html>",
            "text/html; charset=utf-8",
        )
        runtime = WebResearchRuntime()
        with patch("oogway_core.web_research._public_https_url", side_effect=lambda value: value):
            with patch("oogway_core.web_research.build_opener") as builder:
                builder.return_value.open.return_value = response
                result = runtime.read_page("https://example.com/report")
        self.assertIn("Useful fact.", result["content"])
        self.assertNotIn("malicious instructions", result["content"])
        self.assertEqual(result["title"], "Example")


if __name__ == "__main__":
    unittest.main()
