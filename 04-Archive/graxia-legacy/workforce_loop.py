import asyncio
import sys
import os
import time
import logging

# Ensure path is correct
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from graxia.services.agent_mesh.agents.cos import ChiefOfStaffAgent
from graxia.services.agent_mesh.agents.visionary import VisionaryAgent
from graxia.packages.logging.python.notifications import send_telegram_message

# Configure basic logging to focus on the loop
logging.basicConfig(level=logging.WARNING)

async def start_revenue_machine(iterations: int = 3):
    print("\n" + "💰" * 20)
    print("🚀 GRAXIA OS: AUTOPILOT REVENUE ENGINE ACTIVE")
    print("💰" * 20 + "\n")
    
    send_telegram_message("🚀 *GRAXIA OS:* Autopilot Revenue Engine Started.")
    
    visionary = VisionaryAgent()
    cos = ChiefOfStaffAgent()
    
    count = 0
    try:
        while count < iterations:
            count += 1
            print(f"🔄 [LOOP {count}] Visionary is scanning for opportunities...")
            
            # 1. Visionary creates a mission autonomously
            mission_message = visionary.generate_autonomous_mission()
            
            # 2. Feed the mission to the Chief of Staff
            print(f"📡 [LOOP {count}] Mission dispatched to Chief of Staff: {mission_message.mission_id}")
            
            send_telegram_message(f"🔄 *Cycle {count}:* Visionary generated new mission:\n`{mission_message.content}`")
            
            result_state = cos.process_message(mission_message)
            
            # 3. Log the outcome
            if result_state['status'] == 'complete':
                print(f"✅ [LOOP {count}] Mission Success! Revenue pipeline updated.")
                summary = result_state.get('results', [])
                
                # Send summary to Telegram
                msg = f"✅ *Mission Success:* Cycle {count}\nObjective: `{mission_message.content}`\n\n*Results:*\n"
                for res in summary:
                    msg += f"- {res}\n"
                send_telegram_message(msg)
                
            else:
                print(f"⚠️ [LOOP {count}] Mission encountered issues: {result_state.get('error')}")
                send_telegram_message(f"⚠️ *Mission Warning:* Cycle {count} encountered issues.")
            
            print("-" * 40)
            if count < iterations:
                print("⏳ Waiting for next growth cycle (simulated 3s)...")
                await asyncio.sleep(3) # Simulate time between missions
                
    except KeyboardInterrupt:
        print("\n🛑 Revenue Machine stopped by CEO.")
        send_telegram_message("🛑 *Revenue Machine stopped by CEO.*")
    
    print("\n" + "="*40)
    print(f"🏁 GROWTH CYCLE COMPLETE: {count} missions processed.")
    print("="*40 + "\n")
    
    send_telegram_message(f"🏁 *Growth Cycle Complete:* {count} missions processed.")

if __name__ == "__main__":
    # We run 3 iterations for this proof of work
    asyncio.run(start_revenue_machine(iterations=3))
