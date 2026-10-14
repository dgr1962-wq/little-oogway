from __future__ import annotations

import json
import os
import time
import uuid
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from roundtable.controller import RoundtableController
from roundtable.participants import OllamaParticipant
from roundtable.browser_participants import CHATGPT, CLAUDE, VisibleBrowserParticipant
from roundtable.deepseek import DeepSeekMonitor, DeepSeekParticipant

from .adapter import RoundtableParticipantAdapter
from .cli import development_dsn
from .embeddings import OllamaEmbeddingModel
from .ollama import OllamaChatModel
from .repository import TokenSpaceRepository
from .retrieval import HybridMemoryRetriever
from .session import ConversationSession
from .tools import AbsorbSourceTool


MODEL_ID = "little-oogway-roundtable"
WORKSPACE = Path(__file__).resolve().parents[3]


def latest_user_prompt(messages: object) -> str:
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                text = "\n".join(
                    str(item.get("text", ""))
                    for item in content if isinstance(item, dict) and item.get("type") == "text"
                ).strip()
                if text:
                    return text
    raise ValueError("No nonempty user message was supplied")


class RoundtableRuntime:
    def __init__(self) -> None:
        self.ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        self.primary_model = os.getenv("OLLAMA_MODEL", "qwen3:8b")
        self.observer_model = os.getenv("ROUNDTABLE_OBSERVER_MODEL", "llama3.1:8b")
        self.transcript_directory = WORKSPACE / "roundtable" / "transcripts" / "webui"
        self.visible_externals = os.getenv("ROUNDTABLE_VISIBLE_EXTERNALS", "1") == "1"
        profile_root = WORKSPACE / "roundtable" / "agents" / "chrome_profiles"
        self.chatgpt = VisibleBrowserParticipant(
            name="ChatGPT",
            site=CHATGPT,
            profile_directory=profile_root / "chatgpt",
            debug_port=int(os.getenv("ROUNDTABLE_CHATGPT_DEBUG_PORT", "9223")),
        )
        self.claude = VisibleBrowserParticipant(
            name="Claude",
            site=CLAUDE,
            profile_directory=profile_root / "claude",
            debug_port=int(os.getenv("ROUNDTABLE_CLAUDE_DEBUG_PORT", "9224")),
        )
        self.deepseek_monitor = DeepSeekMonitor(
            profile_directory=profile_root / "deepseek-monitor",
            port=int(os.getenv("ROUNDTABLE_DEEPSEEK_MONITOR_PORT", "8092")),
        )
        deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek = DeepSeekParticipant(
            api_key=deepseek_key,
            monitor=self.deepseek_monitor,
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        ) if deepseek_key else None
        self._round_lock = threading.Lock()

    def respond(self, prompt: str) -> tuple[str, dict[str, Any]]:
        with self._round_lock:
            return self._respond_locked(prompt)

    def _respond_locked(self, prompt: str) -> tuple[str, dict[str, Any]]:
        store = TokenSpaceRepository(development_dsn())
        session = ConversationSession(
            model=OllamaChatModel(model_name=self.primary_model, base_url=self.ollama_url),
            store=store,
            memory_retriever=HybridMemoryRetriever(
                repository=store,
                embedding_model=OllamaEmbeddingModel(base_url=self.ollama_url),
            ),
            tools=(AbsorbSourceTool(store),),
            participant_name="little-oogway",
        )
        oogway = RoundtableParticipantAdapter(session)
        first_content, first_metadata = oogway.respond(prompt)
        if first_metadata.get("tool_execution"):
            return first_content, {"mode": "bounded-tool", **first_metadata}

        class PreparedOogway:
            name = "Little Oogway"
            def __init__(self) -> None:
                self._first_response_pending = True

            def respond(self, next_prompt: str):
                if self._first_response_pending:
                    self._first_response_pending = False
                    return first_content, first_metadata
                return oogway.respond(next_prompt)

        participants: list[Any] = [PreparedOogway()]
        if self.visible_externals:
            participants.extend((self.chatgpt, self.claude))
            if self.deepseek is not None:
                participants.append(self.deepseek)
            for browser_participant in (self.chatgpt, self.claude):
                try:
                    browser_participant.ensure_browser()
                except Exception:
                    pass
            if self.deepseek is not None:
                try:
                    self.deepseek_monitor.open_window()
                except Exception:
                    pass
        else:
            participants.append(OllamaParticipant(
                name="Independent Observer",
                model=self.observer_model,
                base_url=self.ollama_url,
                system_prompt=(
                    "You are an independent participant in Little Oogway's Roundtable. "
                    "Analyze the question from a distinct perspective, identify assumptions, "
                    "and answer directly. Do not imitate or claim to see other participants."
                ),
            ))
        controller = RoundtableController(
            participants,
            transcript_directory=self.transcript_directory,
        )
        result = controller.run_deliberation(prompt, chair=participants[0])
        sections = ["# Procedural ledger"]
        ledger = result.chair.metadata.get("procedural_ledger", []) if result.chair else []
        sections.extend(
            f"- **{entry['participant']}**: {entry['disposition']}"
            for entry in ledger
        )
        sections.append("# Chair's disposition")
        if result.chair is not None:
            chair_body = result.chair.content if result.chair.succeeded else f"Unavailable: {result.chair.error}"
            sections.append(chair_body or "Unavailable")
        sections.append("# Opening statements")
        for participant in result.participants:
            body = participant.content if participant.succeeded else f"Unavailable: {participant.error}"
            sections.append(f"## {participant.participant}\n\n{body}")
        sections.append("# Review and procedural interventions")
        for participant in result.reviews:
            body = participant.content if participant.succeeded else f"Unavailable: {participant.error}"
            sections.append(f"## {participant.participant}\n\n{body}")
        sections.append(f"---\nRound `{result.round_id}`")
        return "\n\n".join(sections), {
            "mode": "deliberation",
            "round_id": result.round_id,
            "transcript": str(result.transcript_path),
            "participants": [p.participant for p in result.participants],
            "procedure": ["opening", "review", "chair_disposition"],
            "chair": result.chair.participant if result.chair else None,
            "succeeded": result.succeeded,
            "deepseek_configured": self.deepseek is not None,
        }


