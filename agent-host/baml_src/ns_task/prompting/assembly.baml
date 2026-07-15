//# Package prompt

function PromptDecision(
    selected_task_prompt: string,
    composition: root.task.TaskPromptComposition,
) -> root.task.TaskPromptDecision {
    root.task.TaskPromptDecision {
        full_task_prompt: root.task.internal.PromptText(selected_task_prompt, composition.task_input),
        candidate_memory: composition.candidate_memory,
    }
}

//# Add retry context

function PromptWithRetryContext(
    full_task_prompt: string,
    previous_replies: TaskAttemptReply[],
    refusal_replies: string[],
) -> string {
    let previous_reply_text = previous_replies
        .map(
            (reply) -> {
                `${reply.role}: ${reply.content}`
            },
        )
        .join("\n");
    let refusal_reply_text = refusal_replies
        .map(
            (reply) -> {
                `- ${reply}`
            },
        )
        .join("\n");
    let with_previous_replies = if (previous_reply_text == "") {
        full_task_prompt
    } else {
        `${full_task_prompt}\n\nPrevious Replies:\n${previous_reply_text}`
    };
    if (refusal_reply_text == "") {
        with_previous_replies
    } else {
        `${with_previous_replies}\n\nRefusal Reply:\n${refusal_reply_text}`
    }
}
