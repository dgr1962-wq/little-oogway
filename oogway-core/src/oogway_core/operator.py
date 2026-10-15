from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from .operator_store import OperatorAction, OperatorStore


MAX_OUTPUT = 64_000
MAX_PENDING_ACTIONS = 20
DEFAULT_ROOTS = (Path("/home/darren"), Path("/mnt/storage"))
BLOCKED_PARTS = {
    ".ssh", ".gnupg", "chrome_profiles", ".little-oogway-website",
    "google-chrome", "keyrings",
}
BLOCKED_NAMES = {
    ".env", ".nomic-token", "operator.token", "roundtable.env", "website-guide.env"
}


def blocked_name(name: str) -> bool:
    return name in BLOCKED_NAMES or name.startswith(".env.")


ALLOWED_COMMANDS = {
    "/usr/bin/cp",
    "/usr/bin/mkdir",
    "/usr/bin/mv",
    "/usr/bin/touch",
}

# Privileged operations require operation-specific argument profiles.  Keeping
# this empty is intentional: allowing a powerful executable such as apt,
# systemctl, cp, or chmod with arbitrary arguments is equivalent to allowing a
# root shell even when PolicyKit still asks a human for a password.
PRIVILEGED_COMMANDS: frozenset[str] = frozenset()
MINIMAL_COMMAND_ENV = {
    "HOME": "/home/darren",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": "/usr/bin:/bin",
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
        if blocked_name(resolved.name):
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
            if blocked_name(child.name) or child.name in BLOCKED_PARTS:
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
        argv = ["grep", "-rInF", "--binary-files=without-match", "--exclude-dir=.git"]
        for name in sorted(BLOCKED_NAMES):
            argv.append(f"--exclude={name}")
        argv.append("--exclude=.env*")
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

    def _enforce_pending_limit(self) -> None:
        if len(self.store.list(status="pending", limit=MAX_PENDING_ACTIONS + 1)) >= MAX_PENDING_ACTIONS:
            raise RuntimeError(
                "the operator queue already has the maximum number of pending actions"
            )

    def _path_argument(self, value: str, *, allow_missing: bool = False) -> str:
        if not value or value.startswith("-"):
            raise PermissionError("command path arguments must be explicit paths")
        return str(self.policy.resolve(value, allow_missing=allow_missing))

    def _validated_command(
        self, executable: str, arguments: Sequence[str]
    ) -> tuple[str, list[str]]:
        try:
            resolved = str(Path(executable).resolve(strict=True))
        except (OSError, RuntimeError) as exc:
            raise PermissionError("command executable does not exist") from exc
        if resolved not in ALLOWED_COMMANDS:
            raise PermissionError(
                "command is not in the path-aware operator allowlist"
            )
        values = [str(item) for item in arguments]
        if resolved == "/usr/bin/mkdir":
            flags = [item for item in values if item.startswith("-")]
            operands = [item for item in values if not item.startswith("-")]
            if any(item != "-p" for item in flags) or not operands:
                raise PermissionError("mkdir permits only -p and approved destination paths")
            values = flags + [self._path_argument(item, allow_missing=True) for item in operands]
        elif resolved == "/usr/bin/touch":
            if not values or any(item.startswith("-") for item in values):
                raise PermissionError("touch permits only approved destination paths")
            values = [self._path_argument(item, allow_missing=True) for item in values]
        elif resolved == "/usr/bin/mv":
            if len(values) != 2 or any(item.startswith("-") for item in values):
                raise PermissionError("mv requires exactly two approved paths")
            values = [
                self._path_argument(values[0]),
                self._path_argument(values[1], allow_missing=True),
            ]
        elif resolved == "/usr/bin/cp":
            flags = [item for item in values if item.startswith("-")]
            operands = [item for item in values if not item.startswith("-")]
            if any(item not in {"-a", "-p", "-r", "-R"} for item in flags) or len(operands) < 2:
                raise PermissionError(
                    "cp permits only -a/-p/-r/-R and approved source/destination paths"
                )
            checked = [self._path_argument(item) for item in operands[:-1]]
            checked.append(self._path_argument(operands[-1], allow_missing=True))
            values = flags + checked
        return resolved, values

    def propose_command(
        self,
        executable: str,
        arguments: Sequence[str],
        cwd: str,
        reason: str,
        requested_by: str = "little-oogway",
    ) -> OperatorAction:
        resolved, checked_arguments = self._validated_command(executable, arguments)
        workdir = self.policy.resolve(cwd)
        if not workdir.is_dir():
            raise ValueError("working directory is not a directory")
        argv = [resolved, *checked_arguments]
        if len(argv) > 100 or sum(map(len, argv)) > 20_000:
            raise ValueError("command exceeds the structured argument limit")
        self._enforce_pending_limit()
        return self.store.propose(
            action_type="command",
            risk_level="yellow",
            arguments={"argv": argv, "cwd": str(workdir), "timeout": 120},
            reason=reason.strip() or "Little Oogway requested a command",
            requested_by=requested_by,
            requested_via="private-open-webui",
        )

    def propose_privileged_command(
        self,
        executable: str,
        arguments: Sequence[str],
        cwd: str,
        reason: str,
        requested_by: str = "little-oogway",
    ) -> OperatorAction:
        del executable, arguments, cwd, reason, requested_by
        raise PermissionError(
            "no privileged operation has an argument-safe broker profile yet"
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
        resolved, checked_arguments = self._validated_command(argv[0], argv[1:])
        if [resolved, *checked_arguments] != argv:
            raise PermissionError("stored command no longer satisfies the operator policy")
        cwd = self.policy.resolve(str(action.arguments.get("cwd", "")))
        timeout = min(max(int(action.arguments.get("timeout", 120)), 1), 900)
        execution_argv = argv
        if action.risk_level == "red":
            raise PermissionError("privileged operator execution is disabled pending a safe profile")
        completed = subprocess.run(
            execution_argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=MINIMAL_COMMAND_ENV,
        )
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
