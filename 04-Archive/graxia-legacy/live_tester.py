import asyncio
import sys
import os
import uuid
import logging
from typing import Dict, Any

# Setup Logging
logging.basicConfig(level=logging.INFO)

# Ensure path is correct
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from graxia.services.agent_mesh.agents.cos import ChiefOfStaffAgent
from graxia.packages.bwcp_protocol.models import BWCPMessage, BWCPMessageType, BWCPPriority, RiskClass

async def run_ceo_live_test():
    print("\n" + "="*60)
    print("🚀 [CEO LIVE TEST] STARTING AGENT MESH WORKFORCE")
    print("="*60)
    
    # 1. Setup Chief of Staff
    cos = ChiefOfStaffAgent()
    
    # 2. Create a Mission with actual content for CoS
    mission_id = uuid.uuid4()
    mission_message = BWCPMessage(
        message_id=str(uuid.uuid4()),
        sender_agent="CEO_TELEGRAM",
        receiver_agent="COS",
        mission_id=mission_id,
        type=BWCPMessageType.TASK_ASSIGNMENT,
        priority=BWCPPriority.HIGH,
        risk_class=RiskClass.LOW,
        payload={
            "objective": "Find high-paying Python FastAPI jobs on Upwork and list 3 Hackathons to win prize money.",
            "tenant_id": "ceo_menum_office"
        }
    )
    
    # CoS expects 'content' field in some stubs or internal logic based on .md
    # Let's ensure it has what it needs. Based on cos.py, it uses message.content
    mission_message.content = mission_message.payload['objective']
    mission_message.id = mission_message.message_id
    
    print(f"📡 Mission ID: {mission_id}")
    print(f"🎯 Objective: {mission_message.content}")
    print("-" * 60)
    
    # 3. Trigger Agent Mesh Workflow (Synchronous invoke in this version)
    # The subagent implemented process_message as a sync call to graph.invoke
    print("[*] Dispatching Mission to Chief of Staff...")
    result_state = cos.process_message(mission_message)
    
    print("-" * 60)
    print(f"💰 [MISSION COMPLETE] Status: {result_state['status'].upper()}")
    
    if result_state['status'] == 'complete':
        print("\n📈 WORKFORCE RESULTS:")
        for i, res in enumerate(result_state.get('results', [])):
            # results are task_result BWCPMessages or dicts
            print(f"  Task {i+1}: {res}")
            
        print("\n✅ REVENUE CHANNELS (R1 & R5) SUCCESSFULLY GENERATED OPPORTUNITIES.")
    else:
        print(f"\n❌ MISSION FAILED: {result_state.get('error')}")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(run_ceo_live_test())
