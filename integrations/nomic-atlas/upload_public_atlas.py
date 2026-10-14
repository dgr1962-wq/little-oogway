#!/usr/bin/env python3
"""Upload the filtered public AnyKeyCafe memory field to Nomic Atlas."""

from __future__ import annotations

import json
from pathlib import Path

import nomic
import numpy as np
import pandas as pd
from nomic import atlas
from nomic.data_inference import NomicTopicOptions


ROOT = Path(__file__).resolve().parent
TOKEN_PATH = ROOT / ".nomic-token"
EXPORT_PATH = ROOT / "export" / "anykey-public-memory-atlas.jsonl"


def main() -> None:
    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    nomic.login(token)

    records: list[dict] = []
    vectors: list[list[float]] = []
    with EXPORT_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            vectors.append(row.pop("embedding"))
            records.append(row)

    embeddings = np.asarray(vectors, dtype=np.float32)
    if embeddings.shape != (2000, 768):
        raise ValueError(f"Unexpected embedding matrix: {embeddings.shape}")
    if not all("anykeycafe.com" in row["source_url"] for row in records):
        raise ValueError("Export contains a non-public source URL")

    data = pd.DataFrame.from_records(records)
    dataset = atlas.map_data(
        data=data,
        embeddings=embeddings,
        identifier="little-oogway-public-anykeycafe-memory-field",
        description=(
            "A public semantic map of 2,000 memory fragments absorbed from "
            "AnyKeyCafe.com by Little Oogway. Local files, conversations, "
            "private memories, and original database identifiers are excluded."
        ),
        id_field="point_id",
        is_public=True,
        topic_model=NomicTopicOptions(
            build_topic_model=True,
            topic_label_field="text",
        ),
        duplicate_detection=True,
    )
    print(dataset.identifier)


if __name__ == "__main__":
    main()
