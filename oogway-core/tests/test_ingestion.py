import tempfile
import unittest
from pathlib import Path

from oogway_core.ingestion import (
    _ReadableHTML,
    _ValidatedRedirectHandler,
    classify_locator,
    validate_url,
)


class IngestionTests(unittest.TestCase):
    def test_classifies_and_canonicalizes_local_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "memory.txt")
            path.write_text("remember this", encoding="utf-8")
            kind, locator = classify_locator(str(path))
        self.assertEqual(kind, "local_file")
        self.assertEqual(locator, str(path.resolve()))

    def test_allows_only_approved_https_hosts(self):
        validate_url("https://anykeycafe.com/little-o/")
        with self.assertRaisesRegex(ValueError, "requires HTTPS"):
            validate_url("http://anykeycafe.com/little-o/")
        with self.assertRaisesRegex(ValueError, "not approved"):
            validate_url("https://example.com/")

    def test_rejects_redirect_before_following_unapproved_host(self):
        handler = _ValidatedRedirectHandler()
        with self.assertRaisesRegex(ValueError, "not approved"):
            handler.redirect_request(
                None, None, 302, "Found", {}, "https://example.com/private"
            )

    def test_extracts_readable_html_without_scripts(self):
        parser = _ReadableHTML()
        parser.feed(
            "<html><head><style>hidden</style></head><body>"
            "<h1>Little Oogway</h1><p>Useful memory.</p>"
            "<script>secret()</script></body></html>"
        )
        text = parser.text()
        self.assertIn("Little Oogway", text)
        self.assertIn("Useful memory.", text)
        self.assertNotIn("hidden", text)
        self.assertNotIn("secret", text)

    def test_prefers_main_content_over_navigation(self):
        parser = _ReadableHTML()
        parser.feed(
            "<nav>unrelated navigation</nav><main><h1>Canonical page</h1><p>"
            + "project knowledge " * 20
            + "</p></main><footer>unrelated footer</footer>"
        )
        text = parser.text()
        self.assertIn("Canonical page", text)
        self.assertNotIn("unrelated navigation", text)
        self.assertNotIn("unrelated footer", text)


if __name__ == "__main__":
    unittest.main()
