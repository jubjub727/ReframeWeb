function ChooseTask(
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

        Stop once you have the right task.

        Context sections:
        - Current user request: the request being routed now.
        - Conversation history: earlier human and agent messages.
        - Session memories: remembered observations for this session.
        - Available tasks: the only tasks that may be selected.
        - Task-choice memories: remembered observations about choosing tasks.

        Optional outputs available in this step:
        - agent_thought: compact routing context to add to the conversation when
          it helps later layers interpret the selected task or the user request.
        - candidate_memory: a vague remembered observation that could be useful to
          preserve.

        Rules:
        - Select exactly one task from Available tasks.
        - selected_task_id must exactly match an available task id.
        - Do not invent task ids.
        - Do not perform the task. Only choose the task.
        - Use optional outputs only when they are useful.
        - Keep agent_thought concise when it is useful.
        - User request may be related to memories that this layer is not yet aware of, simply finish your task without thinking too much if that seems to be the case.
        - Do not generate misleading agent_thoughts that would only be relevant to your lack of memory capabilities.
        - Do not make confident assertions in agent_thoughts only use them to provide observations.

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

