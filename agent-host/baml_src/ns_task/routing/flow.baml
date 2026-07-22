//# Choose task

function ChooseTask(
    current_user_request: string,
    current_conversation: root.turn_context.ConversationHistory?,
    session_memories: root.turn_context.SessionMemoryContext[],
    user_preferences: root.turn_context.UserPreferenceMemoryContext[],
    available_tasks: root.task_catalog.AvailableTask[],
    task_choice_memories: TaskChoiceMemoryContext[],
    machine_state: root.turn_context.MachineStateContext,
) -> TaskChoiceDecision {
    client: TaskChoiceModel
    prompt: `
        ${role("system")}

        You choose one task for the current user request.

        Use the available task information and context to decide which task should
        run next.

        When the usual appropriate task would violate a user preference either follow that preferences guidance or simply choose do nothing.

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
        - candidate_memory: a durable observation about how this routing layer
          should choose among available tasks in future requests.

        Rules:
        - Select exactly one task from Available tasks.
        - selected_task_id must exactly match an available task id.
        - Do not invent task ids.
        - Do not perform the task. Only choose the task.
        - Use optional outputs only when they are useful.
        - candidate_memory belongs only to the behavior of task routing. It must
          describe a reusable lesson about deciding which available task to
          select.
        - The request, conversation, memories, preferences, available tasks, and
          machine state are routing inputs. Never copy, paraphrase, consolidate,
          infer, or promote their contents into candidate_memory.
        - A user fact, user preference, formatting preference, request detail,
          response instruction, task result, or summary of an available task is
          never a candidate memory from this layer.
        - Return candidate_memory only when this routing decision exposed a new,
          durable routing lesson not already stated here or in task-choice
          memories. Otherwise return null. If the candidate could be read as
          something to remember about the user, request, or selected task instead
          of the router, return null.
        - User request may be related to memories that this layer is not yet aware of, simply finish your task without thinking too much if that seems to be the case.

        ${role("user")}

        Current user request:
        ${current_user_request}

        Conversation history:
        ${if (current_conversation != null) {
            `Conversation:
        ${current_conversation}`
        } else {
            ""
        }}

        Session memories:
        ${session_memories.map((memory) -> {
            `- ${memory.title}
          Tags: ${memory.tags}
          created_at: ${memory.created_at}
          updated_at: ${memory.updated_at}
          read_at: ${memory.read_at}
          ${memory.description}`
        }).join("\n")}

        User preferences:
        ${user_preferences.map((preference) -> {
            `- ${preference.title}
          Tags: ${preference.tags}
          created_at: ${preference.created_at}
          updated_at: ${preference.updated_at}
          read_at: ${preference.read_at}
          ${preference.description}`
        }).join("\n")}

        Available tasks:
        ${available_tasks.map((task) -> {
            `- id: ${task.id}
          name: ${task.name}
          description: ${task.description}
          input: ${task.input}
          output: ${task.output}
          provider_id: ${task.provider_id}
          prompt: ${task.prompt}
          created_at: ${task.created_at}
          updated_at: ${task.updated_at}
          read_at: ${task.read_at}`
        }).join("\n")}

        Task-choice memories:
        ${task_choice_memories.map((memory) -> {
            `- ${memory.title}
          Tags: ${memory.tags}
          created_at: ${memory.created_at}
          updated_at: ${memory.updated_at}
          read_at: ${memory.read_at}
          ${memory.description}`
        }).join("\n")}

        Machine state:
          captured_at_utc: ${machine_state.captured_at_utc}
          current_local_time: ${machine_state.current_local_time}
          current_utc_time: ${machine_state.current_utc_time}
          timezone_name: ${machine_state.timezone_name}
          utc_offset: ${machine_state.utc_offset}
          os_architecture: ${machine_state.os_architecture}
          monitor_count: ${machine_state.monitor_count}
          monitors:
        ${machine_state.monitors.map((monitor) -> {
            `  - horizontal_resolution: ${monitor.horizontal_resolution}
            vertical_resolution: ${monitor.vertical_resolution}`
        }).join("\n")}
          geolocation_status: ${machine_state.geolocation_status}
          geolocation_source: ${machine_state.geolocation_source}
          ip_address: ${machine_state.ip_address}
          country: ${machine_state.country}
          country_code: ${machine_state.country_code}
          region: ${machine_state.region}
          city: ${machine_state.city}
          postal_code: ${machine_state.postal_code}
          latitude: ${machine_state.latitude}
          longitude: ${machine_state.longitude}
          geolocation_timezone: ${machine_state.geolocation_timezone}
          organization: ${machine_state.organization}
          asn: ${machine_state.asn}
          geolocation_error: ${machine_state.geolocation_error}

        Return only the task choice decision.
        ${ctx.output_format}
    `
}
