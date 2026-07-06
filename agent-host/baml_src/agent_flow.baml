enum ConversationMode {
    WAKE_COMMAND,
    CONTINUOUS_CONVERSATION,
}

class AvailableTask {
    id: string,
    name: string,
    description: string,
    input: string,
    output: string,
    prompt: string,
    provider_id: string,
    created_at: string,
    updated_at: string,
    read_at: string,
}

class ConversationHistoryMessage {
    created_at: string,
    updated_at: string,
    read_at: string,
    role: string,
    content: string,
}

class ConversationHistory {
    id: string,
    name: string,
    created_at: string,
    updated_at: string,
    read_at: string,
    messages: ConversationHistoryMessage[],
}

class SessionMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class TaskChoiceMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class ConversationEvaluationMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class SearchDepthMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RelevanceMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class TaskPromptMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class SelectedTaskContext {
    id: string,
    name: string,
    description: string,
    input: string,
    output: string,
    prompt: string,
    provider_id: string,
    created_at: string,
    updated_at: string,
    read_at: string,
}

class MemoryTagSearch {
    any_of: string[],
    all_of: string[],
    none_of: string[],
}

class MemoryStringSearch {
    contains: string[],
    equals: string[],
}

class CandidateMemory {
    title: string,
    description: string,
}

class SearchDepthDomain {
    id: string,
    description: string,
    searches: string,
    hydrates: string,
}

class SearchDepthTimestamps {
    created_after: string,
    read_after: string,
    updated_after: string,
}

class ConversationMemorySearchHints {
    tags: MemoryTagSearch,
    strings: MemoryStringSearch,
    candidate_memory: CandidateMemory?,
}

class SearchDepthDecision {
    depths: map<string, SearchDepthTimestamps>,
    candidate_memory: CandidateMemory?,
}

class RetrievedMemoryCandidate {
    id: string,
    kind: string,
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
    retrieval_matched: bool,
    parent_session_id: string?,
    parent_conversation_id: string?,
}

class TaskPromptSelectedMemoryContext {
    title: string,
    description: string,
    tags: string[],
    created_at: string,
    updated_at: string,
    read_at: string,
}

class RelevantMemoryDecision {
    kept_memory_ids: string[],
    candidate_memory: CandidateMemory?,
}

class TaskChoiceDecision {
    selected_task_id: string,
    confidence: float,
    reason: string,
    agent_thought: string?,
    candidate_memory: CandidateMemory?,
}

class TaskPromptDecision {
    full_task_prompt: string,
    candidate_memory: CandidateMemory?,
}

class TaskPromptComposition {
    task_input: string,
    candidate_memory: CandidateMemory?,
}

class TaskReturnItem {
    name: string,
    payload: map<string, string>?,
}

class TaskExecutionResult {
    returns: TaskReturnItem[],
}

function ChooseInitialTask(
    current_user_request: string,
    current_conversation: ConversationHistory?,
    session_memories: SessionMemoryContext[],
    available_tasks: AvailableTask[],
    task_choice_memories: TaskChoiceMemoryContext[],
) -> TaskChoiceDecision {
    client: TaskChoiceModel
    prompt: #"
        {{ _.role("system") }}

        You choose one task for the current user request.

        Use the available task information and context to decide which task should
        run next.

        Stop once you have the right task without thinking about it too much. Don't waste time thinking about the agent_thought too much.

        Context sections:
        - Current user request: the request being routed now.
        - Conversation history: earlier human and agent messages.
        - Session memories: remembered observations for this session.
        - Available tasks: the only tasks that may be selected.
        - Task-choice memories: remembered observations about choosing tasks.

        Optional outputs available in this step:
        - agent_thought: private context to add to the conversation without
          notifying the human.
        - candidate_memory: a vague remembered observation that could be useful to
          preserve.

        Rules:
        - Select exactly one task from Available tasks.
        - selected_task_id must exactly match an available task id.
        - Do not invent task ids.
        - Do not perform the task. Only choose the task.
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

        Session memories:
        {% for memory in session_memories %}
        - {{ memory.title }}
          Tags: {{ memory.tags }}
          created_at: {{ memory.created_at }}
          updated_at: {{ memory.updated_at }}
          read_at: {{ memory.read_at }}
          {{ memory.description }}
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

        Return only the task choice decision.
        {{ ctx.output_format }}
    "#
}

function GenerateTaskPrompt(
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
        - Keep a list of exact memories when their contents as memories are directly related to the user request
        - When keeping exact memories make sure to keep their parent context memory as well so the structure/origin of the memory is kept even if its siblings aren't

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

function ExecuteTask(full_task_prompt: string) -> TaskExecutionResult {
    client: TaskExecutionModel
    prompt: #"
        {{ _.role("system") }}

        Complete the task according to the task prompt and any guidance included in
        it.

        Rules:
        - You must follow the output shape requested by the task prompt.
        - When the task prompt describes named response items, put each item name in
          name and its arguments in payload.
        - You must only return response items for which you have direct evidence of its name and structure.
        - Do not add extra commentary outside the structured result.
        - Return an empty returns array when the task prompt does not request any
          response item.

        {{ _.role("user") }}

        Task prompt:
        {{ full_task_prompt }}

        Return the task execution result.
        {{ ctx.output_format }}
    "#
}

function EvaluateRelevantMemories(
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

function EvaluateConversationForMemorySearch(
    current_user_request: string,
    current_conversation: ConversationHistory?,
    session_memories: SessionMemoryContext[],
    selected_task: SelectedTaskContext,
    conversation_evaluation_memories: ConversationEvaluationMemoryContext[],
) -> ConversationMemorySearchHints {
    client: ConversationEvaluationModel
    prompt: #"
        {{ _.role("system") }}

        You evaluate the conversation and produce memory search hints for
        the selected task.

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

function EvaluateSearchDepths(
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

        Choose timestamp cutoffs for each listed search domain.

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
