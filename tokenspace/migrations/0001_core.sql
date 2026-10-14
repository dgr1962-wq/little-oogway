CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA tokenspace_v2;
CREATE TABLE tokenspace_v2.participants (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 name text NOT NULL CHECK (length(trim(name)) > 0),
 kind text NOT NULL CHECK (kind IN ('human', 'model', 'tool', 'system')),
 provider text, model text,
 metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata) = 'object'),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE tokenspace_v2.conversations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), title text,
 provenance jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(provenance) = 'object'),
 metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata) = 'object'),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE tokenspace_v2.rounds (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 conversation_id uuid NOT NULL REFERENCES tokenspace_v2.conversations(id),
 ordinal integer NOT NULL CHECK (ordinal >= 0),
 metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata) = 'object'),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (conversation_id, ordinal)
);
CREATE TABLE tokenspace_v2.turns (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 round_id uuid NOT NULL REFERENCES tokenspace_v2.rounds(id),
 participant_id uuid NOT NULL REFERENCES tokenspace_v2.participants(id),
 ordinal integer NOT NULL CHECK (ordinal >= 0),
 status text NOT NULL DEFAULT 'completed' CHECK (status IN ('completed', 'failed', 'skipped')),
 content text NOT NULL,
 provenance jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(provenance) = 'object'),
 metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata) = 'object'),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (round_id, ordinal)
);
CREATE INDEX turns_participant_idx ON tokenspace_v2.turns(participant_id);
CREATE TABLE tokenspace_v2.memories (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 source_turn_id uuid REFERENCES tokenspace_v2.turns(id),
 content text NOT NULL CHECK (length(trim(content)) > 0),
 provenance jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(provenance) = 'object'),
 metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata) = 'object'),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX memories_source_turn_idx ON tokenspace_v2.memories(source_turn_id);
