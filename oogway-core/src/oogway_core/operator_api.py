from __future__ import annotations

import argparse
import hmac
import html
import json
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .cli import development_dsn
from .operator import OperatorRuntime, action_dict
from .operator_store import OperatorStore
from .private_memory import PrivateMemorySearchRuntime
from .web_research import WebResearchRuntime


TOKEN_FILE = Path.home() / ".config/little-oogway/operator.token"


def load_token() -> str:
    value = os.getenv("OOGWAY_OPERATOR_TOKEN")
    if value:
        token = value.strip()
        if len(token) < 32:
            raise ValueError("operator token is missing or too short")
        return token
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise ValueError("operator token is missing or too short")
    return token


def login_page(error: str = "") -> bytes:
    warning = f"<p class=\"error\">{html.escape(error)}</p>" if error else ""
    return f"""<!doctype html><html><head><meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width\"><title>Operator sign in</title>
<style>body{{background:#111827;color:#e5e7eb;font:16px system-ui}}main{{max-width:520px;margin:10vh auto;padding:24px}}
input,button{{box-sizing:border-box;width:100%;padding:12px;margin:8px 0;border-radius:8px}}.error{{color:#fca5a5}}</style>
</head><body><main><h1>Little Oogway Operator</h1>{warning}
<p>Enter the private operator token to open an eight-hour localhost session.</p>
<form method=\"post\" action=\"/login\"><input type=\"password\" name=\"token\" autocomplete=\"current-password\" required>
<button>Sign in</button></form></main></body></html>""".encode()


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
.pending{{background:#78350f}} article:has(pre){{position:relative}}
.buttons{{display:flex;gap:10px}} form{{display:inline}} button{{border:0;border-radius:7px;padding:9px 13px;font-weight:700;cursor:pointer}}
.approve{{background:#34d399}} .reject{{background:#fca5a5}}
</style></head><body><main><h1>Little Oogway Operator</h1>
<p>Private localhost approval and audit console. Commands run only after an administrator approves them here. Red-risk administrative actions also require a graphical PolicyKit password prompt.</p>
{content}</main></body></html>""".encode()


class OperatorHandler(BaseHTTPRequestHandler):
    runtime: OperatorRuntime
    research: WebResearchRuntime
    memory: PrivateMemorySearchRuntime
    token: str
    sessions: dict[str, tuple[str, float]] = {}
    sessions_lock = threading.Lock()
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

    def _request_context_valid(self) -> bool:
        port = int(self.server.server_address[1])
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        if self.headers.get("Host", "") not in allowed:
            return False
        if self.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
            return False
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme != "http" or parsed.netloc not in allowed:
                return False
        return True

    def _session(self) -> tuple[str, str] | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("oogway_operator_session")
        if morsel is None:
            return None
        session_id = morsel.value
        with self.sessions_lock:
            value = self.sessions.get(session_id)
            if value is None:
                return None
            csrf, expires_at = value
            if expires_at <= time.time():
                self.sessions.pop(session_id, None)
                return None
        return session_id, csrf

    def _html(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, *, cookie: str | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _body(self) -> dict:
        length = min(int(self.headers.get("Content-Length", "0")), 1_000_000)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode())

    def do_GET(self) -> None:
        if not self._request_context_valid():
            self._json(403, {"error": "invalid localhost request context"})
            return
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/health":
            self._json(200, {"ok": True, "service": "little-oogway-operator"})
            return
        if parsed.path == "/":
            session = self._session()
            if session is None:
                self._redirect("/login")
                return
            actions = [action_dict(item) for item in self.runtime.store.list(limit=50)]
            body = dashboard(actions, session[1])
            self._html(200, body)
            return
        if parsed.path == "/login":
            if self._session() is not None:
                self._redirect("/")
                return
            self._html(200, login_page())
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
            elif parsed.path == "/v1/web/search":
                payload = self.research.search(
                    query.get("query", [""])[0], int(query.get("limit", ["8"])[0])
                )
            elif parsed.path == "/v1/web/read":
                payload = self.research.read_page(query.get("url", [""])[0])
            elif parsed.path == "/v1/memory/search":
                payload = self.memory.search(
                    query.get("query", [""])[0], int(query.get("limit", ["6"])[0])
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
        if not self._request_context_valid():
            self._json(403, {"error": "invalid localhost request context"})
            return
        parsed = urlsplit(self.path)
        if parsed.path == "/login":
            length = min(int(self.headers.get("Content-Length", "0")), 20_000)
            form = parse_qs(self.rfile.read(length).decode())
            supplied = form.get("token", [""])[0]
            if not hmac.compare_digest(supplied, self.token):
                self._html(403, login_page("The operator token was not accepted."))
                return
            session_id = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            with self.sessions_lock:
                self.sessions[session_id] = (csrf, time.time() + 8 * 60 * 60)
            cookie = (
                f"oogway_operator_session={session_id}; Path=/; Max-Age=28800; "
                "HttpOnly; SameSite=Strict"
            )
            self._redirect("/", cookie=cookie)
            return
        if parsed.path.startswith("/actions/"):
            session = self._session()
            if session is None:
                self._json(401, {"error": "authenticated operator session required"})
                return
            length = min(int(self.headers.get("Content-Length", "0")), 20_000)
            form = parse_qs(self.rfile.read(length).decode())
            csrf = form.get("csrf", [""])[0]
            if not hmac.compare_digest(csrf, session[1]):
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
            self._redirect("/")
            return
        if not self._authorized():
            self._json(401, {"error": "operator bearer token required"})
            return
        try:
            body = self._body()
            if parsed.path not in {"/v1/actions/command", "/v1/actions/admin-command"}:
                self._json(404, {"error": "not found"})
                return
            arguments = body.get("arguments", [])
            if not isinstance(arguments, list):
                raise ValueError("arguments must be a JSON array")
            proposer = (
                self.runtime.propose_privileged_command
                if parsed.path.endswith("/admin-command")
                else self.runtime.propose_command
            )
            action = proposer(
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
    OperatorHandler.research = WebResearchRuntime()
    OperatorHandler.memory = PrivateMemorySearchRuntime()
    OperatorHandler.token = load_token()
    server = ThreadingHTTPServer((args.host, args.port), OperatorHandler)
    print(f"Little Oogway operator listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
