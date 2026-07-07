function ComposeTaskInput(
    current_user_request: string,
    current_conversation: ConversationHistory?,
    session_memories: SessionMemoryContext[],
    selected_task: SelectedTaskContext,
    selected_memories: TaskPromptSelectedMemoryContext[],
    task_prompt_memories: TaskPromptMemoryContext[],
) -> TaskPromptComposition {
    client: TaskPromptModel
    prompt: #"
        {{ _.role("system") }}

        Prepare the input text that will be stitched under the selected task
        prompt before it is sent to the selected task.

        Return compact task_input text from the supplied context.

        Guidance:
        - Build task_input from the current request, conversation, and remembered
          context.
        - Preserve the user's goal, useful wording, preferences, constraints, and
          unresolved details explicitly present in the supplied context.
        - Translate remembered context into concrete task-relevant guidance.
        - Keep task_input concise and natural. Use light bullets when they make it
          easier to read.
        - Write for the task runner using human-meaningful context rather than
          source bookkeeping.
        - Set candidate_memory only when this composition step reveals durable
          guidance for future prompt composition.
        - Keep a list of exact memories when their contents as memories are directly related to the user request.
        - When keeping exact memories make sure to keep their parent context memory as well so the structure/origin of the memory is kept even if its siblings aren't.

        {{ _.role("user") }}

        Selected task prompt:
        {{ selected_task.prompt }}

        Current request:
        {{ current_user_request }}

        Conversation history:
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
        {% endif %}

        Remembered context from this session:
        {% for memory in session_memories %}
        - {{ memory.title }}
          Tags: {{ memory.tags }}
          {{ memory.description }}
        {% endfor %}

        Other relevant remembered context:
        {% for memory in selected_memories %}
        - {{ memory.title }}
          Tags: {{ memory.tags }}
          {{ memory.description }}
        {% endfor %}

        Prompt composition guidance:
        {% for memory in task_prompt_memories %}
        - {{ memory.title }}
          Tags: {{ memory.tags }}
          {{ memory.description }}
        {% endfor %}

        Return the task prompt composition.
        {{ ctx.output_format }}
    "#
}

