from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class ContractKind(str, Enum):
    MEMORY_RELATIONSHIP = "memory_relationship"
    HYPOTHESIS = "hypothesis"
    CONTRADICTION = "contradiction"
    TRAINING_CANDIDATE = "training_candidate"
    ADAPTER = "adapter"
    EXPERIMENT = "experiment"


REQUIRED_FIELDS: dict[ContractKind, frozenset[str]] = {
    ContractKind.MEMORY_RELATIONSHIP: frozenset(
        {"relationship_id", "subject_memory_id", "object_memory_id", "relationship_type",
         "provenance", "evidence", "confidence", "review_status"}
    ),
    ContractKind.HYPOTHESIS: frozenset(
        {"hypothesis_id", "statement", "supporting_evidence", "conflicting_evidence",
         "predictions", "unresolved_questions", "review_status"}
    ),
    ContractKind.CONTRADICTION: frozenset(
        {"contradiction_id", "statement_ids", "evidence", "review_status"}
    ),
    ContractKind.TRAINING_CANDIDATE: frozenset(
        {"candidate_id", "source_references", "validation_status", "dataset_version",
         "permission_to_use"}
    ),
    ContractKind.ADAPTER: frozenset(
        {"adapter_id", "base_model", "training_configuration", "dataset_manifest",
         "checkpoints", "evaluation_results", "status"}
    ),
    ContractKind.EXPERIMENT: frozenset(
        {"experiment_id", "baseline", "candidate", "resource_measurements", "failures",
         "reproducibility", "status"}
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_record(kind: ContractKind, record: Mapping[str, Any]) -> None:
    missing = sorted(REQUIRED_FIELDS[kind] - record.keys())
    if missing:
        raise ValueError(f"{kind.value} is missing required fields: {', '.join(missing)}")
    confidence = record.get("confidence")
    if confidence is not None and not 0 <= float(confidence) <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if kind is ContractKind.CONTRADICTION and record.get("resolution") is not None:
        raise ValueError("contradictions may record review, but this interface never auto-resolves them")
    if kind is ContractKind.TRAINING_CANDIDATE and record.get("permission_to_use") is not True:
        # Recording an ineligible candidate is allowed; making it usable is not.
        record_status = str(record.get("validation_status"))
        if record_status == "approved":
            raise ValueError("a training candidate cannot be approved without permission_to_use=true")


class RegistryStore:
    """Append-only JSONL registry. It has no production side effects."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def append(self, kind: ContractKind, record: Mapping[str, Any]) -> dict[str, Any]:
        validate_record(kind, record)
        envelope = {
            "contract_version": 1,
            "kind": kind.value,
            "recorded_at": utc_now(),
            "record": dict(record),
        }
        target = self.root / f"{kind.value}.jsonl"
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n")
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
        return envelope

    def records(self, kind: ContractKind) -> list[dict[str, Any]]:
        target = self.root / f"{kind.value}.jsonl"
        if not target.exists():
            return []
        return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line]
