"""Open WebUI Pipe for the localhost-only Little Oogway Roundtable."""

from __future__ import annotations

import asyncio
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROUNDTABLE_COMPLETIONS_URL = "http://127.0.0.1:8091/v1/chat/completions"


class Pipe:
    def __init__(self) -> None:
        self.name = "AI Roundtable"

    @staticmethod
    def _request(body: dict) -> str:
        payload = {
            "model": "little-oogway-roundtable",
            "messages": body.get("messages", []),
            # Let Open WebUI perform the outward streaming.  The Roundtable
            # result is a single auditable procedural record.
            "stream": False,
        }
        request = Request(
            ROUNDTABLE_COMPLETIONS_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=1800) as response:
                result = json.load(response)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:2000]
            raise RuntimeError(f"Roundtable rejected the request: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"Roundtable service is unavailable: {exc}") from exc

        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Roundtable returned an invalid completion") from exc

    async def pipe(self, body: dict) -> str:
        return await asyncio.to_thread(self._request, body)