class Handler(BaseHTTPRequestHandler):
    runtime = RoundtableRuntime()
    server_version = "LittleOogwayRoundtable/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"roundtable-api: {fmt % args}", flush=True)

    def _json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            self._json(200, {"status": "ok", "model": MODEL_ID})
        elif self.path.rstrip("/") == "/v1/models":
            self._json(200, {"object": "list", "data": [{
                "id": MODEL_ID, "object": "model", "created": 0,
                "owned_by": "little-oogway",
            }]})
        else:
            self._json(404, {"error": {"message": "Not found"}})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._json(404, {"error": {"message": "Not found"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 2 * 1024 * 1024:
                raise ValueError("Invalid request size")
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            prompt = latest_user_prompt(request.get("messages"))
            content, metadata = self.runtime.respond(prompt)
            completion_id = f"chatcmpl-{uuid.uuid4().hex}"
            created = int(time.time())
            if request.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                chunk = {
                    "id": completion_id, "object": "chat.completion.chunk",
                    "created": created, "model": MODEL_ID,
                    "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}],
                }
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                final = {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                self.wfile.write(f"data: {json.dumps(final)}\n\ndata: [DONE]\n\n".encode())
                self.wfile.flush()
            else:
                self._json(200, {
                    "id": completion_id, "object": "chat.completion", "created": created,
                    "model": MODEL_ID,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "oogway": metadata,
                })
        except Exception as exc:
            self._json(400, {"error": {"message": str(exc), "type": type(exc).__name__}})


def main() -> int:
    host = os.getenv("ROUNDTABLE_API_HOST", "127.0.0.1")
    port = int(os.getenv("ROUNDTABLE_API_PORT", "8091"))
    print(f"Roundtable API listening at http://{host}:{port}/v1", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
