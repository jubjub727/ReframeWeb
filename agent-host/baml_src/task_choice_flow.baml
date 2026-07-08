function ChooseTask(
    current_user_request: string,
    current_conversation: ConversationHistory?,
    session_memories: SessionMemoryContext[],
    user_preferences: UserPreferenceMemoryContext[],
    available_tasks: AvailableTask[],
    task_choice_memories: TaskChoiceMemoryContext[],
    machine_state: MachineStateContext,
) -> TaskChoiceDecision {
    client: TaskChoiceModel
    prompt: #"
        {{ _.role("system") }}

        You choose one task for the current user request.

        Use the available task information and context to decide which task should
        run next.

        Stop once you have the right task.

        Context sections:
        - Current user request: the request being routed now.
        - Conversation history: earlier human and agent messages.
        - Session memories: remembered observations for this session.
        - User preferences: durable user preferences that should influence routing.
        - Available tasks: the only tasks that may be selected.
        - Task-choice memories: remembered observations about choosing tasks.
        - Machine state: current non-stored local time, timezone, OS/architecture,
          monitor resolutions, and IP geolocation.

        Optional output available in this step:
        - candidate_memory: a vague remembered observation that could be useful to
          preserve.

        Rules:
        - Select exactly one task from Available tasks.
        - selected_task_id must exactly match an available task id.
        - Do not invent task ids.
        - Do not perform the task. Only choose the task.
        - Use optional outputs only when they are useful.
        - User request may be related to memories that this layer is not yet aware of, simply finish your task without thinking too much if that seems to be the case.

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

        Session memories:
        {% for memory in session_memories %}
        - {{ memory.title }}
          Tags: {{ memory.tags }}
          created_at: {{ memory.created_at }}
          updated_at: {{ memory.updated_at }}
          read_at: {{ memory.read_at }}
          {{ memory.description }}
        {% endfor %}

        User preferences:
        {% for preference in user_preferences %}
        - {{ preference.title }}
          Tags: {{ preference.tags }}
          created_at: {{ preference.created_at }}
          updated_at: {{ preference.updated_at }}
          read_at: {{ preference.read_at }}
          {{ preference.description }}
        {% endfor %}

        Available tasks:
        {% for task in available_tasks %}
        - id: {{ task.id }}
          name: {{ task.name }}
          description: {{ task.description }}
          input: {{ task.input }}
          output: {{ task.output }}
          provider_id: {{ task.provider_id }}
          prompt: {{ task.prompt }}
          created_at: {{ task.created_at }}
          updated_at: {{ task.updated_at }}
          read_at: {{ task.read_at }}
        {% endfor %}

        Task-choice memories:
        {% for memory in task_choice_memories %}
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

        Return only the task choice decision.
        {{ ctx.output_format }}
    "#
}

