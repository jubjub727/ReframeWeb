//# Check the original request

function CheckRequestCompletion(
    current_user_request: string,
    current_conversation: root.turn_context.ConversationHistory?,
    successful_tasks: SuccessfulVoiceTaskResult[],
) -> root.task.CompletionResult {
    client: RequestCompletionModel
    prompt: #"
        {{ _.role("system") }}

        You are checking whether the user's original request has been appropriately resolved.

        Judge the complete exchange and the confirmed task results together.

        A resolved request gives the user an accurate and appropriate response. This can include completed work, a truthful answer, a focused request for information required to continue, or a clear explanation of a limitation.

        Confirmed task results provide evidence for completed actions.

        Return PASS when the user has received an appropriate resolution.

        Return FAIL when another response or task is still needed to appropriately resolve the request.

        {{ _.role("user") }}

        Original user request:
        {{ current_user_request }}

        Current conversation:
        {% if current_conversation %}
        {{ current_conversation }}
        {% endif %}

        Confirmed task results:
        {% for task in successful_tasks %}
        - Task: {{ task.task_name }}
          Completion requirement: {{ task.completion_requirement }}
          Result: {{ task.output_summary }}
        {% endfor %}

        Return exactly one token:
        PASS or FAIL

        {{ ctx.output_format }}
    "#
}
