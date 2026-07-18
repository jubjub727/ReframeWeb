ALTER TABLE idempotency_responses ADD COLUMN request_hash TEXT;
ALTER TABLE idempotency_responses
ADD COLUMN state TEXT NOT NULL DEFAULT 'completed'
CHECK(state IN ('pending', 'completed'));

CREATE INDEX workspaces_by_state_created
ON workspaces(state, created_at DESC);

CREATE INDEX memories_by_source_kind
ON memories(source_kind);
