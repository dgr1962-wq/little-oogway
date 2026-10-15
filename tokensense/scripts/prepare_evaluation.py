#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


def canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare an unscored baseline-versus-adapter evaluation plan")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line]
    if not cases or not all(case.get("enabled") is True for case in cases):
        raise ValueError("evaluation cases must be non-empty and explicitly enabled after review")
    parameters = json.loads(args.parameters.read_text(encoding="utf-8"))
    plan = {
        "evaluation_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "planned",
        "baseline": {"model": args.baseline, "results": None},
        "candidate": {"model": args.baseline, "adapter": args.adapter, "results": None},
        "controls": {
            "parameters": parameters,
            "parameters_sha256": canonical_digest(parameters),
            "cases_sha256": canonical_digest(cases),
            "same_prompts": True,
            "same_retrieval_context": True,
        },
        "cases": cases,
        "summary": None,
        "limitations": ["No evaluation has run; this file is a controlled execution plan only."],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    os.chmod(args.output, 0o600)
    print(json.dumps({"output": str(args.output), "evaluation_id": plan["evaluation_id"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
