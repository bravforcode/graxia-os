"""Ask Laya System-1 for an opportunity's action priority.

Used only when the llm provider is unavailable. Any Laya failure returns None,
so the caller keeps the heuristic priority.
"""

import logging

import httpx

from app.core.laya_client import LayaClient, LayaError

logger = logging.getLogger(__name__)

ACTION_PRIORITIES = ("do_now", "queue", "skip")

QUESTIONS = {
    "action_priority": {
        "type": "choice",
        "instructions": (
            "Pick the action for this opportunity. do_now: act this week. "
            "queue: keep for later. skip: not worth the founder's time."
        ),
        "criteria": list(ACTION_PRIORITIES),
    }
}


async def laya_action_priority(client: LayaClient, opp_data: dict) -> str | None:
    try:
        answers = await client.systemone(opp_data, QUESTIONS)
    except (LayaError, httpx.HTTPError) as e:
        logger.warning("laya action_priority unavailable: %s", e)
        return None
    choice = answers.get("action_priority", {}).get("choice")
    if choice not in ACTION_PRIORITIES:
        logger.warning("laya returned unknown action_priority: %r", choice)
        return None
    return choice
