from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import psycopg
from psycopg.types.json import Jsonb

from .embeddings import vector_literal
from .consolidation import CanonicalCandidate, choose_canonical, shingle_containment
from .memory import TextChunk


@dataclass(frozen=True)
class MemoryHit:
    memory_id: str
    content: str
    source_locator: str
    source_ordinal: int
    lexical_score: float
    semantic_score: float
    combined_score: float


@dataclass(frozen=True)
class MemoryPair:
    left_id: str
    left_content: str
    left_locator: str
    left_ordinal: int
    right_id: str
    right_content: str
    right_locator: str
    right_ordinal: int
    vector_similarity: float


@dataclass(frozen=True)
class IngestionJob:
    id: str
    source_kind: str
    source_locator: str
    status: str
    stage: str
    attempt_count: int
    max_attempts: int
    options: dict[str, Any]
    result: dict[str, Any]
    error: str | None


class ConversationStore(Protocol):
    def register_participant(
        self, *, identity_key: str, name: str, kind: str, provider: str | None = None,
        model: str | None = None, metadata: dict[str, Any] | None = None,
    ) -> str: ...

    def create_conversation(
        self, *, title: str | None, provenance: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str: ...

    def create_round(
        self, *, conversation_id: str, ordinal: int,
        metadata: dict[str, Any] | None = None,
    ) -> str: ...

    def add_turn(
        self, *, round_id: str, participant_id: str, ordinal: int,
        status: str, content: str, provenance: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str: ...


@dataclass(frozen=True)
class TokenSpaceRepository:
    """Small persistence boundary for the TokenSpace v2 core tables."""

    dsn: str

    def _returning_id(self, query: str, parameters: tuple[object, ...]) -> str:
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, parameters)
                row = cursor.fetchone()
        if row is None:
            raise RuntimeError("TokenSpace insert returned no identifier")
        return str(row[0])

    def register_participant(
        self, *, identity_key: str, name: str, kind: str, provider: str | None = None,
        model: str | None = None, metadata: dict[str, Any] | None = None,
    ) -> str:
        return self._returning_id(
            """
            INSERT INTO tokenspace_v2.participants(
                identity_key, name, kind, provider, model, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (identity_key) DO UPDATE SET
                name = EXCLUDED.name,
                kind = EXCLUDED.kind,
                provider = EXCLUDED.provider,
                model = EXCLUDED.model,
                metadata = tokenspace_v2.participants.metadata || EXCLUDED.metadata
            RETURNING id
            """,
            (identity_key, name, kind, provider, model, Jsonb(metadata or {})),
        )

    def create_conversation(
        self, *, title: str | None, provenance: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self._returning_id(
            """
            INSERT INTO tokenspace_v2.conversations(title, provenance, metadata)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (title, Jsonb(provenance), Jsonb(metadata or {})),
        )

    def create_round(
        self, *, conversation_id: str, ordinal: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self._returning_id(
            """
            INSERT INTO tokenspace_v2.rounds(conversation_id, ordinal, metadata)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (conversation_id, ordinal, Jsonb(metadata or {})),
        )

    def add_turn(
        self, *, round_id: str, participant_id: str, ordinal: int,
        status: str, content: str, provenance: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self._returning_id(
            """
            INSERT INTO tokenspace_v2.turns(
                round_id, participant_id, ordinal, status, content, provenance, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (
                round_id, participant_id, ordinal, status, content,
                Jsonb(provenance), Jsonb(metadata or {}),
            ),
        )

    def import_source_chunks(
        self,
        *,
        source_type: str,
        source_locator: str,
        content_sha256: str,
        source_metadata: dict[str, Any],
        chunks: list[TextChunk],
        provenance_source: str = "transcript-import",
    ) -> tuple[str, int]:
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tokenspace_v2.memory_sources
                    SET is_active = false
                    WHERE source_type = %s AND source_locator = %s AND is_active
                      AND content_sha256 <> %s
                    """,
                    (source_type, source_locator, content_sha256),
                )
                cursor.execute(
                    """
                    INSERT INTO tokenspace_v2.memory_sources(
                        source_type, source_locator, content_sha256, metadata, is_active
                    ) VALUES (%s, %s, %s, %s, true)
                    ON CONFLICT (source_type, source_locator, content_sha256) DO UPDATE SET
                        metadata = tokenspace_v2.memory_sources.metadata || EXCLUDED.metadata,
                        is_active = true,
                        imported_at = now()
                    RETURNING id
                    """,
                    (source_type, source_locator, content_sha256, Jsonb(source_metadata)),
                )
                source_id = str(cursor.fetchone()[0])
                cursor.executemany(
                    """
                    INSERT INTO tokenspace_v2.memories(
                        source_id, source_ordinal, content, provenance, metadata
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (source_id, source_ordinal) DO UPDATE SET
                        content = EXCLUDED.content,
                        provenance = EXCLUDED.provenance,
                        metadata = EXCLUDED.metadata
                    """,
                    [
                        (
                            source_id,
                            chunk.ordinal,
                            chunk.content,
                            Jsonb(
                                {
                                    "source": provenance_source,
                                    "source_sha256": content_sha256,
                                    "source_locator": source_locator,
                                }
                            ),
                            Jsonb(
                                {
                                    "retrieval_only": True,
                                    "char_start": chunk.char_start,
                                    "char_end": chunk.char_end,
                                }
                            ),
                        )
                        for chunk in chunks
                    ],
                )
                cursor.execute(
                    """
                    DELETE FROM tokenspace_v2.memories
                    WHERE source_id = %s AND source_ordinal >= %s
                    """,
                    (source_id, len(chunks)),
                )
        return source_id, len(chunks)

    def unembedded_memories(
        self, *, model_digest: str, limit: int, source_id: str | None = None
    ) -> list[tuple[str, str]]:
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT memory.id, memory.content
                    FROM tokenspace_v2.memories AS memory
                    JOIN tokenspace_v2.memory_sources AS source ON source.id = memory.source_id
                    WHERE memory.source_id IS NOT NULL
                      AND source.is_active
                      AND (%s::uuid IS NULL OR memory.source_id = %s::uuid)
                      AND NOT EXISTS (
                          SELECT 1
                          FROM tokenspace_v2.memory_embeddings AS embedding
                          WHERE embedding.memory_id = memory.id
                            AND embedding.model_digest = %s
                      )
                    ORDER BY memory.source_id, memory.source_ordinal
                    LIMIT %s
                    """,
                    (source_id, source_id, model_digest, limit),
                )
                return [(str(row[0]), str(row[1])) for row in cursor.fetchall()]

    def store_embeddings(
        self,
        *,
        model: str,
        model_digest: str,
        embeddings: list[tuple[str, list[float]]],
    ) -> int:
        if not embeddings:
            return 0
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO tokenspace_v2.memory_embeddings(
                        memory_id, model, model_digest, dimensions, embedding, metadata
                    ) VALUES (%s, %s, %s, 768, %s::vector, %s)
                    ON CONFLICT (memory_id, model_digest) DO UPDATE SET
                        model = EXCLUDED.model,
                        dimensions = EXCLUDED.dimensions,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        created_at = now()
                    """,
                    [
                        (
                            memory_id,
                            model,
                            model_digest,
                            vector_literal(values),
                            Jsonb({"provider": "ollama"}),
                        )
                        for memory_id, values in embeddings
                    ],
                )
        return len(embeddings)

    def memory_status(self, *, model_digest: str | None = None) -> dict[str, int]:
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        (SELECT count(*) FROM tokenspace_v2.memory_sources WHERE is_active),
                        (SELECT count(*) FROM tokenspace_v2.memories AS m
                         JOIN tokenspace_v2.memory_sources AS s ON s.id = m.source_id
                         WHERE s.is_active),
                        (SELECT count(*) FROM tokenspace_v2.memory_embeddings AS e
                         JOIN tokenspace_v2.memories AS m ON m.id = e.memory_id
                         JOIN tokenspace_v2.memory_sources AS s ON s.id = m.source_id
                         WHERE s.is_active),
                        CASE WHEN %s::text IS NULL THEN 0 ELSE (
                            SELECT count(*)
                            FROM tokenspace_v2.memories AS memory
                            JOIN tokenspace_v2.memory_sources AS source
                              ON source.id = memory.source_id
                            WHERE source.is_active
                              AND NOT EXISTS (
                                  SELECT 1 FROM tokenspace_v2.memory_embeddings AS embedding
                                  WHERE embedding.memory_id = memory.id
                                    AND embedding.model_digest = %s
                              )
                        ) END
                    """,
                    (model_digest, model_digest),
                )
                row = cursor.fetchone()
        return {
            "sources": int(row[0]),
            "memories": int(row[1]),
            "embeddings": int(row[2]),
            "missing_for_model": int(row[3]),
        }

    def enqueue_ingestion_job(
        self,
        *,
        source_kind: str,
        source_locator: str,
        options: dict[str, Any] | None = None,
        requested_by: str = "local-user",
        max_attempts: int = 3,
    ) -> tuple[str, bool]:
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id FROM tokenspace_v2.ingestion_jobs
                    WHERE source_kind = %s AND source_locator = %s
                      AND status IN ('queued', 'processing')
                    ORDER BY created_at DESC LIMIT 1
                    FOR UPDATE
                    """,
                    (source_kind, source_locator),
                )
                row = cursor.fetchone()
                if row is not None:
                    return str(row[0]), False
                cursor.execute(
                    """
                    INSERT INTO tokenspace_v2.ingestion_jobs(
                        source_kind, source_locator, options, requested_by, max_attempts
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        source_kind, source_locator, Jsonb(options or {}),
                        requested_by, max_attempts,
                    ),
                )
                return str(cursor.fetchone()[0]), True

    def claim_ingestion_job(self) -> IngestionJob | None:
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tokenspace_v2.ingestion_jobs
                    SET status = 'failed', stage = 'failed', claimed_at = NULL,
                        error = COALESCE(error, 'Worker stopped during final attempt'),
                        updated_at = now()
                    WHERE status = 'processing'
                      AND claimed_at < now() - interval '30 minutes'
                      AND attempt_count >= max_attempts
                    """
                )
                cursor.execute(
                    """
                    UPDATE tokenspace_v2.ingestion_jobs
                    SET status = 'queued', stage = 'queued', claimed_at = NULL,
                        error = 'Recovered after an interrupted worker', updated_at = now()
                    WHERE status = 'processing'
                      AND claimed_at < now() - interval '30 minutes'
                      AND attempt_count < max_attempts
                    """
                )
                cursor.execute(
                    """
                    WITH candidate AS (
                        SELECT id FROM tokenspace_v2.ingestion_jobs
                        WHERE status = 'queued' AND not_before <= now()
                          AND attempt_count < max_attempts
                        ORDER BY created_at
                        LIMIT 1 FOR UPDATE SKIP LOCKED
                    )
                    UPDATE tokenspace_v2.ingestion_jobs AS job
                    SET status = 'processing', stage = 'fetching',
                        attempt_count = attempt_count + 1,
                        claimed_at = now(), updated_at = now(), error = NULL
                    FROM candidate WHERE job.id = candidate.id
                    RETURNING job.id, job.source_kind, job.source_locator,
                              job.status, job.stage, job.attempt_count,
                              job.max_attempts, job.options, job.result, job.error
                    """
                )
                row = cursor.fetchone()
        return self._ingestion_job(row) if row else None

    def set_ingestion_stage(self, job_id: str, stage: str) -> None:
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                """
                UPDATE tokenspace_v2.ingestion_jobs
                SET stage = %s, updated_at = now() WHERE id = %s AND status = 'processing'
                """,
                (stage, job_id),
            )

    def complete_ingestion_job(self, job_id: str, result: dict[str, Any]) -> None:
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                """
                UPDATE tokenspace_v2.ingestion_jobs
                SET status = 'complete', stage = 'complete', result = %s,
                    completed_at = now(), updated_at = now(), error = NULL
                WHERE id = %s
                """,
                (Jsonb(result), job_id),
            )

    def fail_ingestion_job(self, job_id: str, error: str) -> bool:
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tokenspace_v2.ingestion_jobs
                    SET status = CASE WHEN attempt_count < max_attempts THEN 'queued' ELSE 'failed' END,
                        stage = CASE WHEN attempt_count < max_attempts THEN 'queued' ELSE 'failed' END,
                        not_before = now() + make_interval(secs => LEAST(300, 5 * (2 ^ attempt_count)::integer)),
                        error = left(%s, 4000), claimed_at = NULL, updated_at = now()
                    WHERE id = %s
                    RETURNING status = 'queued'
                    """,
                    (error, job_id),
                )
                row = cursor.fetchone()
        return bool(row and row[0])

    def list_ingestion_jobs(self, limit: int = 20) -> list[IngestionJob]:
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, source_kind, source_locator, status, stage,
                           attempt_count, max_attempts, options, result, error
                    FROM tokenspace_v2.ingestion_jobs
                    ORDER BY created_at DESC LIMIT %s
                    """,
                    (limit,),
                )
                return [self._ingestion_job(row) for row in cursor.fetchall()]

    @staticmethod
    def _ingestion_job(row: tuple[object, ...]) -> IngestionJob:
        return IngestionJob(
            id=str(row[0]), source_kind=str(row[1]), source_locator=str(row[2]),
            status=str(row[3]), stage=str(row[4]), attempt_count=int(row[5]),
            max_attempts=int(row[6]), options=dict(row[7]), result=dict(row[8]),
            error=str(row[9]) if row[9] is not None else None,
        )

    def consolidate_exact_duplicates(self) -> dict[str, int]:
        """Record exact duplicate relationships without changing source memories."""
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT array_agg(
                        memory.id ORDER BY source.source_locator,
                        memory.source_ordinal, memory.id
                    )
                    FROM tokenspace_v2.memories AS memory
                    JOIN tokenspace_v2.memory_sources AS source
                      ON source.id = memory.source_id
                    WHERE source.is_active
                    GROUP BY memory.content
                    HAVING count(*) > 1
                    """
                )
                groups = [list(row[0]) for row in cursor.fetchall()]
                relations = [
                    (
                        group[0], related, "exact_duplicate", 1.0, "confirmed", "",
                        Jsonb({"method": "exact-content", "group_size": len(group)}),
                    )
                    for group in groups
                    for related in group[1:]
                ]
                cursor.executemany(
                    """
                    INSERT INTO tokenspace_v2.memory_relations(
                        canonical_memory_id, related_memory_id, relation_type,
                        confidence, review_status, model_digest, evidence
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (
                        canonical_memory_id, related_memory_id, relation_type, model_digest
                    ) DO UPDATE SET
                        confidence = EXCLUDED.confidence,
                        review_status = EXCLUDED.review_status,
                        evidence = EXCLUDED.evidence,
                        updated_at = now()
                    """,
                    relations,
                )
        return {"groups": len(groups), "relations": len(relations)}

    def consolidation_status(self) -> dict[str, int]:
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        count(*),
                        count(*) FILTER (WHERE relation_type = 'exact_duplicate'),
                        count(*) FILTER (WHERE relation_type = 'semantic_candidate'),
                        count(*) FILTER (WHERE review_status = 'proposed'),
                        count(*) FILTER (WHERE review_status = 'confirmed')
                    FROM tokenspace_v2.memory_relations
                    """
                )
                row = cursor.fetchone()
        return {
            "relations": int(row[0]),
            "exact_duplicates": int(row[1]),
            "semantic_candidates": int(row[2]),
            "proposed": int(row[3]),
            "confirmed": int(row[4]),
        }

    def propose_semantic_duplicates(
        self,
        *,
        model_digest: str,
        vector_threshold: float = 0.96,
        text_overlap_threshold: float = 0.80,
        neighbors: int = 10,
    ) -> dict[str, int]:
        """Record conservative cross-source near-duplicate candidates for review."""
        if not 0 <= vector_threshold <= 1 or not 0 <= text_overlap_threshold <= 1:
            raise ValueError("similarity thresholds must be between 0 and 1")
        if neighbors < 1 or neighbors > 50:
            raise ValueError("neighbors must be between 1 and 50")
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT memory.id, memory.content, source.source_locator,
                           memory.source_ordinal,
                           related.id, related.content, related_source.source_locator,
                           related.source_ordinal, nearest.vector_similarity
                    FROM tokenspace_v2.memory_embeddings AS embedding
                    JOIN tokenspace_v2.memories AS memory ON memory.id = embedding.memory_id
                    JOIN tokenspace_v2.memory_sources AS source ON source.id = memory.source_id
                    CROSS JOIN LATERAL (
                        SELECT candidate.memory_id,
                               1 - (candidate.embedding <=> embedding.embedding)
                                   AS vector_similarity
                        FROM tokenspace_v2.memory_embeddings AS candidate
                        JOIN tokenspace_v2.memories AS candidate_memory
                          ON candidate_memory.id = candidate.memory_id
                        WHERE candidate.model_digest = embedding.model_digest
                          AND candidate.memory_id <> embedding.memory_id
                          AND candidate_memory.source_id <> memory.source_id
                        ORDER BY candidate.embedding <=> embedding.embedding
                        LIMIT %s
                    ) AS nearest
                    JOIN tokenspace_v2.memories AS related
                      ON related.id = nearest.memory_id
                    JOIN tokenspace_v2.memory_sources AS related_source
                      ON related_source.id = related.source_id
                    WHERE embedding.model_digest = %s
                      AND source.is_active
                      AND related_source.is_active
                      AND nearest.vector_similarity >= %s
                    """,
                    (neighbors, model_digest, vector_threshold),
                )
                pairs = [
                    MemoryPair(
                        str(row[0]), str(row[1]), str(row[2]), int(row[3]),
                        str(row[4]), str(row[5]), str(row[6]), int(row[7]), float(row[8]),
                    )
                    for row in cursor.fetchall()
                ]

                proposals: dict[tuple[str, str], tuple[object, ...]] = {}
                for pair in pairs:
                    overlap = shingle_containment(pair.left_content, pair.right_content)
                    if overlap < text_overlap_threshold:
                        continue
                    left_key = (pair.left_locator, pair.left_ordinal, pair.left_id)
                    right_key = (pair.right_locator, pair.right_ordinal, pair.right_id)
                    if left_key <= right_key:
                        canonical_id, related_id = pair.left_id, pair.right_id
                    else:
                        canonical_id, related_id = pair.right_id, pair.left_id
                    confidence = 0.7 * pair.vector_similarity + 0.3 * overlap
                    proposals[(canonical_id, related_id)] = (
                        canonical_id,
                        related_id,
                        "semantic_candidate",
                        confidence,
                        "proposed",
                        model_digest,
                        Jsonb(
                            {
                                "method": "embedding-plus-five-token-shingle-containment",
                                "vector_similarity": pair.vector_similarity,
                                "text_overlap": overlap,
                                "vector_threshold": vector_threshold,
                                "text_overlap_threshold": text_overlap_threshold,
                            }
                        ),
                    )
                cursor.executemany(
                    """
                    INSERT INTO tokenspace_v2.memory_relations(
                        canonical_memory_id, related_memory_id, relation_type,
                        confidence, review_status, model_digest, evidence
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (
                        canonical_memory_id, related_memory_id, relation_type, model_digest
                    ) DO UPDATE SET
                        confidence = EXCLUDED.confidence,
                        evidence = EXCLUDED.evidence,
                        updated_at = now()
                    """,
                    list(proposals.values()),
                )
        return {"neighbors_scanned": len(pairs), "proposals": len(proposals)}

    def review_semantic_relation(
        self,
        *,
        relation_id: str,
        status: str,
        rationale: str,
        reviewer: str = "codex-assisted-manual-comparison",
    ) -> bool:
        if status not in {"confirmed", "rejected"}:
            raise ValueError("semantic relation review status must be confirmed or rejected")
        if not rationale.strip():
            raise ValueError("semantic relation review rationale cannot be empty")
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tokenspace_v2.memory_relations
                    SET review_status = %s,
                        evidence = evidence || jsonb_build_object(
                            'reviewer', %s::text,
                            'review_rationale', %s::text,
                            'reviewed_at', now()
                        ),
                        updated_at = now()
                    WHERE id = %s
                      AND relation_type = 'semantic_candidate'
                    """,
                    (status, reviewer, rationale.strip(), relation_id),
                )
                return cursor.rowcount == 1

    def apply_canonical_policy(self) -> dict[str, object]:
        """Orient confirmed relations toward the best retained retrieval copy."""
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT relation.id,
                           canonical.id, canonical.content,
                           canonical_source.source_locator, canonical.source_ordinal,
                           NULLIF(canonical_source.metadata->>'source_modified_at', '')::timestamptz,
                           related.id, related.content,
                           related_source.source_locator, related.source_ordinal,
                           NULLIF(related_source.metadata->>'source_modified_at', '')::timestamptz,
                           relation.preferred_memory_id
                    FROM tokenspace_v2.memory_relations AS relation
                    JOIN tokenspace_v2.memories AS canonical
                      ON canonical.id = relation.canonical_memory_id
                    JOIN tokenspace_v2.memory_sources AS canonical_source
                      ON canonical_source.id = canonical.source_id
                    JOIN tokenspace_v2.memories AS related
                      ON related.id = relation.related_memory_id
                    JOIN tokenspace_v2.memory_sources AS related_source
                      ON related_source.id = related.source_id
                    WHERE relation.review_status = 'confirmed'
                    ORDER BY relation.id
                    """
                )
                rows = cursor.fetchall()
                changed = 0
                reasons: dict[str, int] = {}
                for row in rows:
                    left = CanonicalCandidate(
                        str(row[1]), str(row[2]), str(row[3]), int(row[4]), row[5]
                    )
                    right = CanonicalCandidate(
                        str(row[6]), str(row[7]), str(row[8]), int(row[9]), row[10]
                    )
                    decision = choose_canonical(left, right)
                    reasons[decision.reason] = reasons.get(decision.reason, 0) + 1
                    if row[11] is None or str(row[11]) != decision.preferred.memory_id:
                        changed += 1
                    evidence = {
                        "canonical_policy": (
                            "explicit-conversation-timestamp, then passage-completeness, "
                            "then source-export-time, then stable-source-order"
                        ),
                        "canonical_reason": decision.reason,
                        "canonical_source_locator": decision.preferred.source_locator,
                        "canonical_source_ordinal": decision.preferred.source_ordinal,
                    }
                    if decision.conversation_timestamp is not None:
                        evidence["canonical_conversation_timestamp"] = (
                            decision.conversation_timestamp.isoformat()
                        )
                    cursor.execute(
                        """
                        UPDATE tokenspace_v2.memory_relations
                        SET preferred_memory_id = %s,
                            preference_reason = %s,
                            evidence = evidence || %s,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (
                            decision.preferred.memory_id,
                            decision.reason,
                            Jsonb(evidence),
                            row[0],
                        ),
                    )
        return {
            "relations_evaluated": len(rows),
            "preferences_changed": changed,
            "reasons": reasons,
        }

    def prefer_confirmed_memories(self, hits: list[MemoryHit]) -> list[MemoryHit]:
        """Collapse a result set only when both sides of a confirmed overlap are present."""
        if len(hits) < 2:
            return hits
        hit_ids = [hit.memory_id for hit in hits]
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT canonical_memory_id, related_memory_id, preferred_memory_id
                    FROM tokenspace_v2.memory_relations
                    WHERE review_status = 'confirmed'
                      AND preferred_memory_id IS NOT NULL
                      AND canonical_memory_id = ANY(%s::uuid[])
                      AND related_memory_id = ANY(%s::uuid[])
                    """,
                    (hit_ids, hit_ids),
                )
                relations = cursor.fetchall()
        suppressed: set[str] = set()
        for left_id, right_id, preferred_id in relations:
            left, right, preferred = str(left_id), str(right_id), str(preferred_id)
            suppressed.add(right if preferred == left else left)
        return [hit for hit in hits if hit.memory_id not in suppressed]

    def search_memories_lexical(self, query: str, *, limit: int = 5) -> list[MemoryHit]:
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH input AS (SELECT websearch_to_tsquery('english', %s) AS query)
                    SELECT memory.id, memory.content, source.source_locator,
                           memory.source_ordinal,
                           ts_rank_cd(memory.search_vector, input.query) AS lexical_score
                    FROM tokenspace_v2.memories AS memory
                    JOIN tokenspace_v2.memory_sources AS source ON source.id = memory.source_id
                    CROSS JOIN input
                    WHERE memory.search_vector @@ input.query
                      AND source.is_active
                    ORDER BY lexical_score DESC, memory.id
                    LIMIT %s
                    """,
                    (query, limit),
                )
                rows = cursor.fetchall()
        return [
            MemoryHit(str(row[0]), row[1], row[2], int(row[3]), float(row[4]), 0.0, float(row[4]))
            for row in rows
        ]

    def search_memories_hybrid(
        self,
        query: str,
        *,
        query_embedding: list[float],
        model_digest: str,
        limit: int = 5,
    ) -> list[MemoryHit]:
        vector = vector_literal(query_embedding)
        candidate_limit = max(limit * 10, 50)
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH input AS (
                        SELECT websearch_to_tsquery('english', %s) AS query,
                               %s::vector AS embedding
                    ),
                    lexical AS (
                        SELECT memory.id
                        FROM tokenspace_v2.memories AS memory
                        JOIN tokenspace_v2.memory_sources AS lexical_source
                          ON lexical_source.id = memory.source_id
                        CROSS JOIN input
                        WHERE memory.search_vector @@ input.query
                          AND lexical_source.is_active
                        ORDER BY ts_rank_cd(memory.search_vector, input.query) DESC
                        LIMIT %s
                    ),
                    semantic AS (
                        SELECT embedding.memory_id AS id
                        FROM tokenspace_v2.memory_embeddings AS embedding
                        JOIN tokenspace_v2.memories AS semantic_memory
                          ON semantic_memory.id = embedding.memory_id
                        JOIN tokenspace_v2.memory_sources AS semantic_source
                          ON semantic_source.id = semantic_memory.source_id
                        CROSS JOIN input
                        WHERE embedding.model_digest = %s
                          AND semantic_source.is_active
                        ORDER BY embedding.embedding <=> input.embedding
                        LIMIT %s
                    ),
                    candidates AS (
                        SELECT id FROM lexical UNION SELECT id FROM semantic
                    )
                    SELECT memory.id, memory.content, source.source_locator,
                           memory.source_ordinal,
                           ts_rank_cd(memory.search_vector, input.query) AS lexical_score,
                           1 - (embedding.embedding <=> input.embedding) AS semantic_score,
                           0.35 * ts_rank_cd(memory.search_vector, input.query)
                               + 0.65 * (1 - (embedding.embedding <=> input.embedding))
                               AS combined_score
                    FROM candidates
                    JOIN tokenspace_v2.memories AS memory ON memory.id = candidates.id
                    JOIN tokenspace_v2.memory_sources AS source ON source.id = memory.source_id
                    JOIN tokenspace_v2.memory_embeddings AS embedding
                      ON embedding.memory_id = memory.id
                     AND embedding.model_digest = %s
                    CROSS JOIN input
                    WHERE source.is_active
                    ORDER BY combined_score DESC, memory.id
                    LIMIT %s
                    """,
                    (
                        query, vector, candidate_limit, model_digest,
                        candidate_limit, model_digest, limit,
                    ),
                )
                rows = cursor.fetchall()
        return [
            MemoryHit(
                str(row[0]), row[1], row[2], int(row[3]),
                float(row[4]), float(row[5]), float(row[6]),
            )
            for row in rows
        ]

    def search_public_archive_hybrid(
        self,
        query: str,
        *,
        query_embedding: list[float],
        model_digest: str,
        limit: int = 5,
    ) -> list[MemoryHit]:
        """Search only active memories absorbed from published AnyKeyCafe URLs."""
        vector = vector_literal(query_embedding)
        candidate_limit = max(limit * 10, 50)
        public_source = """
            source.source_type = 'absorbed-url'
            AND (
                source.source_locator = 'https://anykeycafe.com/'
                OR source.source_locator LIKE 'https://anykeycafe.com/%%'
                OR source.source_locator = 'https://www.anykeycafe.com/'
                OR source.source_locator LIKE 'https://www.anykeycafe.com/%%'
            )
        """
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    WITH input AS (
                        SELECT websearch_to_tsquery('english', %s) AS query,
                               %s::vector AS embedding
                    ),
                    lexical AS (
                        SELECT memory.id
                        FROM tokenspace_v2.memories AS memory
                        JOIN tokenspace_v2.memory_sources AS source
                          ON source.id = memory.source_id
                        CROSS JOIN input
                        WHERE memory.search_vector @@ input.query
                          AND source.is_active AND {public_source}
                        ORDER BY ts_rank_cd(memory.search_vector, input.query) DESC
                        LIMIT %s
                    ),
                    semantic AS (
                        SELECT embedding.memory_id AS id
                        FROM tokenspace_v2.memory_embeddings AS embedding
                        JOIN tokenspace_v2.memories AS memory
                          ON memory.id = embedding.memory_id
                        JOIN tokenspace_v2.memory_sources AS source
                          ON source.id = memory.source_id
                        CROSS JOIN input
                        WHERE embedding.model_digest = %s
                          AND source.is_active AND {public_source}
                        ORDER BY embedding.embedding <=> input.embedding
                        LIMIT %s
                    ),
                    candidates AS (
                        SELECT id FROM lexical UNION SELECT id FROM semantic
                    )
                    SELECT memory.id, memory.content, source.source_locator,
                           memory.source_ordinal,
                           ts_rank_cd(memory.search_vector, input.query) AS lexical_score,
                           1 - (embedding.embedding <=> input.embedding) AS semantic_score,
                           0.35 * ts_rank_cd(memory.search_vector, input.query)
                               + 0.65 * (1 - (embedding.embedding <=> input.embedding))
                               AS combined_score
                    FROM candidates
                    JOIN tokenspace_v2.memories AS memory ON memory.id = candidates.id
                    JOIN tokenspace_v2.memory_sources AS source ON source.id = memory.source_id
                    JOIN tokenspace_v2.memory_embeddings AS embedding
                      ON embedding.memory_id = memory.id
                     AND embedding.model_digest = %s
                    CROSS JOIN input
                    WHERE source.is_active AND {public_source}
                    ORDER BY combined_score DESC, memory.id
                    LIMIT %s
                    """,
                    (
                        query, vector, candidate_limit, model_digest,
                        candidate_limit, model_digest, limit,
                    ),
                )
                rows = cursor.fetchall()
        return [
            MemoryHit(
                str(row[0]), row[1], row[2], int(row[3]),
                float(row[4]), float(row[5]), float(row[6]),
            )
            for row in rows
        ]
