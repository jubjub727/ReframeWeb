function SummariseActionHistory(
    current_conversation: ConversationHistory?,
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
          id: {{ current_conversation.id }}
          name: {{ current_conversation.name }}
          created_at: {{ current_conversation.created_at }}
          updated_at: {{ current_conversation.updated_at }}
          read_at: {{ current_conversation.read_at }}
        {% for message in current_conversation.messages %}
        [{{ message.role }}] {{ message.content }}
        {% endfor %}
        {% else %}
        No current conversation is available.
        {% endif %}

        Recorded action history:
        {{ recorded_action_history }}

        Return the summary.
        {{ ctx.output_format }}
    "#
}
