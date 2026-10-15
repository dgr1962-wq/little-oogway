#!/usr/bin/env python3
"""Idempotently register Core's confirmation-gated Roundtable council tool."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path


TOOL_ID = "little_oogway_roundtable_council"
MODEL_ID = "little-oogway-core"
SPECS = [
    {
        "name": "prepare_roundtable",
        "description": "Create a no-contact Roundtable preflight and display the exact external docket for administrator review.",
        "parameters": {
            "type": "object",
            "properties": {
                "motion": {"type": "string"},
                "document_packet": {"type": "string", "default": ""},
            },
            "required": ["motion"],
        },
    },
    {
        "name": "confirm_roundtable",
        "description": "Contact the configured participants for an existing preflight only after exact typed administrator confirmation.",
        "parameters": {
            "type": "object",
            "properties": {
                "preflight_id": {"type": "string"},
                "typed_confirmation": {"type": "string"},
            },
            "required": ["preflight_id", "typed_confirmation"],
        },
    },
    {
        "name": "roundtable_status",
        "description": "Read the current state of a previously started Roundtable round.",
        "parameters": {
            "type": "object",
            "properties": {"round_id": {"type": "string"}},
            "required": ["round_id"],
        },
    },
    {
        "name": "resume_roundtable",
        "description": "Resume a deferred round with the administrator's explicit ruling.",
        "parameters": {
            "type": "object",
            "properties": {
                "round_id": {"type": "string"},
                "operator_ruling": {"type": "string"},
            },
            "required": ["round_id", "operator_ruling"],
        },
    },
]
META = {
    "description": "Admin-only, confirmation-gated access from Oogway Core to the local AI Roundtable.",
    "manifest": {},
    "has_user_valves": False,
}
PROTOCOL = """
You may ask the AI Roundtable for help through the Roundtable council tool only
in this authenticated private administrator session. First call
prepare_roundtable. That action contacts nobody and returns the exact external
docket plus a preflight ID. Never call confirm_roundtable unless Darren's
current message contains the exact typed confirmation phrase requested by the
tool. A general request such as "ask the Roundtable" authorizes preparation,
not external contact. Document packets are shared externally verbatim after
confirmation: extract only the necessary passages, label provenance, omit
credentials and private TokenSpace memories, and let Darren inspect the
preflight. Use roundtable_status to observe an active round. Resume a deferred
round only with Darren's explicit ruling; do not invent one. The public website
and the Roundtable model do not receive this Core tool.
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    database = args.database.resolve(strict=True)
    content = args.content.resolve(strict=True).read_text(encoding="utf-8")
    if args.backup:
        backup = args.backup.resolve()
        backup.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        destination = sqlite3.connect(backup)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()

    now = int(time.time())
    connection = sqlite3.connect(database, timeout=30)
    try:
        connection.execute("BEGIN IMMEDIATE")
        owner = connection.execute(
            "SELECT id FROM user WHERE role='admin' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if owner is None:
            raise RuntimeError("Open WebUI has no administrative tool owner")
        existing = connection.execute(
            "SELECT created_at FROM tool WHERE id=?", (TOOL_ID,)
        ).fetchone()
        created_at = existing[0] if existing else now
        connection.execute(
            """
            INSERT INTO tool(id,user_id,name,content,specs,meta,created_at,updated_at,valves)
            VALUES(?,?,?,?,?,?,?,?,NULL)
            ON CONFLICT(id) DO UPDATE SET user_id=excluded.user_id,name=excluded.name,
                content=excluded.content,specs=excluded.specs,meta=excluded.meta,
                updated_at=excluded.updated_at
            """,
            (
                TOOL_ID,
                owner[0],
                "Little Oogway Roundtable Council",
                content,
                json.dumps(SPECS),
                json.dumps(META),
                created_at,
                now,
            ),
        )
        row = connection.execute(
            "SELECT meta,params FROM model WHERE id=?", (MODEL_ID,)
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Open WebUI model {MODEL_ID!r} does not exist")
        meta, params = json.loads(row[0] or "{}"), json.loads(row[1] or "{}")
        tool_ids = list(meta.get("toolIds") or [])
        if TOOL_ID not in tool_ids:
            tool_ids.append(TOOL_ID)
        meta["toolIds"] = tool_ids
        system = str(params.get("system") or "").rstrip()
        if PROTOCOL not in system:
            params["system"] = f"{system}\n\n{PROTOCOL}".strip()
        connection.execute(
            "UPDATE model SET meta=?,params=?,updated_at=? WHERE id=?",
            (json.dumps(meta), json.dumps(params), now, MODEL_ID),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print(f"registered {TOOL_ID} with {MODEL_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
