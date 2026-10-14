from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class Participant(Protocol):
    """A model or deterministic actor that can answer one round prompt."""

    name: str

    def respond(self, prompt: str) -> tuple[str, dict[str, Any]]:
        """Return response text and serializable metadata."""


@dataclass(frozen=True)
class MockParticipant:
    """A deterministic participant used to verify orchestration."""

    name: str = "mock-observer"
    prefix: str = "Observed question"

    def respond(self, prompt: str) -> tuple[str, dict[str, Any]]:
        return f"{self.prefix}: {prompt}", {"kind": "mock"}


@dataclass(frozen=True)
class OllamaParticipant:
    """A local participant backed by Ollama's chat endpoint."""

    name: str = "little-oogway"
    model: str = "qwen3:8b"
    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 120.0
    system_prompt: str = (
        "You are Little Oogway, a local participant in a roundtable. "
        "Answer the question directly and concisely. Do not claim to control "
        "other participants or to have performed actions you did not perform."
    )

    def respond(self, prompt: str) -> tuple[str, dict[str, Any]]:
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc

        content = body.get("message", {}).get("content", "").strip()
        if not content:
            raise RuntimeError("Ollama returned no response content")

        metadata = {
            "kind": "ollama",
            "model": body.get("model", self.model),
            "done_reason": body.get("done_reason"),
            "prompt_eval_count": body.get("prompt_eval_count"),
            "eval_count": body.get("eval_count"),
            "total_duration_ns": body.get("total_duration"),
        }
        return content, metadata
