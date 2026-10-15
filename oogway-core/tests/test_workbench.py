from __future__ import annotations

import base64
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from oogway_core.operator import PathPolicy
from oogway_core.workbench import (
    ArchiveRuntime,
    DocumentRuntime,
    FileRuntime,
    GitWorkspaceRuntime,
    MediaRuntime,
)


class WorkbenchTests(unittest.TestCase):
    def test_reads_and_converts_markdown_with_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "notes.md"
            source.write_text("# Notes\n\nBounded tools.\n", encoding="utf-8")
            output = root / "output"
            runtime = DocumentRuntime(PathPolicy((root,)))
            with patch("oogway_core.workbench.OUTPUT_ROOT", output):
                read = runtime.read(str(source))
                converted = runtime.convert_to_markdown(str(source))
            self.assertIn("Bounded tools", read["content"])
            result = Path(converted["output"])
            self.assertTrue(result.is_file())
            self.assertIn(read["sha256"], result.read_text(encoding="utf-8"))

    def test_html_reader_removes_executable_content(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "page.html"
            source.write_text(
                "<html><head><title>Safe title</title><script>attack()</script></head>"
                "<body><h1>Visible</h1><p>Useful text.</p></body></html>",
                encoding="utf-8",
            )
            result = DocumentRuntime(PathPolicy((root,))).read(str(source))
            self.assertIn("Useful text", result["content"])
            self.assertNotIn("attack", result["content"])

    def test_ocr_image_is_bounded_and_reports_confidence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "page.png"
            source.write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                )
            )
            runtime = DocumentRuntime(PathPolicy((root,)))
            with patch.object(runtime, "_ocr_image", return_value=("hello page", [0.9, 0.8])):
                result = runtime.ocr(str(source), max_pages=1)
            self.assertEqual(result["content"], "## Page 1\n\nhello page")
            self.assertEqual(result["mean_confidence"], 0.85)

    def test_archive_rejects_path_traversal(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "bad.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("../escape.txt", "no")
            runtime = ArchiveRuntime(PathPolicy((root,)))
            with self.assertRaisesRegex(ValueError, "unsafe archive path"):
                runtime.inspect(str(source))

    def test_archive_extracts_only_into_bounded_output(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "safe.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("folder/readme.txt", "safe")
            runtime = ArchiveRuntime(PathPolicy((root,)))
            output = root / "output"
            with patch("oogway_core.workbench.OUTPUT_ROOT", output):
                result = runtime.extract(str(source))
            self.assertEqual(Path(result["output"]).joinpath("folder/readme.txt").read_text(), "safe")

    def test_duplicate_detection_hashes_only_equal_sizes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.bin").write_bytes(b"same")
            (root / "two.bin").write_bytes(b"same")
            (root / "other.bin").write_bytes(b"different")
            result = FileRuntime(PathPolicy((root,))).duplicates(str(root))
            self.assertEqual(len(result["duplicate_groups"]), 1)
            self.assertEqual(len(result["duplicate_groups"][0]["paths"]), 2)

    def test_capability_inventory_states_security_boundaries(self) -> None:
        with TemporaryDirectory() as directory:
            result = FileRuntime(PathPolicy((Path(directory),))).capabilities()
            self.assertTrue(result["boundaries"]["authenticated_admin_only"])
            self.assertFalse(result["boundaries"]["public_website"])
            self.assertFalse(result["boundaries"]["arbitrary_shell"])

    def test_media_inspection_uses_structured_ffprobe(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "clip.mp3"
            source.write_bytes(b"audio")
            completed = Mock(returncode=0, stdout=json.dumps({"format": {"duration": "1.0"}}))
            with patch("oogway_core.workbench.subprocess.run", return_value=completed):
                result = MediaRuntime(PathPolicy((root,))).inspect(str(source))
            self.assertEqual(result["ffprobe"]["format"]["duration"], "1.0")

    def test_git_tests_fail_closed_for_unregistered_repository(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            runtime = GitWorkspaceRuntime(PathPolicy((root,)))
            with self.assertRaisesRegex(PermissionError, "no bounded test profile"):
                runtime.test(str(root), "all")


if __name__ == "__main__":
    unittest.main()
