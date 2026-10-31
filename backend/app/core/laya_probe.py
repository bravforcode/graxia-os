"""Ask Laya System-1 one choice question end to end.

Run inside the backend container, with the SSH tunnel to laya-serve open:
    python -m app.core.laya_probe
Exit 0 means Laya answered with a known criterion.
"""

import asyncio
import sys

from app.core.laya_client import LayaClient, laya_client_from_settings

STATE = "Customer asks for a refund on an order delivered two days ago."
QUESTIONS = {
    "action": {
        "type": "choice",
        "instructions": "Pick the best action",
        "criteria": ["approve_refund", "reject_refund"],
    }
}


async def probe(client: LayaClient) -> str:
    answers = await client.systemone(STATE, QUESTIONS)
    choice = answers["action"].get("choice")
    if choice not in QUESTIONS["action"]["criteria"]:
        raise RuntimeError(f"laya returned unknown choice: {choice!r}")
    return choice


def main() -> int:
    choice = asyncio.run(probe(laya_client_from_settings()))
    print(f"laya ok choice={choice}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
