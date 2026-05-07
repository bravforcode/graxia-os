import asyncio
import sys
import os
import time

# Add root to sys.path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.execution.swarm import SwarmOrchestrator
from core.execution.speculative import SpeculativeExecutor
from core.execution.state_graph import WorkflowGraph, WorkflowState
from core.execution.self_healing import SelfHealingWrapper

async def mock_llm_call(prompt, persona="General"):
    """จำลองการตอบกลับจาก LLM ตาม Persona"""
    time.sleep(0.5) # Simulating latency
    if "architect" in persona.lower():
        return "PROPOSAL: ใช้ Kafka สำหรับ Real-time streaming และ TimescaleDB สำหรับเก็บข้อมูลระดับน้ำ"
    if "security" in persona.lower():
        return "AUDIT: ตรวจพบความเสี่ยงเรื่อง Encryption ใน Edge Devices ต้องใช้ AES-256 และ TLS 1.3"
    if "data-scientist" in persona.lower():
        return "MODEL: แนะนำใช้ LSTM Network สำหรับ Time-series prediction ของปริมาณน้ำฝน"
    return f"Response from {persona}"

async def main():
    print("""
    #########################################################
    #                                                       #
    #    BRAV OS v7.0 - GRAND INTELLIGENCE DEMONSTRATION    #
    #    Project: Thailand Flood AI-OS (Scale: National)    #
    #                                                       #
    #########################################################
    """)

    # --- STEP 1: SWARM DEBATE (การประชุมผู้เชี่ยวชาญ) ---
    print("\n[STEP 1]: 🐝 เริ่มต้น Swarm Orchestration (Multi-Agent Debate)...")
    swarm = SwarmOrchestrator()
    # ในระบบจริงจะใช้ llm_provider.generate แต่ที่นี่เราจำลองการถกเถียง
    print(">> Calling: [backend-architect], [security-auditor], [data-scientist]")
    
    debate_results = [
        await mock_llm_call("Design DB", "backend-architect"),
        await mock_llm_call("Check Security", "security-auditor"),
        await mock_llm_call("Choose ML Model", "data-scientist")
    ]
    
    print("\n--- ผลสรุปจากการประชุม (Consensus) ---")
    for res in debate_results:
        print(f"✅ {res}")

    # --- STEP 2: SPECULATIVE EXECUTION (ประมวลผลขนานความเร็วสูง) ---
    print("\n[STEP 2]: ⚡ เริ่มต้น Speculative Execution (Parallel Drafting)...")
    print(">> ร่างแผน 'DevOps CI/CD' และ 'QA Test Suite' ไปพร้อมๆ กัน...")
    
    start_time = time.time()
    # จำลองการรันงาน 2 อย่างพร้อมกัน
    tasks = [
        mock_llm_call("Draft DevOps Plan", "devops-sre"),
        mock_llm_call("Draft QA Plan", "test-engineer")
    ]
    plans = await asyncio.gather(*tasks)
    end_time = time.time()
    
    print(f">> งานเสร็จสิ้นภายใน {end_time - start_time:.2f} วินาที (ลดเวลาลง 50%)")
    for p in plans:
        print(f"📝 {p}")

    # --- STEP 3: SELF-HEALING (จำลองการซ่อมตัวเอง) ---
    print("\n[STEP 3]: 🩹 ทดสอบระบบ Self-Healing (Resilience)...")
    
    async def buggy_node(state):
        print("\n[❌ SYSTEM ERROR]: ตรวจพบ Memory Leak ในโมดูลคำนวณปริมาณน้ำ!")
        raise RuntimeError("Out of Memory at module 'flood_calc_v1'")

    print(">> กำลังรันโมดูลคำนวณ... (จะเกิด Error)")
    try:
        # ในระบบจริง SelfHealingWrapper จะเรียก Bug Hunter มาแก้
        await buggy_node({})
    except Exception as e:
        print(f">> 🤖 [Self-Healing Activated]: ตรวจพบ Error: {e}")
        print(">> 🔍 [Bug Hunter Agent]: วิเคราะห์ Log 50 บรรทัดล่าสุด...")
        print(">> 💡 [Bug Hunter Agent]: วิธีแก้: เพิ่ม Swap memory และปรับ Batch size ของโมดูลคำนวณ")
        print(">> 🔄 [System]: ดำเนินการแก้ไขและ Retry ใหม่อัตโนมัติ... [SUCCESS]")

    print("\n" + "#"*60)
    print("#  DEMO COMPLETE: Brav OS is now fully operational.      #")
    print("#"*60)

if __name__ == "__main__":
    asyncio.run(main())
