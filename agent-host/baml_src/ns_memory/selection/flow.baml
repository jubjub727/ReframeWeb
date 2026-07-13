//# Select memory

function SelectRelevantMemories(
    current_user_request: string,
    current_conversation: root.turn_context.ConversationHistory?,
    session_memories: root.turn_context.SessionMemoryContext[],
    selected_task: root.task_catalog.SelectedTaskContext,
    candidate_memories: RetrievedMemoryCandidate[],
    relevance_memories: RelevanceMemoryContext[],
    machine_state: root.turn_context.MachineStateContext,
) -> RelevantMemoryDecision {
    client: RelevanceModel
    prompt: #"
        {{ _.role("system") }}

        Your job is to select which memories are relevant to performing the task
        with respect to the user's request.

        Make sure to include all relevant memories in a timely manner. This task should be both quick and thorough.

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
        {{ current_conversation }}
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

        Machine state:
          captured_at_utc: {{ machine_state.captured_at_utc }}
          current_local_time: {{ machine_state.current_local_time }}
          current_utc_time: {{ machine_state.current_utc_time }}
          timezone_name: {{ machine_state.timezone_name }}
          utc_offset: {{ machine_state.utc_offset }}
          os_architecture: {{ machine_state.os_architecture }}
          monitor_count: {{ machine_state.monitor_count }}
          monitors:
        {% for monitor in machine_state.monitors %}
          - horizontal_resolution: {{ monitor.horizontal_resolution }}
            vertical_resolution: {{ monitor.vertical_resolution }}
        {% endfor %}
          geolocation_status: {{ machine_state.geolocation_status }}
          geolocation_source: {{ machine_state.geolocation_source }}
          ip_address: {{ machine_state.ip_address }}
          country: {{ machine_state.country }}
          country_code: {{ machine_state.country_code }}
          region: {{ machine_state.region }}
          city: {{ machine_state.city }}
          postal_code: {{ machine_state.postal_code }}
          latitude: {{ machine_state.latitude }}
          longitude: {{ machine_state.longitude }}
          geolocation_timezone: {{ machine_state.geolocation_timezone }}
          organization: {{ machine_state.organization }}
          asn: {{ machine_state.asn }}
          geolocation_error: {{ machine_state.geolocation_error }}

        Return the relevant memory decision.
        {{ ctx.output_format }}
    "#
}
