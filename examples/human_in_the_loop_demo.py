import asyncio
import sys
import os

# Add root to sys.path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.execution.state_graph import WorkflowGraph, WorkflowState

async def marketing_agent(state: WorkflowState) -> WorkflowState:
    print("\n[📣 MarketingAgent]: สร้างแคมเปญ 'Summer Sale 2026'")
    print("[📣 MarketingAgent]: ขอกบประมาณ $50,000 สำหรับ Facebook Ads และ Influencers")
    state.metadata["budget_request"] = 50000
    state.metadata["plan"] = "Summer Sale 2026"
    return state

async def financial_auditor(state: WorkflowState) -> WorkflowState:
    budget = state.metadata.get("budget_request", 0)
    approved = state.metadata.get("human_approved", False)

    print(f"\n[💰 FinancialAuditor]: ตรวจสอบงบประมาณ ${budget}...")

    if approved:
        print("[💰 FinancialAuditor]: ✅ ตรวจพบการอนุมัติจากผู้บริหารแล้ว. อนุญาตให้ดำเนินการต่อ.")
        state.interrupt = False
    elif budget > 10000:
        print("[💰 FinancialAuditor]: งบประมาณสูงเกินเกณฑ์อำนาจตัดสินใจของ AI")
        print("[💰 FinancialAuditor]: 🚩 ส่งเรื่องให้ผู้บริหาร (Human) พิจารณา")
        state.interrupt = True  # หยุดรอคน
    else:
        print("[💰 FinancialAuditor]: งบประมาณผ่านเกณฑ์อนุมัติอัตโนมัติ")
    return state

async def execution_agent(state: WorkflowState) -> WorkflowState:
    print("\n" + "="*50)
    print("[🚀 ExecutionAgent]: ได้รับอนุมัติเป็นทางการแล้ว!")
    print(f"[🚀 ExecutionAgent]: กำลังดำเนินการโอนงบประมาณ ${state.metadata['budget_request']} ไปยังแผนกการตลาด...")
    print("[🚀 ExecutionAgent]: 💸 [TRANSFER SUCCESSFUL] 💸")
    print("[🚀 ExecutionAgent]: ✅ งานทุกอย่างเสร็จสมบูรณ์!")
    print("="*50)
    return state

async def main():
    # 1. สร้าง Graph
    graph = WorkflowGraph()

    # 2. เพิ่ม Node (ผู้เชี่ยวชาญ)
    graph.add_node("marketing", marketing_agent)
    graph.add_node("auditor", financial_auditor)
    graph.add_node("executor", execution_agent)

    # 3. กำหนดเส้นทางการเดิน (Edges)
    graph.set_entry_point("marketing")
    graph.add_edge("marketing", "auditor")
    graph.add_edge("auditor", "executor")
    graph.add_edge("executor", "__end__")

    # 4. เริ่มรันครั้งแรก
    print("--- 🤖 เริ่มต้น Workflow อัตโนมัติ ---")
    state = WorkflowState(input={"task": "ขออนุมัติงบการตลาด"})
    state = await graph.run(state)

    # 5. จุดตรวจสอบ Human-in-the-loop
    if state.interrupt:
        print("\n" + "="*50)
        print("🚨 ระบบหยุดรอ: ต้องการการตัดสินใจจากคุณ (ADMIN)")
        print(f"งาน: {state.input['task']}")
        print(f"รายละเอียด: {state.metadata['plan']} - งบประมาณ: ${state.metadata['budget_request']}")
        print("="*50)

        user_input = input("\nคุณต้องการอนุมัติโครงการนี้หรือไม่? (yes/no): ").lower()

        if user_input == "yes":
            print("\n✅ คุณอนุมัติแล้ว! กำลังบันทึกสิทธิ์และสั่งการ AI ให้ทำงานต่อ...")
            state.metadata["human_approved"] = True # บันทึกว่าคนอนุมัติแล้ว
            await graph.resume(state)
        else:
            print("\n❌ คุณปฏิเสธโครงการ. Workflow ถูกระงับ.")


if __name__ == "__main__":
    asyncio.run(main())
