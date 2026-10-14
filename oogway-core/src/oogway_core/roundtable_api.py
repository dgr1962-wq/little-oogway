from __future__ import annotations

import json
import os
import re
import time
import uuid
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from roundtable.participants import OllamaParticipant
from roundtable.browser_participants import CHATGPT, CLAUDE, VisibleBrowserParticipant
from roundtable.deepseek import DeepSeekMonitor, DeepSeekParticipant
from roundtable.procedure import ProceduralRoundResult, ResumableProcedure

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
COMMAND_RE = re.compile(
    r"^/roundtable\s+(confirm|resume|status|chair|recover)\s+([0-9a-f-]{36})(?:\s*\n(.*))?$",
    re.IGNORECASE | re.DOTALL,
)


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


def parse_roundtable_command(prompt: str) -> tuple[str, str, str] | None:
    match = COMMAND_RE.fullmatch(prompt.strip())
    if match is None:
        return None
    return match.group(1).lower(), match.group(2).lower(), (match.group(3) or "").strip()


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
        self.preflight_directory = self.transcript_directory / "preflight"
        self.runtime_instance = str(uuid.uuid4())
        self.preflight_lease_seconds = int(
            os.getenv("ROUNDTABLE_PREFLIGHT_LEASE_SECONDS", "1800")
        )

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".pending")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _preflight_path(self, preflight_id: str) -> Path:
        return self.preflight_directory / f"{preflight_id}.json"

    def _participant_names(self) -> list[str]:
        names = ["Little Oogway"]
        if self.visible_externals:
            names.extend(("ChatGPT", "Claude"))
            if self.deepseek is not None:
                names.append("DeepSeek")
        else:
            names.append("Independent Observer")
        return names

    def _render_preflight(self, record: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        preflight_id = record["preflight_id"]
        participants = record["participants"]
        external_prompt = record["external_prompt"]
        recovery_note = (
            f"\n\nThis safely replaces interrupted preflight `{record['recovered_from']}`."
            if record.get("recovered_from") else ""
        )
        content = (
            "# Roundtable preflight\n\n"
            f"**Preflight:** `{preflight_id}`  \n"
            f"**Participants:** {', '.join(participants)}  \n"
            "**Procedure:** openings → review pass → operator ruling if required → "
            "additional review pass → final chair minutes\n\n"
            "## Exact opening prompt sent to external participants\n\n"
            f"```text\n{external_prompt}\n```\n\n"
            "Little Oogway's memory-informed statements remain withheld from external "
            "dockets. No external model has been contacted by this preflight."
            f"{recovery_note}\n\n"
            "To begin this exact round, send:\n\n"
            f"`/roundtable confirm {preflight_id}`"
        )
        return content, {
            "mode": "preflight",
            "preflight_id": preflight_id,
            "participants": participants,
            "external_models_contacted": False,
            "recovered_from": record.get("recovered_from"),
        }

    def _create_preflight(
        self, motion: str, *, recovered_from: str | None = None
    ) -> tuple[str, dict[str, Any]]:
        preflight_id = str(uuid.uuid4())
        participants = self._participant_names()
        external_prompt = ResumableProcedure.opening_prompt(motion)
        record = {
            "version": 1,
            "preflight_id": preflight_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
            "motion": motion,
            "participants": participants,
            "external_prompt": external_prompt,
            "recovered_from": recovered_from,
        }
        self._write_json(self._preflight_path(preflight_id), record)
        return self._render_preflight(record)

    def _load_preflight(self, preflight_id: str) -> dict[str, Any]:
        path = self._preflight_path(preflight_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"Unknown Roundtable preflight: {preflight_id}") from exc

    def _recover_preflight(self, preflight_id: str) -> tuple[str, dict[str, Any]]:
        record = self._load_preflight(preflight_id)
        if record["status"] == "pending":
            return self._render_preflight(record)
        if record["status"] in {"completed", "recovered"}:
            raise ValueError(f"Preflight is already {record['status']}")
        if record["status"] == "running":
            same_runtime = record.get("runtime_instance") == self.runtime_instance
            lease_active = float(record.get("lease_expires_at", 0)) > time.time()
            if same_runtime and lease_active:
                raise ValueError("Preflight is still active in this runtime")
        content, metadata = self._create_preflight(
            record["motion"], recovered_from=preflight_id
        )
        record["status"] = "recovered"
        record["recovery_preflight_id"] = metadata["preflight_id"]
        record["recovered_at"] = datetime.now(timezone.utc).isoformat()
        self._write_json(self._preflight_path(preflight_id), record)
        return content, metadata

    def _progress_callback(self, round_id: str, motion: str):
        try:
            self.deepseek_monitor.open_window()
            self.deepseek_monitor.round_begin(round_id, motion)
        except Exception:
            pass

        def progress(event: dict[str, Any]) -> None:
            try:
                self.deepseek_monitor.round_progress(**event)
            except Exception:
                pass

        return progress

    def _finish_progress(self, status: str) -> None:
        try:
            self.deepseek_monitor.round_finish(status)
        except Exception:
            pass

    def _build_participants(self) -> tuple[list[Any], Any]:
        store = TokenSpaceRepository(development_dsn())
        session = ConversationSession(
            model=OllamaChatModel(model_name=self.primary_model, base_url=self.ollama_url),
            store=store,
            memory_retriever=HybridMemoryRetriever(
                repository=store,
                embedding_model=OllamaEmbeddingModel(base_url=self.ollama_url),
            ),
            tools=(),
            participant_name="little-oogway",
        )
        adapter = RoundtableParticipantAdapter(session)

        class NamedOogway:
            name = "Little Oogway"
            retry_safe = True

            @staticmethod
            def respond(next_prompt: str):
                return adapter.respond(next_prompt)

        oogway = NamedOogway()
        participants: list[Any] = [oogway]
        if self.visible_externals:
            participants.extend((self.chatgpt, self.claude))
            if self.deepseek is not None:
                participants.append(self.deepseek)
            for browser_participant in (self.chatgpt, self.claude):
                try:
                    browser_participant.ensure_browser()
                except Exception:
                    # Participant-level failure isolation records the real error
                    # when its turn arrives without preventing other seats from
                    # deliberating.
                    pass
            if self.deepseek is not None:
                try:
                    self.deepseek_monitor.open_window()
                except Exception:
                    # The monitor is observability, not the API participant.
                    pass
        else:
            participants.append(OllamaParticipant(
                name="Independent Observer",
                model=self.observer_model,
                base_url=self.ollama_url,
                system_prompt=(
                    "You are an independent participant in Little Oogway's Roundtable. "
                    "Analyze the motion from a distinct perspective, identify assumptions, "
                    "and answer directly. Do not imitate or claim to see other participants."
                ),
            ))
        return participants, oogway

    @staticmethod
    def _render_result(result: ProceduralRoundResult) -> str:
        latest_pass = len(result.review_passes)
        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        ledger = state["passes"][-1]["ledger"]
        title = {
            "awaiting_ruling": "awaiting a ruling",
            "awaiting_chair": "awaiting chair recovery",
            "completed": "complete",
        }.get(result.status, result.status)
        sections = [
            f"# Roundtable {title}",
            f"**Round:** `{result.round_id}`  ",
            f"**Review pass:** {latest_pass}  ",
            f"**Status:** `{result.status}`",
            "## Procedural ledger",
        ]
        sections.extend(
            f"- `{entry['item_id']}` **{entry['participant']}** — "
            f"{entry['disposition']} · {entry['status']}"
            for entry in ledger
        )
        sections.extend(("## Chair's report", result.chair.content or f"Unavailable: {result.chair.error}"))
        sections.append("## Latest review pass")
        for review in result.reviews:
            body = review.content if review.succeeded else f"Unavailable: {review.error}"
            sections.append(f"### {review.participant}\n\n{body}")
        if result.status == "awaiting_ruling":
            sections.extend((
                "## Continue without repeating openings",
                "Supply the ruling, requested fact, or clarification after this command:",
                f"```text\n/roundtable resume {result.round_id}\nRULING OR CLARIFICATION HERE\n```",
            ))
        elif result.status == "awaiting_chair":
            sections.extend((
                "## Retry only the chair",
                "Participant turns are already preserved and will not be repeated. Send:",
                f"`/roundtable chair {result.round_id}`",
            ))
        return "\n\n".join(sections)

    def _confirm(self, preflight_id: str) -> tuple[str, dict[str, Any]]:
        record = self._load_preflight(preflight_id)
        if record["status"] == "completed":
            round_id = record.get("round_id")
            return (
                f"That preflight already launched Roundtable round `{round_id}`. "
                f"Use `/roundtable status {round_id}` to inspect it.",
                {"mode": "preflight_already_completed", "round_id": round_id},
            )
        if record["status"] != "pending":
            raise ValueError(
                f"Preflight is {record['status']}; use /roundtable recover {preflight_id}"
            )
        if record["participants"] != self._participant_names():
            raise ValueError("Participant availability changed; create a fresh preflight")
        round_id = str(uuid.uuid4())
        record.update({
            "status": "running",
            "round_id": round_id,
            "runtime_instance": self.runtime_instance,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "lease_expires_at": time.time() + self.preflight_lease_seconds,
            "attempt_count": int(record.get("attempt_count", 0)) + 1,
        })
        self._write_json(self._preflight_path(preflight_id), record)
        progress = self._progress_callback(round_id, record["motion"])
        try:
            participants, chair = self._build_participants()
            procedure = ResumableProcedure(participants, self.transcript_directory)
            result = procedure.start(
                record["motion"], chair=chair, progress=progress, round_id=round_id
            )
        except Exception as exc:
            record["status"] = "failed"
            record["failed_at"] = datetime.now(timezone.utc).isoformat()
            record["last_error"] = f"{type(exc).__name__}: {exc}"
            self._write_json(self._preflight_path(preflight_id), record)
            self._finish_progress("failed")
            raise
        record["status"] = "completed"
        record["completed_at"] = datetime.now(timezone.utc).isoformat()
        self._write_json(self._preflight_path(preflight_id), record)
        self._finish_progress(result.status)
        return self._render_result(result), {
            "mode": "resumable_procedure",
            "round_id": result.round_id,
            "status": result.status,
            "review_pass": len(result.review_passes),
            "participants": record["participants"],
        }

    def _resume(self, round_id: str, ruling: str) -> tuple[str, dict[str, Any]]:
        if not ruling:
            raise ValueError("Put the ruling or clarification on the line after the resume command")
        state_path = self.transcript_directory / "state" / f"{round_id}.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        progress = self._progress_callback(round_id, state["motion"])
        participants, chair = self._build_participants()
        procedure = ResumableProcedure(participants, self.transcript_directory)
        result = procedure.resume(round_id, ruling, chair=chair, progress=progress)
        self._finish_progress(result.status)
        return self._render_result(result), {
            "mode": "resumable_procedure",
            "round_id": result.round_id,
            "status": result.status,
            "review_pass": len(result.review_passes),
            "participants": [participant.name for participant in participants],
        }

    def _retry_chair(self, round_id: str) -> tuple[str, dict[str, Any]]:
        state_path = self.transcript_directory / "state" / f"{round_id}.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        progress = self._progress_callback(round_id, state["motion"])
        participants, chair = self._build_participants()
        procedure = ResumableProcedure(participants, self.transcript_directory)
        result = procedure.retry_chair(round_id, chair=chair, progress=progress)
        self._finish_progress(result.status)
        return self._render_result(result), {
            "mode": "chair_recovery",
            "round_id": result.round_id,
            "status": result.status,
            "review_pass": len(result.review_passes),
            "participants_repeated": False,
        }

    def _status(self, round_id: str) -> tuple[str, dict[str, Any]]:
        # Status inspection is local-only and must not launch browser or API participants.
        if not re.fullmatch(r"[0-9a-f-]{36}", round_id):
            raise ValueError("Invalid round identifier")
        state_path = self.transcript_directory / "state" / f"{round_id}.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"Unknown procedural round: {round_id}") from exc
        latest = state["passes"][-1]
        status = {
            "round_id": state["round_id"],
            "motion": state["motion"],
            "status": state["status"],
            "chair": state["chair"],
            "participants": state["participants"],
            "review_pass": latest["number"],
            "ledger": latest["ledger"],
        }
        ledger = "\n".join(
            f"- `{entry['item_id']}` **{entry['participant']}** — "
            f"{entry['disposition']} · {entry['status']}"
            for entry in status["ledger"]
        )
        content = (
            f"# Roundtable status\n\n**Round:** `{round_id}`  \n"
            f"**Status:** `{status['status']}`  \n"
            f"**Review pass:** {status['review_pass']}\n\n"
            f"## Procedural ledger\n\n{ledger}"
        )
        return content, {"mode": "procedure_status", **status}

    def respond(self, prompt: str) -> tuple[str, dict[str, Any]]:
        with self._round_lock:
            return self._respond_locked(prompt)

    def _respond_locked(self, prompt: str) -> tuple[str, dict[str, Any]]:
        command = parse_roundtable_command(prompt)
        if command is not None:
            action, identifier, body = command
            if action == "confirm":
                return self._confirm(identifier)
            if action == "resume":
                return self._resume(identifier, body)
            if action == "chair":
                return self._retry_chair(identifier)
            if action == "recover":
                return self._recover_preflight(identifier)
            return self._status(identifier)

        # Preserve the existing bounded ingestion shortcut without involving an
        # external participant or using the prompt as a deliberation motion.
        store = TokenSpaceRepository(development_dsn())
        absorb_tool = AbsorbSourceTool(store)
        if absorb_tool.can_handle(prompt):
            # Route the bounded action through the ordinary session so both the
            # operator request and tool result retain their TokenSpace audit trail.
            session = ConversationSession(
                model=OllamaChatModel(model_name=self.primary_model, base_url=self.ollama_url),
                store=store,
                tools=(absorb_tool,),
                participant_name="little-oogway",
            )
            result = session.ask(prompt)
            return result.content, {
                "mode": "bounded-tool",
                "conversation_id": result.conversation_id,
                "round_id": result.round_id,
                **result.metadata,
            }

        return self._create_preflight(prompt)


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
    try:
        Handler.runtime.deepseek_monitor.ensure_server()
    except OSError as exc:
        print(f"Roundtable monitor unavailable: {exc}", flush=True)
    print(f"Roundtable API listening at http://{host}:{port}/v1", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
