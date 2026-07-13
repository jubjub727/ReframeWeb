//# Summarise history

function SummariseActionHistory(
    current_conversation: root.turn_context.ConversationHistory?,
    recorded_action_history: string,
) -> string {
    client: ActionHistorySummaryModel
    prompt: #"
        {{ _.role("system") }}

        Given the current conversation and the recorded action history, describe what the actions did and what changed.

        Guidance:
        - Use the conversation to understand what the action inputs and outputs refer to.
        - Base each statement on the listed actions.
        - Describe what happened, what was produced, what changed, and what remains unclear from the action outputs.
        - Keep the summary compact while preserving the details needed to understand the current state.

        {{ _.role("user") }}

        Current conversation:
        {% if current_conversation %}
        Conversation:
        {{ current_conversation }}
        {% else %}
        No current conversation is available.
        {% endif %}

        Recorded action history:
        {{ recorded_action_history }}

        Return the summary.
        {{ ctx.output_format }}
    "#
}
