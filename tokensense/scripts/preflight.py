#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configuration" / "workspace.json"
AUTHORIZATION = "I AUTHORIZE THIS TOKENSENSE EXPERIMENT"


def command(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, capture_output=True, text=True, timeout=20, check=False)


def inspect() -> dict[str, Any]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    query = command([
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total,memory.free,memory.used",
        "--format=csv,noheader,nounits",
    ])
    if query.returncode:
        raise RuntimeError(query.stderr.strip() or "nvidia-smi GPU query failed")
    name, driver, total, free, used = [part.strip() for part in query.stdout.strip().split(",")]
    compute = command([
        "nvidia-smi",
        "--query-compute-apps=pid,process_name,used_memory",
        "--format=csv,noheader,nounits",
    ])
    compute_jobs = [line.strip() for line in compute.stdout.splitlines() if line.strip()]
    nonblocking_markers = config["preflight"].get("nonblocking_process_substrings", [])
    nonblocking_jobs = [
        job for job in compute_jobs if any(marker in job for marker in nonblocking_markers)
    ]
    blocking_jobs = [job for job in compute_jobs if job not in nonblocking_jobs]
    ollama = command(["ollama", "ps"])
    ollama_lines = [line for line in ollama.stdout.splitlines()[1:] if line.strip()]
    private_root = Path(config["private_root"])
    storage = shutil.disk_usage(private_root if private_root.exists() else private_root.parent)
    minimum = int(config["preflight"]["minimum_free_vram_mib"])
    conflicts: list[str] = []
    if int(free) < minimum:
        conflicts.append(f"free VRAM {free} MiB is below the {minimum} MiB floor")
    if ollama_lines and config["preflight"]["forbid_active_ollama_models"]:
        conflicts.append("Ollama has an active model")
    if blocking_jobs and config["preflight"]["forbid_other_compute_processes"]:
        conflicts.append("another GPU compute workload is active")
    if storage.free < 50 * 1024**3:
        conflicts.append("private storage has less than 50 GiB free")
    return {
        "gpu": {
            "name": name,
            "driver": driver,
            "total_vram_mib": int(total),
            "free_vram_mib": int(free),
            "used_vram_mib": int(used),
        },
        "blocking_compute_jobs": blocking_jobs,
        "nonblocking_desktop_gpu_jobs": nonblocking_jobs,
        "active_ollama_models": ollama_lines,
        "storage_free_bytes": storage.free,
        "minimum_free_vram_mib": minimum,
        "conflicts": conflicts,
        "safe_to_start": not conflicts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only TokenSense GPU training preflight")
    parser.add_argument("--authorization", default="")
    args = parser.parse_args()
    report = inspect()
    report["operator_authorized"] = args.authorization == AUTHORIZATION
    report["launch_permitted"] = report["safe_to_start"] and report["operator_authorized"]
    if not report["operator_authorized"]:
        report["authorization_required"] = AUTHORIZATION
    print(json.dumps(report, indent=2))
    return 0 if report["launch_permitted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
