class TaskPromptEvaluation {
    correct: bool,
    shape_ok: bool,
    top_level_labels: string[],
    task_present: bool,
    input_present: bool,
}

class LatencySummary {
    average: float?,
    best: float?,
    worst: float?,
    p50: float?,
}

//# Check task choice

function TaskChoiceCorrect(
    decision: root.task.TaskChoiceDecision,
    expected_task_id: string,
) -> bool {
    decision.selected_task_id == expected_task_id
}

//# Check memory set

function MemorySelectionCorrect(
    decision: root.memory.RelevantMemoryDecision,
    expected_ids: string[],
) -> bool {
    let actual = decision.kept_memory_ids;
    actual
        .sort_by_key(
            (id) -> {
                id
            },
        );
    expected_ids
        .sort_by_key(
            (id) -> {
                id
            },
        );

    baml.deep_equals(actual, expected_ids)
}

//# Check task prompt

function EvaluateTaskPrompt(full_task_prompt: string) -> TaskPromptEvaluation {
    let parts = full_task_prompt.trim().split("\nInput:");

    let task_present = parts.length() == 2
        && parts[0].starts_with("Task:")
        && parts[0].substring(5, parts[0].length()).trim().length() > 0;
    let input_present = parts.length() == 2 && parts[1].trim().length() > 0;
    let labels: string[] = if (parts.length() == 2 && parts[0].starts_with("Task:")) {
        ["Task", "Input"]
    } else {
        []
    };
    let shape_ok = task_present && input_present && baml.deep_equals(labels, ["Task", "Input"]);

    TaskPromptEvaluation {
        correct: shape_ok,
        shape_ok: shape_ok,
        top_level_labels: labels,
        task_present: task_present,
        input_present: input_present,
    }
}

//# Summarise latency

function SummariseLatencies(latencies: float[]) -> LatencySummary {
    if (latencies.length() == 0) {
        return LatencySummary { average: null, best: null, worst: null, p50: null };
    }

    latencies
        .sort_by_key(
            (latency) -> {
                latency
            },
        );

    let total: float = 0.0;
    for (let latency in latencies) {
        total += latency;
    }
    let middle = latencies.length() / 2;
    let median = if (latencies.length() % 2 == 0) {
        (latencies[middle - 1] + latencies[middle]) / 2.0
    } else {
        latencies[middle]
    };

    LatencySummary {
        average: total / (latencies.length() * 1.0),
        best: latencies[0],
        worst: latencies[latencies.length() - 1],
        p50: median,
    }
}
