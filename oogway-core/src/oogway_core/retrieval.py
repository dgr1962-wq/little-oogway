from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .embeddings import OllamaEmbeddingModel
from .repository import MemoryHit, TokenSpaceRepository


@dataclass
class HybridMemoryRetriever:
    repository: TokenSpaceRepository
    embedding_model: OllamaEmbeddingModel
    minimum_score: float = 0.40
    minimum_semantic_only_score: float = 0.47
    candidate_multiplier: int = 5
    adjacent_chunk_distance: int = 1
    max_chunks_per_source: int = 2
    _model_digest: str | None = None

    def retrieve(self, query: str, *, limit: int = 5) -> list[MemoryHit]:
        if limit < 1:
            return []
        if self._model_digest is None:
            self._model_digest = self.embedding_model.digest()
        embedding = self.embedding_model.embed([f"search_query: {query}"])[0]
        candidates = self.repository.search_memories_hybrid(
            query,
            query_embedding=embedding,
            model_digest=self._model_digest,
            limit=max(limit * self.candidate_multiplier, limit),
        )
        candidates = self.repository.prefer_confirmed_memories(candidates)
        return select_diverse_hits(
            candidates,
            limit=limit,
            minimum_score=self.minimum_score,
            minimum_semantic_only_score=self.minimum_semantic_only_score,
            adjacent_chunk_distance=self.adjacent_chunk_distance,
            max_chunks_per_source=self.max_chunks_per_source,
        )


@dataclass
class PublicArchiveRetriever(HybridMemoryRetriever):
    """Hybrid retrieval restricted at the SQL boundary to public archive URLs."""

    def retrieve(self, query: str, *, limit: int = 5) -> list[MemoryHit]:
        if limit < 1:
            return []
        if self._model_digest is None:
            self._model_digest = self.embedding_model.digest()
        embedding = self.embedding_model.embed([f"search_query: {query}"])[0]
        candidates = self.repository.search_public_archive_hybrid(
            query,
            query_embedding=embedding,
            model_digest=self._model_digest,
            limit=max(limit * self.candidate_multiplier, limit),
        )
        candidates = self.repository.prefer_confirmed_memories(candidates)
        return select_diverse_hits(
            candidates,
            limit=limit,
            minimum_score=self.minimum_score,
            minimum_semantic_only_score=self.minimum_semantic_only_score,
            adjacent_chunk_distance=self.adjacent_chunk_distance,
            max_chunks_per_source=self.max_chunks_per_source,
        )


def select_diverse_hits(
    candidates: list[MemoryHit],
    *,
    limit: int,
    minimum_score: float = 0.40,
    minimum_semantic_only_score: float = 0.47,
    adjacent_chunk_distance: int = 1,
    max_chunks_per_source: int = 2,
) -> list[MemoryHit]:
    """Reject weak and substantially overlapping results while preserving rank."""
    selected: list[MemoryHit] = []
    source_ordinals: dict[str, list[int]] = {}
    content_fingerprints: set[str] = set()
    for hit in candidates:
        if hit.combined_score < minimum_score:
            continue
        if hit.lexical_score <= 0 and hit.combined_score < minimum_semantic_only_score:
            continue
        normalized = " ".join(hit.content.split()).casefold()
        fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if fingerprint in content_fingerprints:
            continue
        ordinals = source_ordinals.setdefault(hit.source_locator, [])
        if len(ordinals) >= max_chunks_per_source:
            continue
        if any(
            abs(hit.source_ordinal - ordinal) <= adjacent_chunk_distance
            for ordinal in ordinals
        ):
            continue
        selected.append(hit)
        content_fingerprints.add(fingerprint)
        ordinals.append(hit.source_ordinal)
        if len(selected) == limit:
            break
    return selected
