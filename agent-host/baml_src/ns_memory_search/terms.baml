function ChooseMemorySearch(
    current_user_request: string,
    current_conversation: root.context.ConversationHistory?,
    session_memories: root.context.SessionMemoryContext[],
    selected_task: root.task_routing.SelectedTaskContext,
    conversation_evaluation_memories: ConversationEvaluationMemoryContext[],
    machine_state: root.context.MachineStateContext,
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

        Return only the memory search hints and optional candidate memory.
        {{ ctx.output_format }}
    "#
}
