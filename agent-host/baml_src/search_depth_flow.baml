function ChooseMemorySearchDepths(
    current_timestamp: string,
    current_user_request: string,
    current_conversation: ConversationHistory?,
    session_memories: SessionMemoryContext[],
    selected_task: SelectedTaskContext,
    memory_search_hints: ConversationMemorySearchHints,
    search_domains: SearchDepthDomain[],
    search_depth_memories: SearchDepthMemoryContext[],
) -> SearchDepthDecision {
    client: SearchDepthModel
    prompt: #"
        {{ _.role("system") }}

        Choose timestamp cutoffs for each listed search domain. Your job is to quickly decide an appropriate cutoff date based on current context.

        Stop once you have timestamps that look good enough for the request without thinking about it too much.

        Rules:
        - Return a SearchDepthDecision with depths and optional candidate_memory.
        - depths must contain exactly one key for each listed domain id.
        - Use the listed domain ids exactly as written.
        - Each depth value must contain only created_after, read_after, and
          updated_after ISO 8601 timestamp strings.
        - Use the current timestamp as the reference point for recency.
        - Choose each timestamp independently.
        - Use older timestamps when older context may be useful.
        - Use newer timestamps when recent context is enough.
        - Stop once the timestamp cutoffs look good enough for the request.

        Timestamp fields:
        - created_after: lower-bound cutoff for created_at.
        - read_after: lower-bound cutoff for read_at.
        - updated_after: lower-bound cutoff for updated_at.

        Optional output:
        - candidate_memory: a remembered observation about choosing timestamp
          cutoffs that could be useful later.

        {{ _.role("user") }}

        Current timestamp:
        {{ current_timestamp }}

        Current user request:
        {{ current_user_request }}

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

        Search hints:
        tags:
          any_of: {{ memory_search_hints.tags.any_of }}
          all_of: {{ memory_search_hints.tags.all_of }}
          none_of: {{ memory_search_hints.tags.none_of }}
        strings:
          contains: {{ memory_search_hints.strings.contains }}
          equals: {{ memory_search_hints.strings.equals }}
        candidate_memory:
        {{ memory_search_hints.candidate_memory }}

        Search domains:
        {% for domain in search_domains %}
        - id: {{ domain.id }}
          description: {{ domain.description }}
          searches: {{ domain.searches }}
          hydrates: {{ domain.hydrates }}
        {% endfor %}

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

        Current session memories:
        {% for memory in session_memories %}
        - {{ memory.title }}
          Tags: {{ memory.tags }}
          created_at: {{ memory.created_at }}
          updated_at: {{ memory.updated_at }}
          read_at: {{ memory.read_at }}
          {{ memory.description }}
        {% endfor %}

        Past cutoff notes:
        {% for memory in search_depth_memories %}
        - {{ memory.title }}
          Tags: {{ memory.tags }}
          created_at: {{ memory.created_at }}
          updated_at: {{ memory.updated_at }}
          read_at: {{ memory.read_at }}
          {{ memory.description }}
        {% endfor %}

        Return a SearchDepthDecision.
        {{ ctx.output_format }}
    "#
}

