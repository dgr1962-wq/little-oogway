#!/usr/bin/env python3
"""Manage inactive adapter metadata. This never changes a model runtime."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(os.environ.get("TOKENSENSE_PRIVATE_ROOT", "/mnt/storage/tokensense")) / "adapters"
POINTER = ROOT / "production-selection.json"
STATUSES = {"experimental", "validated", "production", "archived"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_metadata(adapter_id: str) -> tuple[Path, dict]:
    matches = list(ROOT.glob(f"*/{adapter_id}/metadata.json"))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected exactly one metadata record for {adapter_id!r}")
    return matches[0], json.loads(matches[0].read_text(encoding="utf-8"))


def atomic_write(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def move_status(adapter_id: str, status: str, confirmation: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"unsupported status: {status}")
    source, metadata = load_metadata(adapter_id)
    if status == "production" and confirmation != f"PROMOTE {adapter_id}":
        raise PermissionError(f"production selection requires exact confirmation: PROMOTE {adapter_id}")
    target_dir = ROOT / status / adapter_id
    if target_dir.exists() and target_dir != source.parent:
        raise FileExistsError(target_dir)
    metadata["status"] = status
    metadata.setdefault("status_history", []).append({"status": status, "at": now()})
    atomic_write(source, metadata)
    if target_dir != source.parent:
        target_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.replace(source.parent, target_dir)
    if status == "production":
        atomic_write(POINTER, {
            "adapter_id": adapter_id,
            "selected_at": now(),
            "runtime_integration": False,
            "notice": "Registry selection only; Little Oogway is not configured to load this adapter.",
        })


def rollback(adapter_id: str, confirmation: str) -> None:
    if confirmation != f"ROLL BACK TO {adapter_id}":
        raise PermissionError(f"rollback requires exact confirmation: ROLL BACK TO {adapter_id}")
    _, metadata = load_metadata(adapter_id)
    if metadata.get("status") not in {"validated", "production"}:
        raise ValueError("rollback target must be validated or production metadata")
    atomic_write(POINTER, {
        "adapter_id": adapter_id,
        "selected_at": now(),
        "runtime_integration": False,
        "notice": "Rollback pointer only; runtime integration requires a separate reviewed procedure.",
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show")
    show.add_argument("adapter_id")
    status = sub.add_parser("set-status")
    status.add_argument("adapter_id")
    status.add_argument("status", choices=sorted(STATUSES))
    status.add_argument("--confirmation", default="")
    back = sub.add_parser("rollback")
    back.add_argument("adapter_id")
    back.add_argument("--confirmation", default="")
    args = parser.parse_args()
    if args.command == "show":
        _, metadata = load_metadata(args.adapter_id)
        print(json.dumps(metadata, indent=2))
    elif args.command == "set-status":
        move_status(args.adapter_id, args.status, args.confirmation)
    else:
        rollback(args.adapter_id, args.confirmation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
