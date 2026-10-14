from __future__ import annotations

import argparse
import hmac
import html
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .cli import development_dsn
from .operator import OperatorRuntime, action_dict
from .operator_store import OperatorStore


TOKEN_FILE = Path.home() / ".config/little-oogway/operator.token"


def load_token() -> str:
    value = os.getenv("OOGWAY_OPERATOR_TOKEN")
    if value:
        return value.strip()
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise ValueError("operator token is missing or too short")
    return token


def dashboard(actions: list[dict], csrf: str) -> bytes:
    rows = []
    for action in actions:
        arguments = html.escape(json.dumps(action["arguments"], indent=2, sort_keys=True))
        buttons = ""
        if action["status"] == "pending":
            buttons = f"""
              <form method="post" action="/actions/{action['id']}/approve">
                <input type="hidden" name="csrf" value="{html.escape(csrf)}">
                <button class="approve">Approve and run</button>
              </form>
              <form method="post" action="/actions/{action['id']}/reject">
                <input type="hidden" name="csrf" value="{html.escape(csrf)}">
                <button class="reject">Reject</button>
              </form>
            """
        rows.append(f"""
          <article>
            <header><strong>{html.escape(action['action_type'])}</strong>
              <span class="{html.escape(action['status'])}">{html.escape(action['status'])}</span>
              <code>{html.escape(action['id'])}</code>
            </header>
            <p>{html.escape(action['reason'])}</p>
            <pre>{arguments}</pre>
            <div class="buttons">{buttons}</div>
          </article>
        """)
    content = "\n".join(rows) or "<p>No operator actions have been recorded.</p>"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Little Oogway Operator</title><style>
body{{margin:0;background:#111827;color:#e5e7eb;font:16px system-ui}}
main{{max-width:980px;margin:auto;padding:24px}} h1{{color:#93c5fd}}
article{{background:#1f2937;border:1px solid #374151;border-radius:12px;padding:16px;margin:14px 0}}
header{{display:flex;gap:12px;align-items:center;flex-wrap:wrap}} code,pre{{font:13px ui-monospace,monospace}}
pre{{white-space:pre-wrap;background:#0b1220;padding:12px;border-radius:8px;overflow-wrap:anywhere}}
span{{padding:3px 8px;border-radius:999px;background:#374151}} .complete{{background:#065f46}} .failed,.rejected{{background:#7f1d1d}}
.buttons{{display:flex;gap:10px}} form{{display:inline}} button{{border:0;border-radius:7px;padding:9px 13px;font-weight:700;cursor:pointer}}
.approve{{background:#34d399}} .reject{{background:#fca5a5}}
</style></head><body><main><h1>Little Oogway Operator</h1>
<p>Private localhost approval and audit console. Commands run only after an administrator approves them here.</p>
{content}</main></body></html>""".encode()


class OperatorHandler(BaseHTTPRequestHandler):
    runtime: OperatorRuntime
    token: str
    server_version = "LittleOogwayOperator/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"operator-api: {self.address_string()} {format % args}", flush=True)

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {self.token}"
        return hmac.compare_digest(supplied, expected)

    def _body(self) -> dict:
        length = min(int(self.headers.get("Content-Length", "0")), 1_000_000)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode())

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/health":
            self._json(200, {"ok": True, "service": "little-oogway-operator"})
            return
        if parsed.path == "/":
            actions = [action_dict(item) for item in self.runtime.store.list(limit=50)]
            body = dashboard(actions, self.token)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if not self._authorized():
            self._json(401, {"error": "operator bearer token required"})
            return
        try:
            if parsed.path == "/v1/status":
                payload = self.runtime.system_status()
            elif parsed.path == "/v1/files":
                payload = self.runtime.list_directory(query.get("path", [""])[0])
            elif parsed.path == "/v1/read":
                payload = self.runtime.read_file(query.get("path", [""])[0])
            elif parsed.path == "/v1/search":
                payload = self.runtime.search_files(
                    query.get("root", [""])[0], query.get("query", [""])[0]
                )
            elif parsed.path == "/v1/actions":
                status = query.get("status", [None])[0]
                payload = {"actions": [action_dict(item) for item in self.runtime.store.list(status=status)]}
            else:
                self._json(404, {"error": "not found"})
                return
        except (OSError, ValueError, PermissionError) as exc:
            self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
            return
        self._json(200, payload)

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path.startswith("/actions/"):
            length = min(int(self.headers.get("Content-Length", "0")), 20_000)
            form = parse_qs(self.rfile.read(length).decode())
            csrf = form.get("csrf", [""])[0]
            if not hmac.compare_digest(csrf, self.token):
                self._json(403, {"error": "invalid approval token"})
                return
            parts = parsed.path.strip("/").split("/")
            if len(parts) != 3 or parts[2] not in {"approve", "reject"}:
                self._json(404, {"error": "not found"})
                return
            action_id, decision = parts[1], parts[2]
            if decision == "reject":
                changed = self.runtime.store.transition(
                    action_id, from_status="pending", to_status="rejected", actor="local-admin"
                )
            else:
                changed = self.runtime.store.transition(
                    action_id, from_status="pending", to_status="approved", actor="local-admin"
                )
                if changed:
                    self.runtime.execute_approved(action_id)
            if not changed:
                self._json(409, {"error": "action is no longer pending"})
                return
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return
        if not self._authorized():
            self._json(401, {"error": "operator bearer token required"})
            return
        try:
            body = self._body()
            if parsed.path != "/v1/actions/command":
                self._json(404, {"error": "not found"})
                return
            arguments = body.get("arguments", [])
            if not isinstance(arguments, list):
                raise ValueError("arguments must be a JSON array")
            action = self.runtime.propose_command(
                str(body.get("executable", "")),
                [str(item) for item in arguments],
                str(body.get("cwd", "/home/darren")),
                str(body.get("reason", "")),
                requested_by=str(body.get("requested_by", "little-oogway")),
            )
        except (OSError, ValueError, PermissionError) as exc:
            self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
            return
        self._json(HTTPStatus.CREATED, {"action": action_dict(action), "approval_url": "http://127.0.0.1:8094/"})


def main() -> int:
    parser = argparse.ArgumentParser(description="Little Oogway private operator service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8094)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1"}:
        raise ValueError("operator service may listen only on loopback")
    runtime = OperatorRuntime(OperatorStore(development_dsn()))
    OperatorHandler.runtime = runtime
    OperatorHandler.token = load_token()
    server = ThreadingHTTPServer((args.host, args.port), OperatorHandler)
    print(f"Little Oogway operator listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

