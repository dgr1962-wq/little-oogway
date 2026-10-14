from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .models import ModelResponse


@dataclass(frozen=True)
class OllamaChatModel:
    """Synchronous chat model backed by the host-side Ollama API."""

    model_name: str = "qwen3:8b"
    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 120.0
    provider: str = "ollama"

    def respond(self, prompt: str, system_prompt: str) -> ModelResponse:
        payload = {
            "model": self.model_name,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": system_prompt},
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
        return ModelResponse(
            content=content,
            metadata={
                "provider": self.provider,
                "model": body.get("model", self.model_name),
                "done_reason": body.get("done_reason"),
                "prompt_eval_count": body.get("prompt_eval_count"),
                "eval_count": body.get("eval_count"),
                "total_duration_ns": body.get("total_duration"),
            },
        )
