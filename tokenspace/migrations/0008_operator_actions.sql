CREATE TABLE tokenspace_v2.operator_actions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    action_type text NOT NULL CHECK (action_type IN (
        'command', 'write_file', 'move_file', 'trash_file',
        'user_service', 'docker', 'git'
    )),
    risk_level text NOT NULL CHECK (risk_level IN ('green', 'yellow', 'red')),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'approved', 'rejected', 'running',
        'complete', 'failed', 'cancelled'
    )),
    arguments jsonb NOT NULL DEFAULT '{}'::jsonb,
    reason text NOT NULL CHECK (btrim(reason) <> ''),
    requested_by text NOT NULL DEFAULT 'little-oogway',
    requested_via text NOT NULL DEFAULT 'private-open-webui',
    approved_by text,
    approved_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    result jsonb NOT NULL DEFAULT '{}'::jsonb,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX operator_actions_pending_idx
ON tokenspace_v2.operator_actions(status, created_at)
WHERE status = 'pending';

