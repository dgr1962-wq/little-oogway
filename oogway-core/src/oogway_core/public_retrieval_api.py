from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlsplit

from .cli import development_dsn
from .embeddings import OllamaEmbeddingModel
from .repository import MemoryHit, TokenSpaceRepository
from .retrieval import PublicArchiveRetriever


MAX_QUERY_CHARS = 500
MAX_EXCERPT_CHARS = 1600
MAX_RESULTS = 6


def public_title(url: str) -> str:
    path = unquote(urlsplit(url).path).strip("/")
    if not path:
        return "Any Key Cafe"
    return path.rsplit("/", 1)[-1].replace("-", " ").strip().title()


def serialize_hit(hit: MemoryHit) -> dict[str, Any]:
    return {
        "title": public_title(hit.source_locator),
        "url": hit.source_locator,
        "text": hit.content[:MAX_EXCERPT_CHARS],
        "score": round(hit.combined_score, 6),
        "chunk": hit.source_ordinal,
    }


class PublicSearchRuntime:
    def __init__(self, retriever: PublicArchiveRetriever | None = None) -> None:
        if retriever is None:
            ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
            retriever = PublicArchiveRetriever(
                repository=TokenSpaceRepository(development_dsn()),
                embedding_model=OllamaEmbeddingModel(base_url=ollama_url),
            )
        self.retriever = retriever

    def search(self, query: object, limit: object = 5) -> list[dict[str, Any]]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a nonempty string")
        query = query.strip()
        if len(query) > MAX_QUERY_CHARS:
            raise ValueError(f"query exceeds {MAX_QUERY_CHARS} characters")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("limit must be an integer")
        if limit < 1 or limit > MAX_RESULTS:
            raise ValueError(f"limit must be between 1 and {MAX_RESULTS}")
        return [serialize_hit(hit) for hit in self.retriever.retrieve(query, limit=limit)]


class Handler(BaseHTTPRequestHandler):
    runtime: PublicSearchRuntime
    server_version = "LittleOogwayPublicRetrieval/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"public-retrieval: {fmt % args}", flush=True)

    def _json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            self._json(200, {"status": "ok", "scope": "public-anykeycafe-only"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/search":
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 8192:
                raise ValueError("invalid request size")
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            results = self.runtime.search(request.get("query"), request.get("limit", 5))
            self._json(200, {"results": results})
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception:
            self._json(503, {"error": "retrieval temporarily unavailable"})


def main() -> int:
    host = os.getenv("PUBLIC_RETRIEVAL_HOST", "127.0.0.1")
    if host != "127.0.0.1":
        raise ValueError("public retrieval must bind only to 127.0.0.1")
    port = int(os.getenv("PUBLIC_RETRIEVAL_PORT", "8093"))
    Handler.runtime = PublicSearchRuntime()
    print(f"Public retrieval listening at http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
