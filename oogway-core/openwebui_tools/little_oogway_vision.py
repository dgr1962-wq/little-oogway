"""
title: Little Oogway Visual Understanding
author: AnyKey Cafe
version: 0.2.0
required_open_webui_version: 0.11.0
description: Admin-only, format-normalized visual inspection and two-pass SDXL prompt composition through Oogway Core.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:8094"
TOKEN_FILE = Path.home() / ".config/little-oogway/operator.token"
IMAGE_CONTROL_TOKEN_FILE = Path.home() / ".config/little-oogway/main-desk-image-control.token"
IMAGE_CONTROL_URL = "http://192.168.254.14:8876"


def _admin(user: dict[str, Any] | None) -> bool:
    return (user or {}).get("role") == "admin"


def _request(path: str, payload: dict) -> dict:
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    request = Request(
        BASE_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=360) as response:
        return json.loads(response.read().decode("utf-8"))


def _media_workspace_request(
    path: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict:
    token = IMAGE_CONTROL_TOKEN_FILE.read_text(encoding="utf-8").strip()
    data = (
        json.dumps(payload).encode("utf-8")
        if payload is not None
        else (b"" if method == "POST" else None)
    )
    request = Request(
        IMAGE_CONTROL_URL + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


class Tools:
    def image_workspace_status(self, __user__: dict[str, Any] | None = None) -> str:
        """Check whether the private Stable Diffusion workspace on Main Desk is running and ready. Administrator only."""
        if not _admin(__user__):
            return "Denied: image workspace control requires an authenticated administrator."
        return json.dumps(
            _media_workspace_request("/v1/workspace/status"), indent=2, ensure_ascii=False
        )

    def image_workspace_control(
        self,
        action: str,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Start, stop, or restart the private Stable Diffusion workspace on Main Desk. Administrator only; no general remote command access is provided."""
        if not _admin(__user__):
            return "Denied: image workspace control requires an authenticated administrator."
        normalized = action.strip().lower()
        if normalized not in {"start", "stop", "restart"}:
            return "Denied: action must be start, stop, or restart."
        return json.dumps(
            _media_workspace_request(f"/v1/workspace/{normalized}", method="POST"),
            indent=2,
            ensure_ascii=False,
        )

    def video_workspace_status(self, __user__: dict[str, Any] | None = None) -> str:
        """Check whether the private Wan video workspace on Main Desk is running and ready. Administrator only."""
        if not _admin(__user__):
            return "Denied: video workspace control requires an authenticated administrator."
        return json.dumps(
            _media_workspace_request("/v1/workspace/status?workspace=video"),
            indent=2,
            ensure_ascii=False,
        )

    def video_workspace_control(
        self,
        action: str,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Start, stop, or restart the private Wan video workspace. Image and video engines cannot run simultaneously. Administrator only."""
        if not _admin(__user__):
            return "Denied: video workspace control requires an authenticated administrator."
        normalized = action.strip().lower()
        if normalized not in {"start", "stop", "restart"}:
            return "Denied: action must be start, stop, or restart."
        return json.dumps(
            _media_workspace_request(
                f"/v1/workspace/video/{normalized}", method="POST"
            ),
            indent=2,
            ensure_ascii=False,
        )

    def generate_video(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 640,
        height: int = 352,
        frames: int = 49,
        fps: int = 16,
        steps: int = 20,
        cfg: float = 5.0,
        seed: int = -1,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Queue one bounded text-to-video job in Main Desk's fixed Wan 2.2 workflow. Returns a job ID; administrator only."""
        if not _admin(__user__):
            return "Denied: video generation requires an authenticated administrator."
        payload: dict[str, Any] = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "frames": frames,
            "fps": fps,
            "steps": steps,
            "cfg": cfg,
            "seed": seed,
        }
        if negative_prompt.strip():
            payload["negative_prompt"] = negative_prompt
        return json.dumps(
            _media_workspace_request(
                "/v1/video/generate", method="POST", payload=payload
            ),
            indent=2,
            ensure_ascii=False,
        )

    def video_generation_status(
        self,
        prompt_id: str,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Check a previously queued Main Desk video job and report its saved output. Administrator only."""
        if not _admin(__user__):
            return "Denied: video generation status requires an authenticated administrator."
        return json.dumps(
            _media_workspace_request(f"/v1/video/jobs/{prompt_id.strip()}"),
            indent=2,
            ensure_ascii=False,
        )

    def inspect_image(
        self,
        image_source: str,
        visual_question: str = "",
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """Inspect one approved local image path or public HTTPS image. Common formats including WebP are normalized before Qwen3-VL sees them; the original is not changed."""
        if not _admin(__user__):
            return "Denied: visual inspection requires an authenticated administrator."
        result = _request(
            "/v1/vision/inspect",
            {"source": image_source, "question": visual_question},
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    def create_image_variation_prompt(
        self,
        image_source: str,
        requested_change: str,
        __user__: dict[str, Any] | None = None,
    ) -> str:
        """First observe an approved source image without modification, then create an SDXL prompt for the requested creative variation. Use generate_image separately with the returned prompt."""
        if not _admin(__user__):
            return "Denied: visual prompt creation requires an authenticated administrator."
        result = _request(
            "/v1/vision/variation-prompt",
            {"source": image_source, "requested_change": requested_change},
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
