from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "atlas_snapshot.py"


class AtlasSnapshotTests(unittest.TestCase):
    def test_distinguishes_behavior_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.jsonl"
            source.write_text(json.dumps({
                "id": "response-1", "experiment_id": "experiment-1", "embedding": [0.1, 0.2]
            }) + "\n", encoding="utf-8")
            subprocess.run([
                sys.executable, str(SCRIPT), "--kind", "experimental-response",
                "--input", str(source), "--snapshot-id", "snapshot-1", "--root", str(root / "atlas"),
            ], check=True, capture_output=True, text=True)
            manifest = json.loads((root / "atlas/snapshot-1/manifest.json").read_text())
            self.assertEqual(manifest["interpretation"], "model_behavior_observation")
            self.assertFalse(manifest["upload_performed"])


if __name__ == "__main__":
    unittest.main()
