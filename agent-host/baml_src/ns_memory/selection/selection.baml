//# Build chosen graph

function SelectedGraph(
    memories: root.memory.RetrievedMemoryGraph,
    decision: root.memory.RelevantMemoryDecision,
) -> root.memory.RetrievedMemoryGraph {
    let kept_ids = decision.kept_memory_ids;
    let sessions: root.memory.RetrievedSessionGraph[] = [];

    for (let session in memories.past_sessions) {
        if let filtered: root.memory.RetrievedSessionGraph = root.memory.internal.RelevantSessionGraph(session, kept_ids) {
            let _ = sessions.push(filtered);
        }
    }

    root.memory.RetrievedMemoryGraph {
        task_catalog: memories
            .task_catalog
            .filter(
                (task) -> {
                    kept_ids.includes(task.id)
                },
            ),
        past_sessions: sessions,
        current_session_memories: memories
            .current_session_memories
            .filter(
                (memory) -> {
                    kept_ids.includes(memory.id)
                },
            ),
    }
}
