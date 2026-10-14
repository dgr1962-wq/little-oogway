import tempfile
import unittest
from pathlib import Path

from oogway_core.memory import chunk_text, load_transcript, redact_secrets


class MemoryTextTests(unittest.TestCase):
    def test_chunks_cover_text_with_bounded_overlap(self):
        text = "\n\n".join(f"Paragraph {number} " + "x" * 140 for number in range(8))
        chunks = chunk_text(text, max_chars=300, overlap=40)
        self.assertGreater(len(chunks), 1)
        self.assertEqual([chunk.ordinal for chunk in chunks], list(range(len(chunks))))
        self.assertTrue(all(0 < len(chunk.content) <= 300 for chunk in chunks))
        self.assertTrue(all(a.char_start < b.char_start for a, b in zip(chunks, chunks[1:])))

    def test_redacts_common_credentials_without_removing_labels(self):
        result = redact_secrets(
            "api_key = very-secret-value\nGitHub ghp_1234567890123456789012345"
        )
        self.assertNotIn("very-secret-value", result.content)
        self.assertNotIn("ghp_1234567890123456789012345", result.content)
        self.assertIn("api_key = [REDACTED:assigned_secret]", result.content)
        self.assertEqual(result.counts["assigned_secret"], 1)
        self.assertEqual(result.counts["github_token"], 1)

    def test_load_transcript_strips_bom_and_hashes_original_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "source.txt")
            path.write_bytes(b"\xef\xbb\xbfhello\r\nworld")
            text, digest, byte_count = load_transcript(path)
        self.assertEqual(text, "hello\nworld")
        self.assertEqual(len(digest), 64)
        self.assertEqual(byte_count, 15)


if __name__ == "__main__":
    unittest.main()
