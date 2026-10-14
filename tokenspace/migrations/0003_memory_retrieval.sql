CREATE TABLE tokenspace_v2.memory_sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type text NOT NULL CHECK (length(trim(source_type)) > 0),
    source_locator text NOT NULL CHECK (length(trim(source_locator)) > 0),
    content_sha256 text NOT NULL UNIQUE CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata) = 'object'),
    imported_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE tokenspace_v2.memories
ADD COLUMN source_id uuid REFERENCES tokenspace_v2.memory_sources(id),
ADD COLUMN source_ordinal integer CHECK (source_ordinal >= 0),
ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
ADD CONSTRAINT memories_source_position_complete CHECK (
    (source_id IS NULL AND source_ordinal IS NULL)
    OR (source_id IS NOT NULL AND source_ordinal IS NOT NULL)
),
ADD CONSTRAINT memories_source_position_unique UNIQUE (source_id, source_ordinal);

CREATE INDEX memories_search_vector_idx
ON tokenspace_v2.memories USING gin(search_vector);

CREATE TABLE tokenspace_v2.memory_embeddings (
    memory_id uuid NOT NULL REFERENCES tokenspace_v2.memories(id) ON DELETE CASCADE,
    model text NOT NULL CHECK (length(trim(model)) > 0),
    model_digest text NOT NULL CHECK (length(trim(model_digest)) > 0),
    dimensions integer NOT NULL CHECK (dimensions = 768),
    embedding vector(768) NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (memory_id, model_digest)
);

CREATE INDEX memory_embeddings_cosine_idx
ON tokenspace_v2.memory_embeddings
USING hnsw (embedding vector_cosine_ops);
