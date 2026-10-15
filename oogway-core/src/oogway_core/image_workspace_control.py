from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen


TOKEN_FILE = Path.home() / ".config/little-oogway/main-desk-image-control.token"
WORKSPACES = {
    "image": {
        "unit": "stable-diffusion.service",
        "name": "stable-diffusion",
        "health": "http://127.0.0.1:7860/sdapi/v1/sd-models",
    },
    "video": {
        "unit": "main-desk-video-generation.service",
        "name": "wan-video-generation",
        "health": "http://127.0.0.1:8188/system_stats",
    },
}
UNIT = str(WORKSPACES["image"]["unit"])
COMFY_URL = "http://127.0.0.1:8188"
MAX_REQUEST_BYTES = 64 * 1024
DEFAULT_NEGATIVE = (
    "static frame, low quality, blurry, distorted anatomy, extra limbs, "
    "text, subtitles, watermark, logo, compression artifacts"
)


def load_token() -> str:
    token = os.getenv("OOGWAY_IMAGE_CONTROL_TOKEN", "").strip()
    if not token:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise ValueError("workspace token is missing or too short")
    return token


def _workspace(name: str) -> dict[str, str]:
    try:
        return WORKSPACES[name]
    except KeyError as exc:
        raise ValueError("unsupported workspace") from exc


