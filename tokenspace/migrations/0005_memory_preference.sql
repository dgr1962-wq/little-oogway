ALTER TABLE tokenspace_v2.memory_relations
ADD COLUMN preferred_memory_id uuid
    REFERENCES tokenspace_v2.memories(id) ON DELETE RESTRICT,
ADD COLUMN preference_reason text,
ADD CONSTRAINT memory_relations_preferred_is_member CHECK (
    preferred_memory_id IS NULL
    OR preferred_memory_id IN (canonical_memory_id, related_memory_id)
),
ADD CONSTRAINT memory_relations_preference_complete CHECK (
    (preferred_memory_id IS NULL AND preference_reason IS NULL)
    OR (
        preferred_memory_id IS NOT NULL
        AND preference_reason IS NOT NULL
        AND length(trim(preference_reason)) > 0
    )
);

CREATE INDEX memory_relations_preferred_idx
ON tokenspace_v2.memory_relations(preferred_memory_id)
WHERE preferred_memory_id IS NOT NULL;
