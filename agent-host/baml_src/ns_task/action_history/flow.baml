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
        - Keep the summary compact while preserving the details needed to understand the current state.

        {{ _.role("user") }}

        Recorded actions for this task attempt:
        {{ recorded_action_history }}

        Return the summary.
        {{ ctx.output_format }}
    "#
}
