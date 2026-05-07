import sys
sys.path.insert(0, 'backend')
import asyncio
from app.database import AsyncSessionLocal
from app.core.skill_recommender import SkillRecommender

async def test():
    async with AsyncSessionLocal() as db:
        recommender = SkillRecommender(db)
        try:
            # Test without cache
            results = await recommender.recommend(
                task_context="python data analysis",
                preferred_types=[],
                limit=3,
                use_cache=False,  # Disable cache
            )
            print(f"✅ Got {len(results)} recommendations")
            for r in results:
                print(f"  - {r.name}: {r.score:.2f}")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
