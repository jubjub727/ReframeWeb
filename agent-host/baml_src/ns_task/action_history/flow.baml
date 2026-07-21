//# Summarise history

function SummariseActionHistory(recorded_action_history: string) -> string {
    client: ActionHistorySummaryModel
    prompt: #"
        {{ _.role("system") }}

        Summarize what the recorded actions for this task attempt did and what changed.

        Guidance:
        - The listed actions are the complete scope of this summary.
        - Base each statement on their inputs and outputs.
        - Describe what happened, what was produced, what changed, and what remains unclear from the action outputs.
        - Preserve payload values exactly when their representation matters. Do
          not reinterpret punctuation or formatting inside a value as a different
          structure unless the action data itself establishes that structure.
        - Summarize the recorded actions without speculating about the request
          that caused them or declaring their payload ambiguous merely because
          request context is outside this summary's scope.
        - Keep the summary compact while preserving the details needed to understand the current state.

        {{ _.role("user") }}

        Recorded actions for this task attempt:
        {{ recorded_action_history }}

        Return the summary.
        {{ ctx.output_format }}
    "#
}
