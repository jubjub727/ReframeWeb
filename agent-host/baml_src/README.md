# BAML source layout

The source tree is organized around stable domain intent rather than individual
pipeline stages. Only directories prefixed with `ns_` create BAML namespaces;
ordinary subdirectories organize related files in an IDE without adding nodes to
the namespace graph.

| Namespace | Responsibility |
| --- | --- |
| `root.task` | Task routing, prompt preparation, execution, action summaries, and completion checks |
| `root.task_catalog` | Task definitions and selected-task lookup |
| `root.memory` | Memory search, retrieved graphs, relevance selection, and filtering |
| `root.turn_context` | Conversation, preference, session-memory, and machine-state inputs |
| `root.voice_turn` | Turn-level orchestration and timing |
| `root.opencode_go` | Concrete OpenCode Go model clients and inventory |
| `root.benchmarks` | Typed fixtures, cases, and deterministic evaluation helpers |

Dependencies should point toward contracts and data preparation:

```text
voice_turn ─┬─> task ──> memory ─┬─> task_catalog
            ├─> memory           └─> turn_context
            ├─> task_catalog
            └─> turn_context
```

Provider clients remain independent and are selected by the Python Agent Host.
Benchmark code may depend on runtime namespaces, but runtime code must not depend
on benchmarks.
