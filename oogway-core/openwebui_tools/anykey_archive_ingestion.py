"""
title: AnyKeyCafe Core Archive Ingestion
author: AnyKey Cafe
version: 0.1.0
required_open_webui_version: 0.11.0
description: Admin-only access to Little Oogway Core's durable AnyKeyCafe archive ingestion controller.
"""

from __future__ import annotations

import subprocess
from typing import Any


RUNNER = "/home/darren/Documents/Little-Oogway/oogway-core/scripts/run-archive-controller.sh"


class Tools:
    def ingest_anykeycafe_archive(
        self,
        action: str,
        sample_size: int = 3,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Use Oogway Core to inventory, sample, or fully ingest AnyKeyCafe.

        This private administrative tool accepts exactly three actions:
        `inventory` discovers URLs without changing memory; `sample` queues 1-25
        URLs; and `full` queues the complete published archive. A full run must
        only be selected in response to an explicit administrator request.
        """
        if (__user__ or {}).get("role") != "admin":
            return "Denied: AnyKeyCafe archive ingestion requires an authenticated administrator."

        normalized = action.strip().lower()
        if normalized == "inventory":
            argv = [RUNNER, "--inventory-only", "--sample", str(min(max(sample_size, 1), 25))]
        elif normalized == "sample":
            if sample_size < 1 or sample_size > 25:
                return "Denied: sample_size must be between 1 and 25."
            argv = [RUNNER, "--sample", str(sample_size)]
        elif normalized == "full":
            argv = [RUNNER]
        else:
            return "Denied: action must be inventory, sample, or full."

        try:
            completed = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=240,
            )
        except subprocess.TimeoutExpired:
            return "Oogway Core did not return within four minutes; inspect the durable queue before retrying."
        except OSError as exc:
            return f"Oogway Core could not be started: {type(exc).__name__}: {exc}"

        output = (completed.stdout + completed.stderr).strip()
        lines = output.splitlines()
        if len(lines) > 30:
            output = "\n".join(lines[:5] + [f"... {len(lines) - 15} lines omitted ..."] + lines[-10:])
        status = "completed" if completed.returncode == 0 else f"failed ({completed.returncode})"
        return f"Oogway Core {status}.\n{output}".strip()
