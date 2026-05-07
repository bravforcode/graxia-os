from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.cognitive_state import CognitiveState
from app.schemas.cognitive_state import CognitiveStateCreate, CognitiveStateOut

router = APIRouter(prefix="/cognitive", tags=["cognitive"])


@router.get("/today", response_model=CognitiveStateOut)
async def get_today(db: AsyncSession = Depends(get_db)):
    from datetime import date

    from app.core.identity import identity

    defaults = identity.get_cognitive_defaults()
    try:
        result = await db.execute(select(CognitiveState).order_by(desc(CognitiveState.date)).limit(1))
        state = result.scalar_one_or_none()
        if not state:
            from datetime import date as d_cls

            state = CognitiveState(
                date=d_cls.today(),
                energy=defaults["default_energy"],
                stress=defaults["default_stress"],
                available_hours_this_week=defaults["default_available_hours"],
            )
            db.add(state)
            await db.commit()
            await db.refresh(state)
        return state
    except Exception:
        return CognitiveStateOut(
            id=uuid4(),
            date=date.today(),
            energy=defaults["default_energy"],
            stress=defaults["default_stress"],
            available_hours_this_week=defaults["default_available_hours"],
            exam_pressure=0,
            mood_note=None,
            created_at=None,
        )


@router.post("/checkin", response_model=CognitiveStateOut)
async def checkin(data: CognitiveStateCreate, db: AsyncSession = Depends(get_db)):
    from datetime import date
    try:
        today = date.today()
        result = await db.execute(select(CognitiveState).where(CognitiveState.date == today))
        state = result.scalar_one_or_none()
        if state:
            for k, v in data.model_dump().items():
                setattr(state, k, v)
        else:
            state = CognitiveState(date=today, **data.model_dump())
            db.add(state)
        await db.commit()
        await db.refresh(state)
        from app.core.event_bus import event_bus

        await event_bus.emit(
            "cognitive_state.updated",
            {
                "energy": state.energy,
                "stress": state.stress,
                "available_hours": state.available_hours_this_week,
            },
        )
        return state
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cognitive state could not be saved because the database is unavailable: {exc}",
        ) from exc
