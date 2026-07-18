CREATE TABLE checkpoint_publications (
    manifest_id TEXT PRIMARY KEY REFERENCES manifests(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    workspace_name TEXT NOT NULL,
    base_memory_ids_json TEXT NOT NULL,
    retained_count INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('pending', 'published')),
    memory_id TEXT,
    created_at INTEGER NOT NULL,
    published_at INTEGER,
    CHECK(
        (state = 'pending' AND memory_id IS NULL AND published_at IS NULL)
        OR (state = 'published' AND memory_id IS NOT NULL AND published_at IS NOT NULL)
    )
);

CREATE INDEX checkpoint_publications_by_state
ON checkpoint_publications(state, created_at);
