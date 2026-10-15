#!/usr/bin/env python3
"""Configure the private Open WebUI model selector for Little Oogway.

This script is deliberately limited to presentation and Pipe registration:
it does not remove Ollama models or alter TokenSpace. Embedding and raw base
models remain active but are hidden from the chat selector through metadata.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path


PIPE_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "openwebui_functions"
    / "little_oogway_roundtable_pipe.py"
)


def put_model(
    connection: sqlite3.Connection,
    *,
    model_id: str,
    owner_id: str,
    name: str,
    active: bool,
    meta: dict | None = None,
    timestamp: int,
) -> None:
    connection.execute(
        """
        INSERT INTO model(
            id, user_id, base_model_id, name, meta, params,
            created_at, updated_at, is_active
        ) VALUES (?, ?, NULL, ?, ?, '{}', ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            user_id = excluded.user_id,
            base_model_id = NULL,
            name = excluded.name,
            meta = excluded.meta,
            updated_at = excluded.updated_at,
            is_active = excluded.is_active
        """,
        (
            model_id,
            owner_id,
            name,
            json.dumps(meta or {}),
            timestamp,
            timestamp,
            int(active),
        ),
    )


def put_roundtable_pipe(
    connection: sqlite3.Connection, *, owner_id: str, timestamp: int
) -> None:
    content = PIPE_SOURCE.read_text(encoding="utf-8")
    connection.execute(
        """
        INSERT INTO function(
            id, user_id, name, type, content, meta, created_at, updated_at,
            valves, is_active, is_global
        ) VALUES (?, ?, ?, 'pipe', ?, ?, ?, ?, NULL, 1, 0)
        ON CONFLICT(id) DO UPDATE SET
            user_id = excluded.user_id,
            name = excluded.name,
            type = excluded.type,
            content = excluded.content,
            meta = excluded.meta,
            updated_at = excluded.updated_at,
            is_active = 1,
            is_global = 0
        """,
        (
            "little-oogway-roundtable",
            owner_id,
            "AI Roundtable",
            content,
            json.dumps(
                {
                    "description": (
                        "Local bridge to Little Oogway's structured, "
                        "confirmation-gated Roundtable runtime."
                    ),
                    "manifest": {},
                }
            ),
            timestamp,
            timestamp,
        ),
    )


def configure(database: Path, backup_directory: Path, owner_id: str | None) -> Path:
    database = database.resolve()
    backup_directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d-%H%M%S")
    backup = backup_directory / f"webui-before-model-selector-{stamp}.db"

    source = sqlite3.connect(database)
    try:
        destination = sqlite3.connect(backup)
        try:
            source.backup(destination)
        finally:
            destination.close()

        now = int(time.time())
        if owner_id is None:
            owner = source.execute(
                "SELECT id FROM user WHERE role = 'admin' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if owner is None:
                raise RuntimeError("Open WebUI has no administrative model owner")
            owner_id = owner[0]
        put_model(
            source,
            model_id="little-oogway-roundtable",
            owner_id=owner_id,
            name="AI Roundtable",
            active=True,
            meta={
                "profile_image_url": "/static/favicon.png",
                "description": (
                    "Structured, auditable deliberation between Little Oogway "
                    "and the configured independent model participants."
                ),
                "capabilities": {
                    "citations": True,
                    "memory": True,
                    "status_updates": True,
                },
                "tags": [{"name": "Roundtable"}],
            },
            timestamp=now,
        )
        put_roundtable_pipe(source, owner_id=owner_id, timestamp=now)

        # Active, hidden overrides keep the engines resolvable by workspace
        # presets while excluding them from the ordinary chat selector.
        # Do not add an untagged Nomic alias: Open WebUI maps Ollama basenames
        # to the same object as the fully tagged model and would remove it
        # twice while applying inactive overrides.
        source.execute(
            "DELETE FROM model WHERE id = ? AND user_id = ?",
            ("nomic-embed-text", owner_id),
        )
        for model_id, name in (
            ("nomic-embed-text:v1.5", "Nomic Embed (background only)"),
            ("qwen3:8b", "Qwen3 8B (Little Oogway base)"),
            ("qwen3-vl:8b", "Qwen3 VL 8B (visual preset base)"),
        ):
            put_model(
                source,
                model_id=model_id,
                owner_id=owner_id,
                name=name,
                active=True,
                meta={"hidden": True},
                timestamp=now,
            )

        # Core's curated server-side tools must not be crowded out by Open
        # WebUI's large generic builtin catalogue. Permit only the native
        # image-generation bridge; all other abilities use the smaller,
        # audited Little Oogway tool bundles.
        core = source.execute(
            "SELECT meta FROM model WHERE id = ?", ("little-oogway-core",)
        ).fetchone()
        if core is not None:
            core_meta = json.loads(core[0] or "{}")
            capabilities = core_meta.setdefault("capabilities", {})
            capabilities["builtin_tools"] = True
            capabilities["image_generation"] = True
            core_meta["builtinTools"] = {
                "time": False,
                "files": False,
                "knowledge": False,
                "chats": False,
                "subagents": False,
                "memory": False,
                "web_search": False,
                "image_generation": True,
                "code_interpreter": False,
                "notes": False,
                "channels": False,
                "tasks": False,
                "automations": False,
                "calendar": False,
                "notifications": False,
            }
            source.execute(
                "UPDATE model SET meta = ?, updated_at = ? WHERE id = ?",
                (json.dumps(core_meta), now, "little-oogway-core"),
            )

        row = source.execute("SELECT settings FROM user WHERE id = ?", (owner_id,)).fetchone()
        if row is not None:
            settings = json.loads(row[0] or "{}")
            ui = settings.setdefault("ui", {})
            # Open WebUI applies a model's default tools only when exactly one
            # model is selected. Keep Roundtable available in the selector,
            # but default new chats to Core alone so its research tools attach.
            ui["models"] = ["little-oogway-core"]
            source.execute(
                "UPDATE user SET settings = ?, updated_at = ? WHERE id = ?",
                (json.dumps(settings), now, owner_id),
            )

        source.commit()
    finally:
        source.close()

    return backup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--owner-id")
    args = parser.parse_args()
    backup = configure(args.database, args.backup_dir, args.owner_id)
    print(f"Configured private Open WebUI model selector; backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
