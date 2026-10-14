from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


MONITOR_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>DeepSeek · Little Oogway Roundtable</title>
<style>
:root{color-scheme:dark;font-family:Inter,system-ui,sans-serif;background:#0b1020;color:#e8edff}
body{margin:0}.bar{padding:18px 24px;background:#111936;border-bottom:1px solid #263157;display:flex;gap:14px;align-items:center}
.dot{width:11px;height:11px;border-radius:50%;background:#64748b}.dot.running{background:#38bdf8;box-shadow:0 0 14px #38bdf8}.dot.complete{background:#4ade80}.dot.failed{background:#fb7185}
main{padding:24px;max-width:900px;margin:auto}.label{font-size:.75rem;letter-spacing:.12em;text-transform:uppercase;color:#8da2d8;margin-top:24px}
.card{white-space:pre-wrap;line-height:1.55;background:#111936;border:1px solid #263157;border-radius:14px;padding:18px;margin-top:8px;min-height:42px}
#status{color:#a9b8e4}.muted{color:#7181ad}
</style></head><body><div class="bar"><span id="dot" class="dot"></span><strong>DeepSeek API Monitor</strong><span id="status">Waiting for a Roundtable round</span></div>
<main><div class="label">Question sent to DeepSeek</div><div id="prompt" class="card muted">No round active.</div>
<div class="label">DeepSeek response</div><div id="response" class="card muted">The streamed answer will appear here.</div></main>
<script>
async function refresh(){try{const r=await fetch('/state',{cache:'no-store'}),s=await r.json();
document.getElementById('status').textContent=s.message||s.status;
document.getElementById('dot').className='dot '+s.status;
const p=document.getElementById('prompt'),o=document.getElementById('response');p.textContent=s.prompt||'No round active.';o.textContent=s.response||'The streamed answer will appear here.';
p.classList.toggle('muted',!s.prompt);o.classList.toggle('muted',!s.response);}catch(e){}setTimeout(refresh,300)}refresh();
</script></body></html>"""


@dataclass
class DeepSeekMonitor:
    profile_directory: Path
    host: str = "127.0.0.1"
    port: int = 8092
    chrome_path: str = "/opt/google/chrome/chrome"
    _state: dict[str, Any] = field(default_factory=lambda: {
        "status": "idle", "message": "Waiting for a Roundtable round",
        "prompt": "", "response": "", "updated_at": time.time(),
    }, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _server: ThreadingHTTPServer | None = field(default=None, init=False, repr=False)
    _browser: subprocess.Popen[bytes] | None = field(default=None, init=False, repr=False)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def update(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values, updated_at=time.time())

    def begin(self, prompt: str) -> None:
        self.update(status="running", message="DeepSeek is responding…", prompt=prompt, response="")

    def append(self, text: str) -> None:
        with self._lock:
            self._state["response"] += text
            self._state["updated_at"] = time.time()

    def complete(self) -> None:
        self.update(status="complete", message="DeepSeek response complete")

    def fail(self, error: str) -> None:
        self.update(status="failed", message=error)

    def ensure_server(self) -> None:
        if self._server is not None:
            return
        monitor = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: object) -> None:
                return

            def do_GET(self) -> None:
                if self.path == "/state":
                    payload = json.dumps(monitor.snapshot()).encode()
                    self.send_response(200); self.send_header("Content-Type", "application/json")
                elif self.path in ("/", "/index.html"):
                    payload = MONITOR_HTML.encode()
                    self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
                else:
                    payload = b"Not found"; self.send_response(404); self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        threading.Thread(target=self._server.serve_forever, name="deepseek-monitor", daemon=True).start()

    def open_window(self) -> None:
        self.ensure_server()
        if self._browser is not None and self._browser.poll() is None:
            return
        self.profile_directory.mkdir(parents=True, exist_ok=True)
        log = (self.profile_directory / "monitor-browser.log").open("ab")
        self._browser = subprocess.Popen(
            [self.chrome_path, f"--user-data-dir={self.profile_directory}",
             "--profile-directory=Default", "--no-first-run", "--new-window",
             "--window-size=900,900", f"--app=http://{self.host}:{self.port}/"],
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )


@dataclass
class DeepSeekParticipant:
    api_key: str
    monitor: DeepSeekMonitor
    name: str = "DeepSeek"
    model: str = "deepseek-flash"
    base_url: str = "https://api.deepseek.com"
    timeout_seconds: float = 240.0
    system_prompt: str = (
        "You are an independent participant in Little Oogway's Roundtable. "
        "Analyze the question from a distinct perspective and answer directly."
    )

    def respond(self, prompt: str) -> tuple[str, dict[str, Any]]:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("DeepSeek prompt cannot be empty")
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        self.monitor.open_window()
        self.monitor.begin(prompt)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": True,
        }
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        pieces: list[str] = []
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    delta = event.get("choices", [{}])[0].get("delta", {})
                    text = delta.get("content") or ""
                    if text:
                        pieces.append(text); self.monitor.append(text)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            message = f"DeepSeek request failed: {exc}"
            self.monitor.fail(message)
            raise RuntimeError(message) from exc
        content = "".join(pieces).strip()
        if not content:
            self.monitor.fail("DeepSeek returned no response content")
            raise RuntimeError("DeepSeek returned no response content")
        self.monitor.complete()
        return content, {"kind": "api", "provider": "deepseek", "model": self.model}
