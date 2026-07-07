function ChooseMemorySearch(
    current_user_request: string,
    current_conversation: ConversationHistory?,
    session_memories: SessionMemoryContext[],
    selected_task: SelectedTaskContext,
    conversation_evaluation_memories: ConversationEvaluationMemoryContext[],
) -> ConversationMemorySearchHints {
    client: ConversationEvaluationModel
    prompt: #"
        {{ _.role("system") }}

        Choose memory search hints for the selected task and current request.

        The hints will drive memory search before the selected task runs.

        Stop once the hints look good enough for the request without thinking about it too much.

        Search surfaces:
        - tags: exact memory tags. They are not substring searched.
        - strings.contains: case-insensitive text fragments. Each value is checked
          as a substring against searchable memory content.
        - strings.equals: exact text values. Each value is checked for exact
          equality against searchable memory content.

        Optional outputs available in this step:
        - candidate_memory: a vague remembered observation that could be useful to
          preserve.

        Rules:
        - Return only search hints and optional candidate_memory.
        - Search hints are alternatives during retrieval; a memory can be useful
          when any positive tag or string hint matches.
        - Prefer tags.any_of for positive tag hints.
        - Leave tags.all_of empty unless compatibility with older memories needs it.
        - Use tags.none_of only for clear exclusions.
        - Use strings.contains for durable words or phrases that should appear
          inside a relevant memory.
        - Use strings.equals only for exact text that should match a relevant
          memory value as a whole.
        - Prefer a small set of high-signal hints over broad keyword stuffing.
        - Return empty arrays when no useful search hint is available.
        - Use optional outputs only when they are useful.

        {{ _.role("user") }}

        Current user request:
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
        [{{ message.role }}] created_at={{ message.created_at }} updated_at={{ message.updated_at }} read_at={{ message.read_at }} {{ message.content }}
        {% endfor %}
        {% endif %}

        Session memories for this session:
        {% for memory in session_memories %}
        - {{ memory.title }}
          Tags: {{ memory.tags }}
          created_at: {{ memory.created_at }}
          updated_at: {{ memory.updated_at }}
          read_at: {{ memory.read_at }}
          {{ memory.description }}
        {% endfor %}

        Selected task:
        - id: {{ selected_task.id }}
          name: {{ selected_task.name }}
          description: {{ selected_task.description }}
          input: {{ selected_task.input }}
          output: {{ selected_task.output }}
          provider_id: {{ selected_task.provider_id }}
          prompt: {{ selected_task.prompt }}
          created_at: {{ selected_task.created_at }}
          updated_at: {{ selected_task.updated_at }}
          read_at: {{ selected_task.read_at }}

        Conversation-evaluation memories:
        {% for memory in conversation_evaluation_memories %}
        - {{ memory.title }}
          Tags: {{ memory.tags }}
          created_at: {{ memory.created_at }}
          updated_at: {{ memory.updated_at }}
          read_at: {{ memory.read_at }}
          {{ memory.description }}
        {% endfor %}

        Return only the memory search hints and optional candidate memory.
        {{ ctx.output_format }}
    "#
}
