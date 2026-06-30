from __future__ import annotations

from reframe_agent_host.baml_client import b, types


class ConversationPlanner:
    async def plan(
        self,
        transcript: str,
        conversation_mode: types.ConversationMode,
        playback_state: types.PlaybackState,
    ) -> types.AgentTurnPlan:
        return await b.PlanConversationTurn(
            transcript=transcript,
            conversation_mode=conversation_mode,
            playback_state=playback_state,
        )
