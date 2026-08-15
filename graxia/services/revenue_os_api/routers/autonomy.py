"""Global autonomy mode control. Every route is admin-authenticated (Task 1a) — this
endpoint can turn unattended, money-moving autonomy on."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.core.policy_engine import PolicyEngine
from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.enums import AutonomyMode
from ..dependencies import require_admin_api_key

router = APIRouter(dependencies=[Depends(require_admin_api_key)])


class SetModeRequest(BaseModel):
    mode: AutonomyMode


@router.get("/status")
async def get_status(db: AsyncSession = Depends(get_db)) -> dict:
    mode = await PolicyEngine.get_autonomy_mode(db)
    return {"mode": mode.value}


@router.post("/mode")
async def set_mode(body: SetModeRequest, db: AsyncSession = Depends(get_db)) -> dict:
    mode = await PolicyEngine.set_autonomy_mode(db, body.mode)
    return {"mode": mode.value}
