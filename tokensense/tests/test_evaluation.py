from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_evaluation.py"


class EvaluationHarnessTests(unittest.TestCase):
    def test_plan_preserves_identical_controls_and_no_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / "cases.jsonl"
            cases.write_text(json.dumps({
                "case_id": "synthetic-1", "dimension": "factual_accuracy",
                "prompt": "synthetic", "retrieval_context": [], "scoring_criteria": "exact",
                "enabled": True,
            }) + "\n", encoding="utf-8")
            parameters = root / "parameters.json"
            parameters.write_text(json.dumps({"temperature": 0}), encoding="utf-8")
            output = root / "plan.json"
            subprocess.run([
                sys.executable, str(SCRIPT), "--cases", str(cases),
                "--baseline", "base", "--adapter", "candidate",
                "--parameters", str(parameters), "--output", str(output),
            ], check=True, capture_output=True, text=True)
            plan = json.loads(output.read_text())
            self.assertTrue(plan["controls"]["same_prompts"])
            self.assertTrue(plan["controls"]["same_retrieval_context"])
            self.assertIsNone(plan["baseline"]["results"])
            self.assertIsNone(plan["candidate"]["results"])
            self.assertIsNone(plan["summary"])


if __name__ == "__main__":
    unittest.main()
