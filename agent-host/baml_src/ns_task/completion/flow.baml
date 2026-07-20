//# Check completion

function CheckTaskCompletion(
    completion_string: string,
    output_summary: string,
    current_user_request: string = "",
    current_conversation: root.turn_context.ConversationHistory? = null,
) -> CompletionResult {
    client: TaskCompletionModel
    prompt: #"
        {{ _.role("system") }}

        You are a task completion checker.

        Decide whether the completion requirement is satisfied by the current
        user request, current conversation, and task output summary together.

        The active user request is the primary specification for result quality.
        The completion requirement describes the kind of outcome the selected
        task must produce. Validate the delivered result against the active user
        request itself, not merely against the generic outcome type.

        The current conversation is reloaded after the task's actions were
        dispatched. Treat an agent or agent_reply message in it as direct
        evidence that the reply was already posted to the user (agent is the
        persisted conversation role for an agent_reply action). Do not require
        another "fresh" reply or fail merely because the compact task output
        summary does not explicitly restate that timing. A validation_reply is
        feedback from an earlier failed check, not proof that the current attempt
        is incomplete; judge the newest task outcome on its own evidence.

        On a retry, the candidate result is the newest task attempt described by
        the task output summary. Earlier agent replies are superseded history.
        Use validation_reply messages only as diagnostic context about what needs
        attention. Derive the expected result from the active user request rather
        than treating retry guidance as an answer key.

        Validate both completion and result quality. For a reply task, confirm
        that a reply was posted, that it directly responds to the user's request,
        and that it has no demonstrable factual or logical error. Do not
        rubber-stamp a merely non-empty reply. Equally, do not invent a stricter
        requirement, demand preferred wording, or ask for another reply after a
        satisfactory one is already present.

        Use sound judgment appropriate to the task. Consider the conversation,
        retry guidance, and action summary as a whole. Validate the substance of
        the result rather than merely its delivery. When correctness is part of
        the requested outcome, independently check claims that can reasonably be
        checked from the available context.

        Distinguish material errors or omissions from harmless differences in
        wording, style, or method. Return PASS when the evidence as a whole shows
        that the intended outcome was achieved. Return FAIL only when a concrete,
        material problem remains. Earlier validation_reply messages are relevant
        context but are fallible, just like the other evidence.

        {{ _.role("user") }}

        Active user request:
        {{ current_user_request }}

        Completion requirement:
        {{ completion_string }}

        Current filtered conversation after task dispatch:
        {% if current_conversation %}
        {{ current_conversation }}
        {% else %}
        No conversation was available.
        {% endif %}

        Task output summary:
        {{ output_summary }}

        Return exactly one token:
        PASS or FAIL

        {{ ctx.output_format }}
    "#
}
