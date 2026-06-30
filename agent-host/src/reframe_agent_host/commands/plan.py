from __future__ import annotations

import json

from reframe_agent_host.baml_client import b, types


async def run_plan_turn(
    transcript: str,
    mode: types.ConversationMode,
    playback_state: types.PlaybackState,
) -> int:
    result = await b.PlanConversationTurn(
        transcript=transcript,
        conversation_mode=mode,
        playback_state=playback_state,
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0