def _unit_state(unit: str) -> str:
    completed = subprocess.run(
        ["systemctl", "--user", "is-active", unit],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip() or "unknown"


def service_state(workspace: str = "image") -> dict[str, object]:
    definition = _workspace(workspace)
    state = _unit_state(definition["unit"])
    try:
        with urlopen(definition["health"], timeout=2) as response:
            api_ready = response.status == 200
    except OSError:
        api_ready = False
    return {
        "service": state,
        "api_ready": api_ready,
        "workspace": definition["name"],
    }


def control_service(action: str, workspace: str = "image") -> dict[str, object]:
    if action not in {"start", "stop", "restart"}:
        raise ValueError("unsupported workspace action")
    definition = _workspace(workspace)
    if action in {"start", "restart"}:
        other = "video" if workspace == "image" else "image"
        other_definition = _workspace(other)
        if _unit_state(other_definition["unit"]) in {"active", "activating", "reloading"}:
            raise RuntimeError(
                f"{other_definition['name']} is active; stop it before starting "
                f"{definition['name']} so the two GPU workloads cannot collide"
            )
    completed = subprocess.run(
        ["systemctl", "--user", action, definition["unit"]],
        capture_output=True,
        check=False,
        text=True,
        timeout=45,
    )
    if completed.returncode:
        detail = completed.stderr.strip()[:500] or "systemctl returned an error"
        raise RuntimeError(detail)
    return {"accepted": True, "action": action, **service_state(workspace)}


def _bounded_text(value: object, name: str, maximum: int, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    result = value.strip()
    if required and not result:
        raise ValueError(f"{name} is required")
    if len(result) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return result


def _bounded_int(
    value: object,
    name: str,
    minimum: int,
    maximum: int,
    *,
    multiple: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    if multiple and value % multiple:
        raise ValueError(f"{name} must be a multiple of {multiple}")
    return value


def validate_video_request(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    allowed = {"prompt", "negative_prompt", "width", "height", "frames", "fps", "steps", "cfg", "seed"}
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"unsupported fields: {', '.join(sorted(unknown))}")
    prompt = _bounded_text(payload.get("prompt", ""), "prompt", 4000, required=True)
    negative = _bounded_text(
        payload.get("negative_prompt", DEFAULT_NEGATIVE), "negative_prompt", 2000
    )
    width = _bounded_int(payload.get("width", 640), "width", 320, 1024, multiple=32)
    height = _bounded_int(payload.get("height", 352), "height", 320, 1024, multiple=32)
    if width * height > 832 * 480:
        raise ValueError("requested pixel area exceeds the safe 12 GB GPU profile")
    frames = _bounded_int(payload.get("frames", 49), "frames", 17, 81)
    if (frames - 1) % 4:
        raise ValueError("frames must equal 4n+1 (for example 49 or 81)")
    fps = _bounded_int(payload.get("fps", 16), "fps", 8, 30)
    steps = _bounded_int(payload.get("steps", 20), "steps", 4, 30)
    cfg_value = payload.get("cfg", 5.0)
    if isinstance(cfg_value, bool) or not isinstance(cfg_value, (int, float)):
        raise ValueError("cfg must be a number")
    cfg = float(cfg_value)
    if not 1.0 <= cfg <= 10.0:
        raise ValueError("cfg must be between 1 and 10")
    seed = payload.get("seed", -1)
    if isinstance(seed, bool) or not isinstance(seed, int) or not -1 <= seed < 2**63:
        raise ValueError("seed must be -1 or a non-negative 63-bit integer")
    if seed == -1:
        seed = secrets.randbelow(2**63)
    return {
        "prompt": prompt,
        "negative_prompt": negative,
        "width": width,
        "height": height,
        "frames": frames,
        "fps": fps,
        "steps": steps,
        "cfg": cfg,
        "seed": seed,
    }


def build_video_graph(settings: dict[str, object]) -> dict[str, object]:
    """Build the one reviewed Wan 2.2 graph; callers cannot submit arbitrary nodes."""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
        "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": settings["prompt"]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": settings["negative_prompt"]}},
        "7": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["3", 0], "width": settings["width"], "height": settings["height"], "length": settings["frames"], "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0], "seed": settings["seed"], "steps": settings["steps"], "cfg": settings["cfg"], "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "CreateVideo", "inputs": {"images": ["9", 0], "fps": float(settings["fps"])}},
        "11": {"class_type": "SaveVideo", "inputs": {"video": ["10", 0], "filename_prefix": "Little-Oogway/video", "format": "mp4", "codec": {"codec": "h264", "encoding": {"crf": 20}}}},
    }


def _comfy_json(path: str, *, payload: dict[str, object] | None = None, timeout: int = 15) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        COMFY_URL + path,
        data=data,
        method="GET" if data is None else "POST",
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(f"video engine rejected the request: {detail}") from exc
    except (URLError, OSError) as exc:
        raise RuntimeError("video engine is not ready") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("video engine returned an invalid response")
    return parsed


def generate_video(payload: object) -> dict[str, object]:
    if not service_state("video")["api_ready"]:
        raise RuntimeError("video workspace is not API-ready")
    settings = validate_video_request(payload)
    result = _comfy_json("/prompt", payload={"prompt": build_video_graph(settings)})
    prompt_id = result.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id:
        raise RuntimeError("video engine did not return a job ID")
    return {"accepted": True, "prompt_id": prompt_id, "settings": settings}


def video_job_status(prompt_id: str) -> dict[str, object]:
    if not isinstance(prompt_id, str) or len(prompt_id) > 80 or not prompt_id:
        raise ValueError("invalid video job ID")
    if any(character not in "0123456789abcdef-" for character in prompt_id.lower()):
        raise ValueError("invalid video job ID")
    history = _comfy_json(f"/history/{prompt_id}")
    entry = history.get(prompt_id)
    if entry is None:
        return {"prompt_id": prompt_id, "state": "queued-or-running", "outputs": []}
    if not isinstance(entry, dict):
        raise RuntimeError("video engine returned invalid job history")
    outputs: list[dict[str, str]] = []
    for node_output in (entry.get("outputs") or {}).values():
        if not isinstance(node_output, dict):
            continue
        for key in ("videos", "images", "gifs"):
            items = node_output.get(key, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                filename = item.get("filename")
                subfolder = item.get("subfolder", "")
                if isinstance(filename, str) and isinstance(subfolder, str):
                    safe_filename = Path(filename).name[:255]
                    safe_subfolder = Path(subfolder).name[:255]
                    outputs.append(
                        {
                            "filename": safe_filename,
                            "subfolder": safe_subfolder,
                            "main_desk_path": str(
                                Path("/home/darren/Videos/Little-Oogway")
                                / safe_subfolder
                                / safe_filename
                            ),
                        }
                    )
    status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
    complete = bool(status.get("completed")) or bool(outputs)
    return {
        "prompt_id": prompt_id,
        "state": "complete" if complete else "running",
        "outputs": outputs[:20],
        "status": str(status.get("status_str", ""))[:100],
    }


class ImageWorkspaceHandler(BaseHTTPRequestHandler):
    token: str
    server_version = "OogwayMediaWorkspace/0.2"

    def log_message(self, format: str, *args: object) -> None:
        print(f"media-workspace: {self.address_string()} {format % args}", flush=True)

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        return hmac.compare_digest(supplied, f"Bearer {self.token}")

    def _body(self) -> object:
        raw_length = self.headers.get("Content-Length", "")
        if not raw_length.isdigit():
            raise ValueError("valid Content-Length required")
        length = int(raw_length)
        if length > MAX_REQUEST_BYTES:
            raise ValueError("request body is too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "bearer token required"})
            return
        parsed = urlsplit(self.path)
        if parsed.path == "/v1/workspace/status":
            workspace = parse_qs(parsed.query).get("workspace", ["image"])[0]
            try:
                self._json(HTTPStatus.OK, service_state(workspace))
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": f"{type(exc).__name__}: {exc}"})
            return
        job_prefix = "/v1/video/jobs/"
        if parsed.path.startswith(job_prefix):
            try:
                self._json(HTTPStatus.OK, video_job_status(parsed.path.removeprefix(job_prefix)))
            except (OSError, RuntimeError, ValueError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": f"{type(exc).__name__}: {exc}"})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "bearer token required"})
            return
        parsed = urlsplit(self.path)
        try:
            if parsed.path == "/v1/video/generate":
                result = generate_video(self._body())
            else:
                parts = parsed.path.strip("/").split("/")
                if parts[:2] != ["v1", "workspace"]:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                if len(parts) == 3:
                    workspace, action = "image", parts[2]
                elif len(parts) == 4:
                    workspace, action = parts[2], parts[3]
                else:
                    raise ValueError("unsupported workspace route")
                result = control_service(action, workspace)
        except (json.JSONDecodeError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": f"{type(exc).__name__}: {exc}"})
            return
        self._json(HTTPStatus.OK, result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Narrow image and video workspace controller")
    parser.add_argument("--host", default=os.getenv("OOGWAY_IMAGE_CONTROL_HOST", "192.168.254.14"))
    parser.add_argument("--port", type=int, default=int(os.getenv("OOGWAY_IMAGE_CONTROL_PORT", "8876")))
    args = parser.parse_args()
    ImageWorkspaceHandler.token = load_token()
    server = ThreadingHTTPServer((args.host, args.port), ImageWorkspaceHandler)
    print(f"media-workspace listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
