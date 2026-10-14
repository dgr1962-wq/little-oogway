from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from .operator_store import OperatorAction, OperatorStore


MAX_OUTPUT = 64_000
DEFAULT_ROOTS = (Path("/home/darren"), Path("/mnt/storage"))
BLOCKED_PARTS = {
    ".ssh", ".gnupg", "chrome_profiles", ".little-oogway-website",
    "google-chrome", "keyrings",
}
BLOCKED_NAMES = {".env", ".nomic-token", "roundtable.env", "website-guide.env"}
BLOCKED_EXECUTABLES = {
    "sudo", "su", "pkexec", "rm", "rmdir", "shred", "mkfs", "fdisk",
    "parted", "dd", "mount", "umount", "reboot", "shutdown", "poweroff",
    "bash", "sh", "zsh", "fish",
}


def _trim(value: str, limit: int = MAX_OUTPUT) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[:limit] + f"\n... {len(value) - limit} characters omitted ...", True


@dataclass(frozen=True)
class PathPolicy:
    roots: tuple[Path, ...] = DEFAULT_ROOTS

    def resolve(self, value: str, *, allow_missing: bool = False) -> Path:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = Path("/home/darren") / candidate
        resolved = candidate.resolve(strict=not allow_missing)
        if not any(resolved == root or root in resolved.parents for root in self.roots):
            raise PermissionError("path is outside Little Oogway's approved roots")
        if any(part in BLOCKED_PARTS for part in resolved.parts):
            raise PermissionError("path is within a protected credential or browser area")
        if resolved.name in BLOCKED_NAMES:
            raise PermissionError("credential files are protected")
        return resolved


class OperatorRuntime:
    def __init__(self, store: OperatorStore, policy: PathPolicy | None = None):
        self.store = store
        self.policy = policy or PathPolicy()

    def system_status(self) -> dict[str, Any]:
        commands = {
            "uptime": ["uptime", "-p"],
            "memory": ["free", "-h"],
            "disk": ["df", "-h", "/", "/mnt/storage"],
            "gpu": ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu", "--format=csv,noheader"],
        }
        result: dict[str, Any] = {"hostname": os.uname().nodename}
        for name, argv in commands.items():
            try:
                completed = subprocess.run(argv, capture_output=True, text=True, timeout=10)
                output, truncated = _trim((completed.stdout + completed.stderr).strip(), 8000)
                result[name] = {"exit_code": completed.returncode, "output": output, "truncated": truncated}
            except OSError as exc:
                result[name] = {"error": f"{type(exc).__name__}: {exc}"}
        return result

    def list_directory(self, path: str, limit: int = 200) -> dict[str, Any]:
        target = self.policy.resolve(path)
        if not target.is_dir():
            raise ValueError("path is not a directory")
        entries = []
        for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold())):
            if child.name in BLOCKED_NAMES or child.name in BLOCKED_PARTS:
                continue
            stat = child.stat()
            entries.append({
                "name": child.name,
                "kind": "directory" if child.is_dir() else "file",
                "bytes": stat.st_size,
                "modified": stat.st_mtime,
            })
            if len(entries) >= min(max(limit, 1), 500):
                break
        return {"path": str(target), "entries": entries}

    def read_file(self, path: str, max_chars: int = 40_000) -> dict[str, Any]:
        target = self.policy.resolve(path)
        if not target.is_file():
            raise ValueError("path is not a regular file")
        if target.stat().st_size > 2_000_000:
            raise ValueError("file is larger than the direct-read limit")
        raw = target.read_bytes()
        if b"\x00" in raw[:8192]:
            raise ValueError("binary files require a specialized viewer")
        text = raw.decode("utf-8", errors="replace")
        content, truncated = _trim(text, min(max(max_chars, 1), 100_000))
        return {
            "path": str(target),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "content": content,
            "truncated": truncated,
        }

    def search_files(self, root: str, query: str, limit: int = 100) -> dict[str, Any]:
        target = self.policy.resolve(root)
        if not query.strip() or len(query) > 500:
            raise ValueError("query must contain 1-500 characters")
        argv = ["grep", "-RInF", "--binary-files=without-match", "--exclude=.env", "--exclude-dir=.git"]
        for part in BLOCKED_PARTS:
            argv.append(f"--exclude-dir={part}")
        argv.extend(["--", query, str(target)])
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        if completed.returncode not in {0, 1}:
            raise OSError(completed.stderr.strip() or "text search failed")
        result_limit = min(max(limit, 1), 500)
        all_lines = completed.stdout.splitlines()
        lines = all_lines[:result_limit]
        return {
            "root": str(target),
            "query": query,
            "matches": lines,
            "limited": len(all_lines) > result_limit,
        }

    def propose_command(
        self,
        executable: str,
        arguments: Sequence[str],
        cwd: str,
        reason: str,
        requested_by: str = "little-oogway",
    ) -> OperatorAction:
        program = Path(executable).name
        if program in BLOCKED_EXECUTABLES:
            raise PermissionError(f"{program} requires the future privileged broker")
        workdir = self.policy.resolve(cwd)
        if not workdir.is_dir():
            raise ValueError("working directory is not a directory")
        argv = [executable, *[str(item) for item in arguments]]
        if len(argv) > 100 or sum(map(len, argv)) > 20_000:
            raise ValueError("command exceeds the structured argument limit")
        return self.store.propose(
            action_type="command",
            risk_level="yellow",
            arguments={"argv": argv, "cwd": str(workdir), "timeout": 120},
            reason=reason.strip() or "Little Oogway requested a command",
            requested_by=requested_by,
            requested_via="private-open-webui",
        )

    def execute_approved(self, action_id: str) -> OperatorAction:
        action = self.store.get(action_id)
        if action is None:
            raise KeyError("operator action not found")
        if action.status != "approved":
            raise ValueError("operator action is not approved")
        if not self.store.transition(action_id, from_status="approved", to_status="running"):
            raise RuntimeError("operator action was claimed elsewhere")
        try:
            result = self._execute(action)
        except Exception as exc:
            self.store.transition(
                action_id,
                from_status="running",
                to_status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        else:
            self.store.transition(
                action_id,
                from_status="running",
                to_status="complete",
                result=result,
            )
        updated = self.store.get(action_id)
        if updated is None:
            raise RuntimeError("operator action disappeared")
        return updated

    def _execute(self, action: OperatorAction) -> dict[str, Any]:
        if action.action_type != "command":
            raise ValueError(f"unsupported action type {action.action_type}")
        argv = action.arguments.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
            raise ValueError("stored command arguments are invalid")
        if Path(argv[0]).name in BLOCKED_EXECUTABLES:
            raise PermissionError("stored executable is blocked")
        cwd = self.policy.resolve(str(action.arguments.get("cwd", "")))
        timeout = min(max(int(action.arguments.get("timeout", 120)), 1), 900)
        completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        stdout, stdout_truncated = _trim(completed.stdout)
        stderr, stderr_truncated = _trim(completed.stderr)
        return {
            "argv": argv,
            "cwd": str(cwd),
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": stdout_truncated or stderr_truncated,
        }


def action_dict(action: OperatorAction) -> dict[str, Any]:
    return asdict(action)
