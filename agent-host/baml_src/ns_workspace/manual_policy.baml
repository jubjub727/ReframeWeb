function ManualWorkspacePlan(
    memory_ids: string[],
    prefetch_paths: string[],
    scratch_globs: string[],
) -> WorkspacePlan {
    //# Deterministic manual policy until an explicitly requested agent policy exists.
    WorkspacePlan {
        memory_ids: memory_ids,
        prefetch_paths: prefetch_paths,
        rules: scratch_globs
            .map(
                (path_glob) -> {
                    WorkspacePolicyRule {
                        path_glob: path_glob,
                        materialization: Materialization.DirectDisk,
                        retention: Retention.Discard,
                        provenance: "manual",
                    }
                },
            ),
    }
}

function ManualCheckpoint(paths: string[]) -> CheckpointSelection {
    //# Retention stays explicit and discard-by-default.
    CheckpointSelection {
        paths: paths,
        reasons: paths
            .reduce(
                (reasons, path) -> {
                    let _ = reasons.set(path, "manually selected");
                    reasons
                },
                {},
            ),
    }
}

test "manual workspace policy is deterministic" {
    let plan = ManualWorkspacePlan(["memory_node:design"], ["README.md"], ["**/node_modules/**"]);
    assert.equal(plan.memory_ids, ["memory_node:design"]);
    assert.equal(plan.rules.at(0)?.retention, Retention.Discard)
}

test "manual checkpoint retains only explicit paths" {
    let selection = ManualCheckpoint(["src/result.rs"]);
    assert.equal(selection.paths, ["src/result.rs"]);
    assert.equal(selection.reasons.get("src/result.rs"), "manually selected")
}

test "empty manual selections stay empty" {
    let plan = ManualWorkspacePlan([], [], []);
    let selection = ManualCheckpoint([]);
    assert.equal(plan.memory_ids, []);
    assert.equal(plan.prefetch_paths, []);
    assert.equal(plan.rules, []);
    assert.equal(selection.paths, [])
}
