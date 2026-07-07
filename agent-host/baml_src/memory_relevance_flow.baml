function SelectRelevantMemories(
    current_user_request: string,
    current_conversation: ConversationHistory?,
    session_memories: SessionMemoryContext[],
    selected_task: SelectedTaskContext,
    candidate_memories: RetrievedMemoryCandidate[],
    relevance_memories: RelevanceMemoryContext[],
) -> RelevantMemoryDecision {
    client: RelevanceModel
    prompt: #"
        {{ _.role("system") }}

        Your job is to select which memories are relevant to performing the task
        with respect to the user's request.

        Stop once you have a good set of relevant memories without thinking about it too much.

        Optional output:
        - candidate_memory: an observational memory to create when something seems
          interesting or useful enough to remember.

        Rules:
        - Return only the ids of candidate memories that are relevant.
        - A memory is relevant when it would materially affect how the task should
          be performed for this request.
        - Return an empty kept_memory_ids array when no memory is relevant.

        {{ _.role("user") }}

        Current user request:
        {{ current_user_request }}

        Task:
        {{ selected_task.name }}
        {{ selected_task.description }}

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

        Session memories for this session:
        {% for memory in session_memories %}
        - {{ memory.title }}
          Tags: {{ memory.tags }}
          created_at: {{ memory.created_at }}
          updated_at: {{ memory.updated_at }}
          read_at: {{ memory.read_at }}
          {{ memory.description }}
        {% endfor %}

        Candidate memories:
        {% for memory in candidate_memories %}
        - id: {{ memory.id }}
          title: {{ memory.title }}
          tags: {{ memory.tags }}
          created_at: {{ memory.created_at }}
          updated_at: {{ memory.updated_at }}
          read_at: {{ memory.read_at }}
          description: {{ memory.description }}
        {% endfor %}

        Relevance memories:
        {% for memory in relevance_memories %}
        - {{ memory.title }}
          Tags: {{ memory.tags }}
          created_at: {{ memory.created_at }}
          updated_at: {{ memory.updated_at }}
          read_at: {{ memory.read_at }}
          {{ memory.description }}
        {% endfor %}

        Return the relevant memory decision.
        {{ ctx.output_format }}
    "#
}

