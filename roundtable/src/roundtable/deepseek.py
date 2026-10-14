from __future__ import annotations

import json
import os
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
<title>Little Oogway Roundtable Monitor</title>
<style>
:root{color-scheme:dark;font-family:Inter,system-ui,sans-serif;background:#0b1020;color:#e8edff}
body{margin:0}.bar{padding:18px 24px;background:#111936;border-bottom:1px solid #263157;display:flex;gap:14px;align-items:center}
.dot{width:11px;height:11px;border-radius:50%;background:#64748b}.dot.running{background:#38bdf8;box-shadow:0 0 14px #38bdf8}.dot.complete{background:#4ade80}.dot.failed{background:#fb7185}
main{padding:24px;max-width:980px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}.label{font-size:.75rem;letter-spacing:.12em;text-transform:uppercase;color:#8da2d8;margin-top:24px}
.card{white-space:pre-wrap;line-height:1.55;background:#111936;border:1px solid #263157;border-radius:14px;padding:18px;margin-top:8px;min-height:42px}.metric{font-size:1.08rem;font-weight:650}.sub{font-size:.82rem;color:#8da2d8;margin-top:5px}
#status{color:#a9b8e4}.muted{color:#7181ad}
</style></head><body><div class="bar"><span id="dot" class="dot"></span><strong>Little Oogway Roundtable</strong><span id="status">Waiting for a round</span></div>
<main><div class="grid"><div class="card"><div id="phase" class="metric">Idle</div><div class="sub">Phase</div></div><div class="card"><div id="participant" class="metric">—</div><div class="sub">Current participant</div></div><div class="card"><div id="elapsed" class="metric">0s</div><div class="sub">Elapsed</div></div><div class="card"><div id="usage" class="metric">—</div><div id="cost" class="sub">DeepSeek usage</div></div></div>
<div class="label">Procedural ledger</div><div id="ledger" class="card muted">No ledger yet.</div>
<div class="label">Question sent to DeepSeek</div><div id="prompt" class="card muted">No DeepSeek turn active.</div>
<div class="label">DeepSeek response</div><div id="response" class="card muted">The streamed answer will appear here.</div></main>
<script>
async function refresh(){try{const r=await fetch('/state',{cache:'no-store'}),s=await r.json();
document.getElementById('status').textContent=s.message||s.status;
document.getElementById('dot').className='dot '+s.status;
document.getElementById('phase').textContent=(s.phase||'idle').replaceAll('_',' ');document.getElementById('participant').textContent=s.participant||'—';document.getElementById('elapsed').textContent=Math.round(s.elapsed_seconds||0)+'s';
const d=s.deepseek||{},u=d.usage||{},c=d.estimated_cost_usd;document.getElementById('usage').textContent=u.total_tokens?u.total_tokens.toLocaleString()+' tokens':'—';document.getElementById('cost').textContent=c==null?'DeepSeek cost not reported':('Estimated cost $'+Number(c.min).toFixed(6)+(c.max!==c.min?'–$'+Number(c.max).toFixed(6):''));
const l=document.getElementById('ledger');l.textContent=(s.ledger||[]).map(x=>x.item_id+' · '+x.participant+' · '+x.disposition+' · '+x.status).join('\n')||'No ledger yet.';l.classList.toggle('muted',!(s.ledger||[]).length);
const p=document.getElementById('prompt'),o=document.getElementById('response');p.textContent=d.prompt||'No DeepSeek turn active.';o.textContent=d.response||'The streamed answer will appear here.';
p.classList.toggle('muted',!d.prompt);o.classList.toggle('muted',!d.response);}catch(e){}setTimeout(refresh,500)}refresh();
</script></body></html>"""


@dataclass
class DeepSeekMonitor:
    profile_directory: Path
    host: str = "127.0.0.1"
    port: int = 8092
    chrome_path: str = "/opt/google/chrome/chrome"
    _state: dict[str, Any] = field(default_factory=lambda: {
        "status": "idle", "message": "Waiting for a Roundtable round",
        "round_id": None, "motion": "", "phase": "idle", "participant": None,
        "phase_status": "idle", "started_at": None, "elapsed_seconds": 0,
        "ledger": [], "updated_at": time.time(),
        "deepseek": {"status": "idle", "prompt": "", "response": "", "usage": {},
                     "estimated_cost_usd": None},
    }, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _server: ThreadingHTTPServer | None = field(default=None, init=False, repr=False)
    _browser: subprocess.Popen[bytes] | None = field(default=None, init=False, repr=False)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            value = dict(self._state)
            value["deepseek"] = dict(self._state["deepseek"])
            started_at = value.get("started_at")
            if started_at and value.get("status") == "running":
                value["elapsed_seconds"] = max(0, time.time() - started_at)
            return value

    def update(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values, updated_at=time.time())

    def round_begin(self, round_id: str, motion: str) -> None:
        now = time.time()
        self.update(
            status="running", message="Roundtable round in progress", round_id=round_id,
            motion=motion, phase="starting", participant=None, phase_status="running",
            started_at=now, elapsed_seconds=0, ledger=[],
        )
        self._update_deepseek(
            status="idle", prompt="", response="", usage={}, estimated_cost_usd=None
        )

    def round_progress(self, **event: Any) -> None:
        values = {
            "phase": event.get("phase", "round"),
            "participant": event.get("participant"),
            "phase_status": event.get("status", "running"),
            "message": f"{event.get('phase', 'round')} · {event.get('status', 'running')}",
        }
        if "ledger" in event:
            values["ledger"] = event["ledger"]
        self.update(**values)

    def round_finish(self, status: str) -> None:
        started_at = self._state.get("started_at")
        elapsed = max(0, time.time() - started_at) if started_at else 0
        display = "complete" if status == "completed" else "idle"
        self.update(
            status=display, message=f"Roundtable status: {status}", phase=status,
            participant=None, phase_status=status, elapsed_seconds=elapsed,
        )

    def _update_deepseek(self, **values: Any) -> None:
        with self._lock:
            self._state["deepseek"].update(values)
            self._state["updated_at"] = time.time()

    def begin(self, prompt: str) -> None:
        self._update_deepseek(
            status="running", prompt=prompt, response="", usage={}, estimated_cost_usd=None
        )

    def append(self, text: str) -> None:
        with self._lock:
            self._state["deepseek"]["response"] += text
            self._state["updated_at"] = time.time()

    def complete(
        self, usage: dict[str, Any] | None = None, estimated_cost_usd: float | None = None
    ) -> None:
        self._update_deepseek(
            status="complete", usage=usage or {}, estimated_cost_usd=estimated_cost_usd
        )

    def fail(self, error: str) -> None:
        self._update_deepseek(status="failed", error=error)

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

    def _estimated_cost(self, usage: dict[str, Any]) -> dict[str, float] | None:
        """Return an honest cost range from reported usage, never a billed total."""
        if not usage:
            return None
        try:
            input_rate = float(os.environ["DEEPSEEK_INPUT_USD_PER_MILLION"])
            output_rate = float(os.environ["DEEPSEEK_OUTPUT_USD_PER_MILLION"])
        except (KeyError, ValueError):
            if self.model != "deepseek-flash":
                return None
            # Official DeepSeek Flash USD rates checked 2026-10-14. The API bills
            # different peak/off-peak rates and may change them; presenting the
            # range avoids guessing the Chinese-holiday exception.
            hit_low, hit_high = 0.003, 0.006
            miss_low, miss_high = 0.15, 0.30
            output_low, output_high = 0.60, 1.20
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            prompt_details = usage.get("prompt_tokens_details") or {}
            hit_tokens = int(
                usage.get("prompt_cache_hit_tokens")
                or prompt_details.get("cached_tokens")
                or 0
            )
            miss_tokens = int(
                usage.get("prompt_cache_miss_tokens")
                or max(0, prompt_tokens - hit_tokens)
            )
            output_tokens = int(usage.get("completion_tokens") or 0)
            low = (
                hit_tokens * hit_low + miss_tokens * miss_low + output_tokens * output_low
            ) / 1_000_000
            high = (
                hit_tokens * hit_high + miss_tokens * miss_high + output_tokens * output_high
            ) / 1_000_000
            return {"min": round(low, 8), "max": round(high, 8)}
        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        exact = round(
            (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000,
            8,
        )
        return {"min": exact, "max": exact}

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
            "stream_options": {"include_usage": True},
        }
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        pieces: list[str] = []
        usage: dict[str, Any] = {}
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
                    if isinstance(event.get("usage"), dict):
                        usage.update(event["usage"])
                    choices = event.get("choices") or []
                    delta = choices[0].get("delta", {}) if choices else {}
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
        try:
            estimated_cost = self._estimated_cost(usage)
        except (AttributeError, TypeError, ValueError) as exc:
            estimated_cost = None
            usage["cost_estimate_error"] = f"{type(exc).__name__}: {exc}"
        self.monitor.complete(usage, estimated_cost)
        return content, {
            "kind": "api",
            "provider": "deepseek",
            "model": self.model,
            "usage": usage,
            "estimated_cost_usd": estimated_cost,
        }
