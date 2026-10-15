#!/usr/bin/env python3
"""Create immutable private Atlas-ready snapshots. This script never uploads."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["approved-memory", "experimental-response"], required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--root", type=Path, default=Path("/mnt/storage/tokensense/atlas"))
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line]
    if not rows:
        raise ValueError("snapshot input is empty")
    dimensions = {len(row.get("embedding", [])) for row in rows}
    if len(dimensions) != 1 or 0 in dimensions:
        raise ValueError("all rows must have same-size non-empty embeddings")
    if args.kind == "approved-memory" and not all(row.get("review_status") == "approved" for row in rows):
        raise PermissionError("memory snapshots require review_status=approved for every row")
    if args.kind == "experimental-response" and not all(row.get("experiment_id") for row in rows):
        raise ValueError("response snapshots require experiment_id on every row")
    target = args.root / args.snapshot_id
    target.mkdir(parents=True, exist_ok=False, mode=0o700)
    data = target / "embeddings.jsonl"
    data.write_bytes(args.input.read_bytes())
    os.chmod(data, 0o600)
    manifest = {
        "schema_version": 1,
        "snapshot_id": args.snapshot_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": args.kind,
        "interpretation": "stored_knowledge" if args.kind == "approved-memory" else "model_behavior_observation",
        "records": len(rows),
        "dimensions": dimensions.pop(),
        "data_sha256": digest(data),
        "upload_performed": False,
        "existing_atlas_datasets_modified": False,
    }
    metadata = target / "manifest.json"
    metadata.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.chmod(metadata, 0o600)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
