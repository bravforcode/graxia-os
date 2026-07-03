import asyncio

from core.execution.message_bus import AgentMessage, message_bus


async def approve():
    await message_bus.connect()
    msg = AgentMessage(
        sender="Human",
        receiver="System",
        topic="approvals/task_Frontend_Dev",
        content={"status": "approved"},
    )
    await message_bus.publish("approvals/task_Frontend_Dev", msg)
    print("Approval sent.")


if __name__ == "__main__":
    asyncio.run(approve())
