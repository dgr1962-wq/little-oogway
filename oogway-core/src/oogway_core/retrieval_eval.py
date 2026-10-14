from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from .repository import MemoryHit


class Retriever(Protocol):
    def retrieve(self, query: str, *, limit: int = 5) -> list[MemoryHit]: ...


@dataclass(frozen=True)
class EvaluationReport:
    results: list[dict[str, Any]]
    positive_hit_rate: float
    mean_reciprocal_rank: float
    negative_rejection_rate: float
    average_source_diversity: float
    average_latency_ms: float
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "results": self.results,
            "metrics": {
                "positive_hit_rate": self.positive_hit_rate,
                "mean_reciprocal_rank": self.mean_reciprocal_rank,
                "negative_rejection_rate": self.negative_rejection_rate,
                "average_source_diversity": self.average_source_diversity,
                "average_latency_ms": self.average_latency_ms,
            },
            "passed": self.passed,
        }


def load_evaluation(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document.get("cases"), list) or not document["cases"]:
        raise ValueError("evaluation must contain a non-empty cases list")
    return document


def evaluate_retrieval(retriever: Retriever, specification: dict[str, Any]) -> EvaluationReport:
    limit = int(specification.get("limit", 5))
    results: list[dict[str, Any]] = []
    positive_ranks: list[int | None] = []
    negative_passes: list[bool] = []
    diversities: list[float] = []
    latencies: list[float] = []

    for case in specification["cases"]:
        started = perf_counter()
        hits = retriever.retrieve(case["query"], limit=limit)
        latency_ms = (perf_counter() - started) * 1000
        latencies.append(latency_ms)
        if hits:
            diversities.append(len({hit.source_locator for hit in hits}) / len(hits))

        expects_results = bool(case.get("expected_sources"))
        rank = None
        if expects_results:
            expected = set(case["expected_sources"])
            rank = next(
                (index for index, hit in enumerate(hits, start=1) if hit.source_locator in expected),
                None,
            )
            positive_ranks.append(rank)
            passed = rank is not None
        else:
            passed = not hits
            negative_passes.append(passed)

        results.append(
            {
                "id": case["id"],
                "passed": passed,
                "rank": rank,
                "result_count": len(hits),
                "top_score": hits[0].combined_score if hits else None,
                "sources": [hit.source_locator for hit in hits],
                "latency_ms": round(latency_ms, 2),
            }
        )

    hit_rate = sum(rank is not None for rank in positive_ranks) / len(positive_ranks)
    mrr = sum(1 / rank for rank in positive_ranks if rank is not None) / len(positive_ranks)
    rejection_rate = sum(negative_passes) / len(negative_passes) if negative_passes else 1.0
    diversity = sum(diversities) / len(diversities) if diversities else 1.0
    latency = sum(latencies) / len(latencies)
    thresholds = specification.get("thresholds", {})
    passed = (
        hit_rate >= float(thresholds.get("positive_hit_rate", 1.0))
        and mrr >= float(thresholds.get("mean_reciprocal_rank", 0.8))
        and rejection_rate >= float(thresholds.get("negative_rejection_rate", 1.0))
        and diversity >= float(thresholds.get("average_source_diversity", 0.6))
    )
    return EvaluationReport(
        results=results,
        positive_hit_rate=hit_rate,
        mean_reciprocal_rank=mrr,
        negative_rejection_rate=rejection_rate,
        average_source_diversity=diversity,
        average_latency_ms=latency,
        passed=passed,
    )
