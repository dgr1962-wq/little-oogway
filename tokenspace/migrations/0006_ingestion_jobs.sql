ALTER TABLE tokenspace_v2.memory_sources
ADD COLUMN is_active boolean NOT NULL DEFAULT true;

CREATE UNIQUE INDEX memory_sources_one_active_locator_idx
ON tokenspace_v2.memory_sources(source_type, source_locator)
WHERE is_active;

CREATE TABLE tokenspace_v2.ingestion_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_kind text NOT NULL CHECK (source_kind IN ('local_file', 'url')),
    source_locator text NOT NULL CHECK (btrim(source_locator) <> ''),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'complete', 'failed')),
    stage text NOT NULL DEFAULT 'queued'
        CHECK (stage IN (
            'queued', 'fetching', 'normalizing', 'chunking',
            'embedding', 'indexing', 'complete', 'failed'
        )),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 20),
    not_before timestamptz NOT NULL DEFAULT now(),
    options jsonb NOT NULL DEFAULT '{}'::jsonb,
    result jsonb NOT NULL DEFAULT '{}'::jsonb,
    error text,
    requested_by text NOT NULL DEFAULT 'local-user',
    claimed_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ingestion_jobs_one_active_source_idx
ON tokenspace_v2.ingestion_jobs(source_kind, source_locator)
WHERE status IN ('queued', 'processing');

CREATE INDEX ingestion_jobs_ready_idx
ON tokenspace_v2.ingestion_jobs(status, not_before, created_at)
WHERE status = 'queued';

