import asyncio
import sys
import os
import json

# Add root to sys.path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.execution.message_bus import message_bus, AgentMessage
from core.routing.task_delegator import ChiefOrchestrator
from core.execution.real_swarm import RealSwarmOrchestrator

async def display_events(bus):
    """Listen to the message bus and print events in real-time."""
    # AWAIT the subscribe call!
    subscriber = await bus.subscribe("all")
    print("📡 [System]: Connected to Agent Message Bus (Live Stream)\n")
    while True:
        msg = await subscriber.get()
        if msg.topic == "system.exit":
            break
            
        print(f"[{msg.sender.upper()}] -> [{msg.receiver.upper() if msg.receiver else 'ALL'}] (Topic: {msg.topic})")
        
        content = msg.content
        if isinstance(content, dict):
            print(json.dumps(content, indent=2, ensure_ascii=False))
        else:
            print(f"💬 {content}")
        print("-" * 60)

async def main():
    print("""
    #########################################################
    #                                                       #
    #    BRAV OS v8.0 - THE REAL AWAKENING (LIVE API)       #
    #    100% Autonomous, LLM-Powered Multi-Agent Swarm     #
    #                                                       #
    #########################################################
    """)
    print("⚠️  ตรวจสอบให้แน่ใจว่าคุณได้ตั้งค่า API_KEY ในไฟล์ .env ของคุณแล้ว (เช่น OPENAI_API_KEY)\n")

    # 1. Use the Global singleton bus
    bus = message_bus

    # 2. Start the Event Display Task
    display_task = asyncio.create_task(display_events(bus))
    
    # Wait a moment for the subscriber to register
    await asyncio.sleep(0.5)

    # 3. Initialize the Real Swarm Engine and Chief Orchestrator
    chief = ChiefOrchestrator(bus=bus)
    swarm = RealSwarmOrchestrator(bus=bus)

    # Start the swarm listener in the background
    swarm_task = asyncio.create_task(swarm.listen_and_execute())

    # 4. Give the Chief Orchestrator a Massive Project
    project_prompt = "ออกแบบระบบ Backend, ตรวจสอบความปลอดภัย, และเขียนเอกสารสำหรับระบบพยากรณ์น้ำท่วมแห่งชาติ (National Flood Prediction System)"
    
    print(f"🎯 [User]: สั่งงานใหญ่: {project_prompt}\n")
    
    # 5. Chief breaks it down and assigns tasks to the real agents!
    await chief.execute_project(project_prompt)

    # Let the swarm run for a bit (In a real app, you'd wait for a "Project Complete" event)
    # We increase sleep time to allow real LLM calls to finish
    await asyncio.sleep(60) 
    
    # Graceful Shutdown
    await bus.publish("all", AgentMessage(sender="system", receiver="all", topic="system.exit", content="Shutting down."))
    
    try:
        await asyncio.wait_for(display_task, timeout=5)
    except asyncio.TimeoutError:
        display_task.cancel()
        
    swarm_task.cancel()
    print("\n🏁 [System]: Demonstration completed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
