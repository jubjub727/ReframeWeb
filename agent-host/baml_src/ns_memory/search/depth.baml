//# Set search depth

function ChooseMemorySearchDepths(
    current_timestamp: string,
    current_user_request: string,
    current_conversation: root.turn_context.ConversationHistory?,
    session_memories: root.turn_context.SessionMemoryContext[],
    selected_task: root.task_catalog.SelectedTaskContext,
    memory_search_hints: ConversationMemorySearchHints,
    search_domains: SearchDepthDomain[],
    search_depth_memories: SearchDepthMemoryContext[],
    machine_state: root.turn_context.MachineStateContext,
) -> SearchDepthDecision {
    client: SearchDepthModel
    prompt: `
        ${role("system")}

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
        - candidate_memory: a durable observation about how this layer should
          choose timestamp cutoffs in future searches.
        - candidate_memory belongs only to the behavior of timestamp-cutoff
          selection. It must describe a reusable lesson about choosing time
          ranges for search domains.
        - The request, conversation, memories, task, search hints, domains, and
          machine state are cutoff-selection inputs. Never copy, paraphrase,
          consolidate, infer, or promote their contents into candidate_memory.
        - A user fact, user preference, formatting preference, request detail,
          task instruction, task result, search subject, or chosen timestamp is
          never a candidate memory from this layer.
        - Return candidate_memory only when this decision exposed a new, durable
          cutoff-selection lesson not already stated here or in cutoff memories.
          Otherwise return null. If the candidate could be read as something to
          remember about the user, request, searched content, or current cutoff
          instead of the cutoff selector, return null.

        ${role("user")}

        Current timestamp:
        ${current_timestamp}

        Current user request:
        ${current_user_request}

        Selected task:
        - id: ${selected_task.id}
          name: ${selected_task.name}
          description: ${selected_task.description}
          input: ${selected_task.input}
          output: ${selected_task.output}
          provider_id: ${selected_task.provider_id}
          prompt: ${selected_task.prompt}
          created_at: ${selected_task.created_at}
          updated_at: ${selected_task.updated_at}
          read_at: ${selected_task.read_at}

        Search hints:
        tags:
          any_of: ${memory_search_hints.tags.any_of}
          all_of: ${memory_search_hints.tags.all_of}
          none_of: ${memory_search_hints.tags.none_of}
        strings:
          contains: ${memory_search_hints.strings.contains}
          equals: ${memory_search_hints.strings.equals}

        Search domains:
        ${search_domains.map((domain) -> {
            `- id: ${domain.id}
          description: ${domain.description}
          searches: ${domain.searches}
          hydrates: ${domain.hydrates}`
        }).join("\n")}

        Conversation history:
        ${if (current_conversation != null) {
            `Conversation:
        ${current_conversation}`
        } else {
            ""
        }}

        Current session memories:
        ${session_memories.map((memory) -> {
            `- ${memory.title}
          Tags: ${memory.tags}
          created_at: ${memory.created_at}
          updated_at: ${memory.updated_at}
          read_at: ${memory.read_at}
          ${memory.description}`
        }).join("\n")}

        Past cutoff notes:
        ${search_depth_memories.map((memory) -> {
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

        Return a SearchDepthDecision.
        ${ctx.output_format}
    `
}
