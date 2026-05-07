import sys
sys.path.insert(0, 'backend')
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.core.agent_skill_bridge import AgentSkillBridge

async def test():
    async with AsyncSessionLocal() as db:
        bridge = AgentSkillBridge(db)
        try:
            results = await bridge.get_skills_for_task(
                agent_id="agent-001",
                task_description="python data analysis",
                limit=2,
            )
            print(f"✅ Got {len(results)} results")
            for r in results:
                print(f"  - {r['name']}: {r['relevance_score']:.2f}")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
