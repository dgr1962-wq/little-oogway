WITH ranked AS (
    SELECT
        id,
        first_value(id) OVER (
            PARTITION BY kind, name, coalesce(provider, ''), coalesce(model, '')
            ORDER BY created_at, id
        ) AS canonical_id
    FROM tokenspace_v2.participants
)
UPDATE tokenspace_v2.turns AS turn
SET participant_id = ranked.canonical_id
FROM ranked
WHERE turn.participant_id = ranked.id
  AND ranked.id <> ranked.canonical_id;

WITH duplicates AS (
    SELECT
        id,
        row_number() OVER (
            PARTITION BY kind, name, coalesce(provider, ''), coalesce(model, '')
            ORDER BY created_at, id
        ) AS position
    FROM tokenspace_v2.participants
)
DELETE FROM tokenspace_v2.participants AS participant
USING duplicates
WHERE participant.id = duplicates.id
  AND duplicates.position > 1;

ALTER TABLE tokenspace_v2.participants
ADD COLUMN identity_key text;

UPDATE tokenspace_v2.participants
SET identity_key = CASE
    WHEN kind = 'model' THEN concat('model:', provider, ':', model, ':', name)
    ELSE concat(kind, ':', name)
END;

ALTER TABLE tokenspace_v2.participants
ALTER COLUMN identity_key SET NOT NULL,
ADD CONSTRAINT participants_identity_key_nonempty
    CHECK (length(trim(identity_key)) > 0),
ADD CONSTRAINT participants_identity_key_unique UNIQUE (identity_key);
