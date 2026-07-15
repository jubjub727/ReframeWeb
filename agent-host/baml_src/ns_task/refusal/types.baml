class TaskFailureDecision {
    validation_reply: string,
    can_refine: bool,
}

class TaskRetryContext {
    previous_replies: TaskAttemptReply[],
    refusal_replies: string[],
}

class TaskFailureResolution {
    validation_reply: string,
    can_refine: bool,
    retry_context: TaskRetryContext,
    retry_prompt: string,
}
