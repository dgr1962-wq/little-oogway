from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class OllamaEmbeddingModel:
    model_name: str = "nomic-embed-text:v1.5"
    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 120.0
    dimensions: int = 768
    num_gpu: int | None = None
    num_thread: int | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, object] = {"model": self.model_name, "input": texts}
        options = {
            key: value
            for key, value in {"num_gpu": self.num_gpu, "num_thread": self.num_thread}.items()
            if value is not None
        }
        if options:
            payload["options"] = options
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/api/embed",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ollama embedding request failed: {exc}") from exc
        embeddings = body.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise RuntimeError("Ollama returned an unexpected embedding batch")
        for embedding in embeddings:
            if not isinstance(embedding, list) or len(embedding) != self.dimensions:
                raise RuntimeError(
                    f"Expected {self.dimensions} embedding dimensions, "
                    f"received {len(embedding) if isinstance(embedding, list) else 'invalid'}"
                )
        return embeddings

    def digest(self) -> str:
        request = urllib.request.Request(f"{self.base_url.rstrip('/')}/api/tags")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                models = json.loads(response.read().decode("utf-8")).get("models", [])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not inspect Ollama models: {exc}") from exc
        for model in models:
            if model.get("name") == self.model_name:
                digest = model.get("digest")
                if digest:
                    return str(digest)
        raise RuntimeError(f"Ollama model is not installed: {self.model_name}")


def vector_literal(values: list[float], *, dimensions: int = 768) -> str:
    if len(values) != dimensions:
        raise ValueError(f"Expected {dimensions} values, received {len(values)}")
    return "[" + ",".join(format(float(value), ".9g") for value in values) + "]"
