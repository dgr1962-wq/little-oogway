#!/usr/bin/env python3
"""Export a deterministic, public-only TokenSpace sample for Nomic Atlas.

The query is read-only and accepts only active HTTPS sources on the public
AnyKeyCafe hostnames. Local files, conversations, turns, and legacy schemas are
excluded. Database UUIDs are replaced with stable one-way point identifiers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import psycopg

from oogway_core.cli import development_dsn


ALLOWED_HOSTS = {"anykeycafe.com", "www.anykeycafe.com"}


def parse_vector(value: str) -> list[float]:
    text = value.strip()
    if not (text.startswith("[") and text.endswith("]")):
        raise ValueError("Unexpected pgvector text representation")
    vector = [float(item) for item in text[1:-1].split(",")]
    if len(vector) != 768:
        raise ValueError(f"Expected 768 dimensions, received {len(vector)}")
    return vector


def is_public_anykey_url(locator: str) -> bool:
    parsed = urlsplit(locator)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS


def point_id(memory_id: str) -> str:
    return hashlib.sha256(f"anykey-atlas:{memory_id}".encode()).hexdigest()[:24]


def deterministic_sample(rows: list[dict], limit: int) -> list[dict]:
    if limit <= 0 or len(rows) <= limit:
        return sorted(rows, key=lambda row: (row["source_url"], row["source_ordinal"]))

    by_source: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_source[row["source_url"]].append(row)
    for source_rows in by_source.values():
        source_rows.sort(key=lambda row: hashlib.sha256(row["point_id"].encode()).digest())

    selected = [source_rows[0] for source_rows in by_source.values()]
    selected_ids = {row["point_id"] for row in selected}
    remainder = [row for row in rows if row["point_id"] not in selected_ids]
    remainder.sort(key=lambda row: hashlib.sha256(row["point_id"].encode()).digest())
    selected.extend(remainder[: max(0, limit - len(selected))])
    return sorted(selected, key=lambda row: (row["source_url"], row["source_ordinal"]))


def load_public_rows() -> list[dict]:
    query = """
        SELECT DISTINCT ON (memory.id)
            memory.id::text,
            memory.source_ordinal,
            memory.content,
            source.source_type,
            source.source_locator,
            source.imported_at,
            embedding.model,
            embedding.model_digest,
            embedding.embedding::text
        FROM tokenspace_v2.memories AS memory
        JOIN tokenspace_v2.memory_sources AS source ON source.id = memory.source_id
        JOIN tokenspace_v2.memory_embeddings AS embedding
          ON embedding.memory_id = memory.id
        WHERE source.is_active
          AND source.source_type = 'absorbed-url'
          AND (
              source.source_locator = 'https://anykeycafe.com/'
              OR source.source_locator LIKE 'https://anykeycafe.com/%'
              OR source.source_locator = 'https://www.anykeycafe.com/'
              OR source.source_locator LIKE 'https://www.anykeycafe.com/%'
          )
        ORDER BY memory.id, embedding.created_at DESC
    """
    result: list[dict] = []
    with psycopg.connect(development_dsn()) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute(query)
            for row in cursor:
                locator = str(row[4])
                if not is_public_anykey_url(locator):
                    raise RuntimeError(f"Public-source guard rejected {locator!r}")
                raw_content = str(row[2]).strip()
                result.append(
                    {
                        "point_id": point_id(str(row[0])),
                        "source_ordinal": int(row[1]),
                        "text": raw_content[:4000],
                        "source_type": str(row[3]),
                        "source_url": locator,
                        "source_path": urlsplit(locator).path or "/",
                        "imported_at": row[5].isoformat(),
                        "embedding_model": str(row[6]),
                        "embedding_digest": str(row[7]),
                        "embedding": parse_vector(str(row[8])),
                    }
                )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=2000)
    args = parser.parse_args()

    rows = load_public_rows()
    sample = deterministic_sample(rows, args.limit)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data_path = args.output_dir / "anykey-public-memory-atlas.jsonl"
    manifest_path = args.output_dir / "manifest.json"

    with data_path.open("w", encoding="utf-8") as handle:
        for row in sample:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "First Nomic Atlas snapshot of public AnyKeyCafe memory embeddings",
        "privacy_boundary": "Active HTTPS AnyKeyCafe URL sources only; no local files or conversations",
        "database": "tokenspace_v2_dev",
        "legacy_database_accessed": False,
        "available_public_points": len(rows),
        "exported_points": len(sample),
        "public_sources": len({row["source_url"] for row in sample}),
        "dimensions": 768,
        "data_sha256": digest,
        "data_file": data_path.name,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
