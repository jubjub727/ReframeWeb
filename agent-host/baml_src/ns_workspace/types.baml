enum Materialization {
    Lazy,
    Prefetch,
    DirectDisk,
}

enum Retention {
    Discard,
    CacheOnly,
    Checkpoint,
    Always,
}

class FilesystemMemoryReference {
    id: string,
    title: string,
    description: string,
    tags: string[],
}

class WorkspacePolicyRule {
    path_glob: string,
    materialization: Materialization,
    retention: Retention,
    provenance: string,
}

class WorkspacePlan {
    memory_ids: string[],
    prefetch_paths: string[],
    rules: WorkspacePolicyRule[],
}

class WorkspaceChange {
    path: string,
    change_kind: "create" | "write" | "rename" | "delete" | "metadata",
    size_bytes: int?,
}

class CheckpointSelection {
    paths: string[],
    reasons: map<string, string>,
}
