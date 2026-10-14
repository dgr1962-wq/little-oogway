"""
title: Little Oogway Private Machine Operator
author: AnyKey Cafe
version: 0.1.0
required_open_webui_version: 0.11.0
description: Admin-only Core tools for inspecting Little Oogway's machine and proposing audited actions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:8094"
TOKEN_FILE = Path.home() / ".config/little-oogway/operator.token"


def _request(path: str, *, payload: dict | None = None) -> dict:
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(
        BASE_URL + path,
        data=data,
        method="GET" if payload is None else "POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=140) as response:
        return json.loads(response.read().decode())


def _admin(user: dict[str, Any] | None) -> bool:
    return (user or {}).get("role") == "admin"


class Tools:
    def inspect_system(self, __user__: dict[str, Any] | None = None) -> str:
        """Inspect CPU uptime, memory, disks, and GPU on Little Oogway's machine."""
        if not _admin(__user__):
            return "Denied: machine tools require an authenticated administrator."
        return json.dumps(_request("/v1/status"), indent=2)

    def list_directory(self, path: str, __user__: dict[str, Any] | None = None) -> str:
        """List a directory under /home/darren or /mnt/storage; protected credential areas are denied."""
        if not _admin(__user__):
            return "Denied: machine tools require an authenticated administrator."
        return json.dumps(_request("/v1/files?" + urlencode({"path": path})), indent=2)

    def read_text_file(self, path: str, __user__: dict[str, Any] | None = None) -> str:
        """Read a bounded UTF-8 text file from an approved path; secrets and browser profiles are denied."""
        if not _admin(__user__):
            return "Denied: machine tools require an authenticated administrator."
        return json.dumps(_request("/v1/read?" + urlencode({"path": path})), indent=2)

    def search_text_files(
        self, root: str, query: str, __user__: dict[str, Any] | None = None
    ) -> str:
        """Search bounded text content beneath an approved root without entering protected areas."""
        if not _admin(__user__):
            return "Denied: machine tools require an authenticated administrator."
        return json.dumps(_request("/v1/search?" + urlencode({"root": root, "query": query})), indent=2)

    def propose_command(
        self,
        executable: str,
        arguments_json: str,
        working_directory: str,
        reason: str,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Propose a structured user-level command. It cannot run until approved in the local operator console."""
        if not _admin(__user__):
            return "Denied: machine tools require an authenticated administrator."
        try:
            arguments = json.loads(arguments_json or "[]")
        except json.JSONDecodeError as exc:
            return f"Denied: arguments_json is invalid: {exc}"
        if not isinstance(arguments, list):
            return "Denied: arguments_json must contain one JSON array."
        result = _request(
            "/v1/actions/command",
            payload={
                "executable": executable,
                "arguments": arguments,
                "cwd": working_directory,
                "reason": reason,
                "requested_by": (__user__ or {}).get("name", "little-oogway-admin"),
            },
        )
        return (
            "Command proposed but not executed. Review it in the private localhost approval console.\n"
            + json.dumps(result, indent=2)
        )

    def operator_actions(
        self, status: str = "pending", __user__: dict[str, Any] | None = None
    ) -> str:
        """List pending or completed machine actions from the TokenSpace audit ledger."""
        if not _admin(__user__):
            return "Denied: machine tools require an authenticated administrator."
        return json.dumps(_request("/v1/actions?" + urlencode({"status": status})), indent=2)

    def propose_administrative_command(
        self,
        executable: str,
        arguments_json: str,
        working_directory: str,
        reason: str,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Propose a red-risk administrative command. It requires ledger approval and graphical PolicyKit authentication."""
        if not _admin(__user__):
            return "Denied: administrative tools require an authenticated administrator."
        try:
            arguments = json.loads(arguments_json or "[]")
        except json.JSONDecodeError as exc:
            return f"Denied: arguments_json is invalid: {exc}"
        if not isinstance(arguments, list):
            return "Denied: arguments_json must contain one JSON array."
        result = _request(
            "/v1/actions/admin-command",
            payload={
                "executable": executable,
                "arguments": arguments,
                "cwd": working_directory,
                "reason": reason,
                "requested_by": (__user__ or {}).get("name", "little-oogway-admin"),
            },
        )
        return (
            "Administrative command proposed but not executed. Approval and a graphical "
            "PolicyKit password prompt are both required.\n" + json.dumps(result, indent=2)
        )
