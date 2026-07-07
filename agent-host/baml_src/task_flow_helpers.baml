function MemorySearchDomains() -> SearchDepthDomain[] {
    [
        SearchDepthDomain {
            id: "task_catalog",
            description: "Historic task catalog records. Use this domain when older task definitions may help interpret or run the selected task.",
            searches: "Task memory nodes only.",
            hydrates: "Matched Task nodes only.",
        },
        SearchDepthDomain {
            id: "past_conversation_context",
            description: "Historic conversation context outside the current default session context. Use this domain when earlier sessions, conversations, messages, or session memories may clarify the request.",
            searches: "Session nodes, Conversation nodes, ConversationMessage nodes, and SessionMemory nodes attached to those past sessions.",
            hydrates: "The containing Session node, relevant Conversation nodes, matched ConversationMessage nodes, and relevant SessionMemory nodes from that session.",
        },
    ]
}

function SelectedTaskDetails(
    available_tasks: AvailableTask[],
    selected_task_id: string,
) -> SelectedTaskContext {
    for (let task in available_tasks) {
        if (task.id == selected_task_id) {
            return SelectedTaskContext {
                id: task.id,
                name: task.name,
                description: task.description,
                input: task.input,
                output: task.output,
                prompt: task.prompt,
                provider_id: task.provider_id,
                created_at: task.created_at,
                updated_at: task.updated_at,
                read_at: task.read_at,
            };
        }
    }

    throw baml.errors.InvalidArgument {
        message: `selected task does not exist in available task context: ${selected_task_id}`,
    }
}

function TaskPromptText(selected_task_prompt: string, task_input: string) -> string {
    `Task:\n${selected_task_prompt}\n\nInput:\n${task_input}`
}

function FinishTaskPrompt(
    selected_task_prompt: string,
    composition: TaskPromptComposition,
) -> TaskPromptDecision {
    TaskPromptDecision {
        full_task_prompt: TaskPromptText(selected_task_prompt, composition.task_input),
        candidate_memory: composition.candidate_memory,
    }
}
