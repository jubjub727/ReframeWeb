CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
INSERT OR IGNORE INTO schema_version(version) VALUES (1);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    source_kind TEXT NOT NULL DEFAULT 'directory',
    manifest_id TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('active', 'closed')),
    worktree_path TEXT NOT NULL,
    head_manifest TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_sources (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    memory_id TEXT NOT NULL REFERENCES memories(id),
    ordinal INTEGER NOT NULL,
    PRIMARY KEY(workspace_id, memory_id)
);

CREATE TABLE IF NOT EXISTS workspace_scratch (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    PRIMARY KEY(workspace_id, path)
);

CREATE TABLE IF NOT EXISTS baselines (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    hash TEXT NOT NULL,
    size INTEGER NOT NULL,
    source_kind TEXT NOT NULL,
    source_ref TEXT,
    PRIMARY KEY(workspace_id, path)
);

CREATE TABLE IF NOT EXISTS journal_events (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    size INTEGER,
    scanned_at INTEGER NOT NULL,
    PRIMARY KEY(workspace_id, path)
);

CREATE TABLE IF NOT EXISTS manifests (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    parent_id TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS manifest_entries (
    manifest_id TEXT NOT NULL REFERENCES manifests(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    hash TEXT NOT NULL,
    size INTEGER NOT NULL,
    source_kind TEXT NOT NULL,
    source_ref TEXT,
    PRIMARY KEY(manifest_id, path)
);

CREATE INDEX IF NOT EXISTS journal_by_workspace ON journal_events(workspace_id, path);
CREATE INDEX IF NOT EXISTS manifest_entries_by_manifest ON manifest_entries(manifest_id, path);

CREATE TABLE IF NOT EXISTS idempotency_responses (
    key TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
