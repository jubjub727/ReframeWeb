enum ConversationMode {
  WakeCommand
  ContinuousConversation
}

class AvailableTask {
  id string
  name string
  description string
  input string
  output string
  prompt string
  provider_id string
  created_at string
  updated_at string
  read_at string
}

class ConversationHistoryMessage {
  created_at string
  updated_at string
  read_at string
  role string
  content string
}

class ConversationHistory {
  id string
  name string
  created_at string
  updated_at string
  read_at string
  messages ConversationHistoryMessage[]
}

class SessionMemoryContext {
  title string
  description string
  tags string[]
  created_at string
  updated_at string
  read_at string
}

class TaskChoiceMemoryContext {
  title string
  description string
  tags string[]
  created_at string
  updated_at string
  read_at string
}

class ConversationEvaluationMemoryContext {
  title string
  description string
  tags string[]
  created_at string
  updated_at string
  read_at string
}

class SelectedTaskContext {
  id string
  name string
  description string
  input string
  output string
  prompt string
  provider_id string
  created_at string
  updated_at string
  read_at string
}

class MemoryTagSearch {
  any_of string[]
  all_of string[]
  none_of string[]
}

class MemoryStringSearch {
  contains string[]
  equals string[]
}

class CandidateMemory {
  title string
  description string
}

class ConversationMemorySearchHints {
  tags MemoryTagSearch
  strings MemoryStringSearch
  candidate_memory CandidateMemory?
}

class TaskChoiceDecision {
  selected_task_id string
  confidence float
  reason string
  agent_thought string?
  candidate_memory CandidateMemory?
}

function ChooseInitialTask(
  current_user_request: string,
  session_conversations: ConversationHistory[],
  session_memories: SessionMemoryContext[],
  available_tasks: AvailableTask[],
  task_choice_memories: TaskChoiceMemoryContext[]
) -> TaskChoiceDecision {
  client TaskChoiceModel
  prompt #"
    {{ _.role("user") }}

    You choose one task for the current user request.

    Use the available task information and context to decide which task should
    run next.

    Context sections:
    - Current user request: the request being routed now.
    - Conversation history: earlier human and agent messages from this session.
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

    Current user request:
    {{ current_user_request }}

    Conversation history:
    {% for conversation in session_conversations %}
    Conversation:
      id: {{ conversation.id }}
      name: {{ conversation.name }}
      created_at: {{ conversation.created_at }}
      updated_at: {{ conversation.updated_at }}
      read_at: {{ conversation.read_at }}
    {% for message in conversation.messages %}
    [{{ message.role }}] created_at={{ message.created_at }} updated_at={{ message.updated_at }} read_at={{ message.read_at }} {{ message.content }}
    {% endfor %}
    {% endfor %}

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

function EvaluateConversationForMemorySearch(
  current_user_request: string,
  session_conversations: ConversationHistory[],
  session_memories: SessionMemoryContext[],
  selected_task: SelectedTaskContext,
  conversation_evaluation_memories: ConversationEvaluationMemoryContext[]
) -> ConversationMemorySearchHints {
  client ConversationEvaluationModel
  prompt #"
    {{ _.role("system") }}

    You evaluate the current conversation and produce memory search hints for
    the selected task.

    The hints will drive memory search before the selected task runs.

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
    - Use tags.any_of for useful alternatives where any matching tag may help.
    - Use tags.all_of only when every listed tag must be present.
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

    Conversation history for the current session:
    {% for conversation in session_conversations %}
    Conversation:
      id: {{ conversation.id }}
      name: {{ conversation.name }}
      created_at: {{ conversation.created_at }}
      updated_at: {{ conversation.updated_at }}
      read_at: {{ conversation.read_at }}
    {% for message in conversation.messages %}
    [{{ message.role }}] created_at={{ message.created_at }} updated_at={{ message.updated_at }} read_at={{ message.read_at }} {{ message.content }}
    {% endfor %}
    {% endfor %}

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
