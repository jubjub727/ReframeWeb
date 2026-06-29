enum ConversationMode {
  WakeCommand
  ContinuousConversation
}

enum PlaybackState {
  Idle
  Speaking
  Interrupted
}

enum HostRoute {
  ContinueListening
  CancelSpeech
  SpeakToUser
  UseNativeWindow
  UseTransport
  UpdateMemory
}

class HostAction {
  route HostRoute
  reason string
}

class AgentTurnPlan {
  mode ConversationMode
  heard_user_speech string
  interpreted_intent string
  should_interrupt_playback bool
  actions HostAction[]
  spoken_response string
}

function PlanConversationTurn(
  transcript: string,
  conversation_mode: ConversationMode,
  playback_state: PlaybackState
) -> AgentTurnPlan {
  client ConversationTurnPlanningModel
  prompt #"
    You are planning one turn of the ReframeWeb Agent Host.

    ReframeWeb starts from the user's spoken interaction. The Python Agent Host
    receives audio, transcription, and playback state, then uses this BAML flow
    to decide what the agentic runtime should do next.

    The system is not a browser automation layer. It is an agent-native workflow
    environment that will route through native windows, Visual Panels, transport
    layer calls, WebAssembly Stores, Data Lenses, Compute Modules, and memory as
    those pieces become available.

    Transcript:
    {{ transcript }}

    Conversation mode:
    {{ conversation_mode }}

    Playback state:
    {{ playback_state }}

    Return the next host-level plan.
    {{ ctx.output_format }}
  "#
}
