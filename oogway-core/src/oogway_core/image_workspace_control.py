from __future__ import annotations

import argparse
import hmac
import json
import os
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen


TOKEN_FILE = Path.home() / ".config/little-oogway/main-desk-image-control.token"
UNIT = "stable-diffusion.service"


def load_token() -> str:
    token = os.getenv("OOGWAY_IMAGE_CONTROL_TOKEN", "").strip()
    if not token:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise ValueError("image workspace token is missing or too short")
    return token


def service_state() -> dict[str, object]:
    completed = subprocess.run(
        ["systemctl", "--user", "is-active", UNIT],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    state = completed.stdout.strip() or "unknown"
    try:
        with urlopen("http://127.0.0.1:7860/sdapi/v1/sd-models", timeout=2) as response:
            api_ready = response.status == 200
    except OSError:
        api_ready = False
    return {"service": state, "api_ready": api_ready, "workspace": "stable-diffusion"}


def control_service(action: str) -> dict[str, object]:
    if action not in {"start", "stop", "restart"}:
        raise ValueError("unsupported image workspace action")
    completed = subprocess.run(
        ["systemctl", "--user", action, UNIT],
        capture_output=True,
        check=False,
        text=True,
        timeout=45,
    )
    if completed.returncode:
        detail = completed.stderr.strip()[:500] or "systemctl returned an error"
        raise RuntimeError(detail)
    return {"accepted": True, "action": action, **service_state()}


class ImageWorkspaceHandler(BaseHTTPRequestHandler):
    token: str
    server_version = "OogwayImageWorkspace/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"image-workspace: {self.address_string()} {format % args}", flush=True)

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

    def do_GET(self) -> None:
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "bearer token required"})
            return
        if self.path != "/v1/workspace/status":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        self._json(HTTPStatus.OK, service_state())

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "bearer token required"})
            return
        prefix = "/v1/workspace/"
        if not self.path.startswith(prefix):
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            result = control_service(self.path.removeprefix(prefix))
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": f"{type(exc).__name__}: {exc}"})
            return
        self._json(HTTPStatus.OK, result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Narrow Stable Diffusion workspace controller")
    parser.add_argument("--host", default=os.getenv("OOGWAY_IMAGE_CONTROL_HOST", "192.168.254.14"))
    parser.add_argument("--port", type=int, default=int(os.getenv("OOGWAY_IMAGE_CONTROL_PORT", "8876")))
    args = parser.parse_args()
    ImageWorkspaceHandler.token = load_token()
    server = ThreadingHTTPServer((args.host, args.port), ImageWorkspaceHandler)
    print(f"image-workspace listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
