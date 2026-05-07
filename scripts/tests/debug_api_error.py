import sys
sys.path.insert(0, 'backend')
import asyncio
from decimal import Decimal
from uuid import UUID
from datetime import datetime
from app.database import AsyncSessionLocal
from app.models.skillsmp_skill import SkillsMPSkill
from app.schemas.skillsmp import SkillsMPSkillOut, SkillsMPSkillList
from sqlalchemy import select, func, desc

async def test():
    async with AsyncSessionLocal() as db:
        # Query like API does
        query = select(SkillsMPSkill).where(SkillsMPSkill.is_deleted_at_source == False)
        
        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = await db.scalar(count_query)
        print(f"Total: {total}")
        
        # Get skills
        query = query.order_by(
            desc(SkillsMPSkill.effectiveness_score),
            desc(SkillsMPSkill.usage_count),
            SkillsMPSkill.name
        ).offset(0).limit(2)
        
        result = await db.execute(query)
        skills = result.scalars().all()
        print(f"Skills: {len(skills)}")
        
        # Try to serialize
        items = []
        for skill in skills:
            print(f"\nSkill: {skill.name}")
            print(f"  id: {skill.id} (type: {type(skill.id)})")
            print(f"  external_id: {skill.external_id}")
            print(f"  success_rate: {skill.success_rate} (type: {type(skill.success_rate)})")
            print(f"  effectiveness_score: {skill.effectiveness_score}")
            print(f"  skill_metadata: {skill.skill_metadata}")
            
            try:
                # Try manual conversion first
                data = {
                    "id": skill.id,
                    "external_id": skill.external_id,
                    "source_type": skill.source_type,
                    "name": skill.name,
                    "description": skill.description,
                    "content_preview": (skill.content or "")[:500] + "..." if skill.content and len(skill.content) > 500 else skill.content,
                    "metadata": skill.skill_metadata or {},
                    "usage_count": skill.usage_count or 0,
                    "success_rate": skill.success_rate or Decimal("0"),
                    "effectiveness_score": skill.effectiveness_score or Decimal("0"),
                    "last_used_at": skill.last_used_at,
                    "context_tags": skill.context_tags or [],
                    "trigger_patterns": skill.trigger_patterns or [],
                    "related_skill_ids": skill.related_skill_ids or [],
                    "version": skill.version or 1,
                    "has_ai_improvement": bool(skill.ai_improved_version),
                    "created_at": skill.created_at,
                    "updated_at": skill.updated_at,
                    "last_synced_at": skill.last_synced_at,
                }
                print(f"  Data prepared OK")
                
                out = SkillsMPSkillOut(**data)
                print(f"  Schema OK: {out.name}")
                items.append(out)
            except Exception as e:
                print(f"  ERROR: {e}")
                import traceback
                traceback.print_exc()
        
        # Build response
        try:
            response = SkillsMPSkillList(
                total=total or 0,
                items=items,
                page=1,
                limit=2,
            )
            print(f"\n✅ Response built OK")
            print(response.model_dump_json(indent=2)[:500])
        except Exception as e:
            print(f"\n❌ Response error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
