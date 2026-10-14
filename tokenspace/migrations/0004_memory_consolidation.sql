CREATE TABLE tokenspace_v2.memory_relations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_memory_id uuid NOT NULL
        REFERENCES tokenspace_v2.memories(id) ON DELETE RESTRICT,
    related_memory_id uuid NOT NULL
        REFERENCES tokenspace_v2.memories(id) ON DELETE RESTRICT,
    relation_type text NOT NULL CHECK (
        relation_type IN ('exact_duplicate', 'semantic_candidate', 'supersedes')
    ),
    confidence double precision NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    review_status text NOT NULL DEFAULT 'proposed' CHECK (
        review_status IN ('proposed', 'confirmed', 'rejected')
    ),
    model_digest text NOT NULL DEFAULT '',
    evidence jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(evidence) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (canonical_memory_id <> related_memory_id),
    UNIQUE (canonical_memory_id, related_memory_id, relation_type, model_digest)
);

CREATE INDEX memory_relations_related_idx
ON tokenspace_v2.memory_relations(related_memory_id, relation_type, review_status);
