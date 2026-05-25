"""
Onboarding wizard API.
5-step flow: welcome → profile → first_scan → complete
Stores progress, allows resume, guards dashboard access.
"""
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

class OnboardingStep(str):
    """Onboarding step identifiers."""
    WELCOME = "welcome"
    PROFILE = "profile"
    FIRST_SCAN = "first_scan"
    COMPLETE = "complete"


class ProfileData(BaseModel):
    """User profile data for onboarding step 2."""
    full_name: str = Field(..., min_length=1, max_length=255)
    title: str | None = Field(None, max_length=100)
    company: str | None = Field(None, max_length=100)
    location: str | None = Field(None, max_length=100)
    bio: str | None = Field(None, max_length=2000)
    skills: list[str] = Field(default_factory=list, max_length=50)
    industries: list[str] = Field(default_factory=list, max_length=20)
    goals: list[str] = Field(default_factory=list, max_length=10)


class OnboardingState(BaseModel):
    """Current onboarding state response."""
    user_id: str
    current_step: str
    completed_steps: list[str]
    profile_data: dict[str, Any] | None
    first_scan_completed: bool
    is_complete: bool
    required: bool  # Added to satisfy tests
    started_at: str
    updated_at: str


class OnboardingProgress(BaseModel):
    """Update onboarding progress."""
    step: str = Field(..., pattern="^(welcome|profile|first_scan|complete)$")
    data: dict[str, Any] | None = None


def _get_user_state(user: User) -> dict[str, Any]:
    """Determine state dynamically from the User model in the database."""
    is_complete = bool(user.onboarding_completed_at)
    
    # Simple derivation of current state
    if is_complete:
        current_step = OnboardingStep.COMPLETE
        completed_steps = [OnboardingStep.WELCOME, OnboardingStep.PROFILE, OnboardingStep.FIRST_SCAN, OnboardingStep.COMPLETE]
    elif user.full_name:
        current_step = OnboardingStep.FIRST_SCAN
        completed_steps = [OnboardingStep.WELCOME, OnboardingStep.PROFILE]
    else:
        current_step = OnboardingStep.WELCOME
        completed_steps = []
        
    return {
        "user_id": str(user.id),
        "current_step": current_step,
        "completed_steps": completed_steps,
        "profile_data": {"full_name": user.full_name} if user.full_name else None,
        "first_scan_completed": is_complete,
        "is_complete": is_complete,
        "required": not is_complete,
        "started_at": user.created_at.isoformat() if user.created_at else datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/state", response_model=OnboardingState)
async def get_onboarding_state(
    user: User = Depends(get_current_user),
) -> OnboardingState:
    """Get current onboarding state for logged-in user."""
    state = _get_user_state(user)
    return OnboardingState(**state)


@router.post("/progress")
async def update_onboarding_progress(
    progress: OnboardingProgress,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OnboardingState:
    """
    Advance onboarding step.
    Validates step order, saves data, triggers side effects.
    """
    state = _get_user_state(user)

    # Validate step order
    step_order = [OnboardingStep.WELCOME, OnboardingStep.PROFILE, OnboardingStep.FIRST_SCAN, OnboardingStep.COMPLETE]
    current_idx = step_order.index(state["current_step"])
    new_idx = step_order.index(progress.step)

    if new_idx > current_idx + 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot skip steps. Current: {state['current_step']}, Requested: {progress.step}",
        )

    # Handle step-specific logic
    if progress.step == OnboardingStep.PROFILE and progress.data:
        try:
            profile = ProfileData(**progress.data)
            user.full_name = profile.full_name
            await db.commit()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid profile data: {e}",
            )

    elif progress.step == OnboardingStep.FIRST_SCAN:
        # Trigger first scan (async task)
        import asyncio

        from app.tasks.daily_scan import run_daily_scan
        asyncio.create_task(run_daily_scan())

    elif progress.step == OnboardingStep.COMPLETE:
        user.onboarding_completed_at = datetime.now(UTC)
        await db.commit()

    return OnboardingState(**_get_user_state(user))


@router.post("/skip")
async def skip_onboarding(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OnboardingState:
    """
    Skip onboarding (mark complete with minimal data).
    Allows power users to bypass wizard.
    """
    user.onboarding_completed_at = datetime.now(UTC)
    await db.commit()
    return OnboardingState(**_get_user_state(user))


@router.get("/required")
async def is_onboarding_required(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Check if user must complete onboarding before accessing dashboard.
    Used by frontend router guard.
    """
    return {
        "required": not bool(user.onboarding_completed_at),
        "current_step": _get_user_state(user)["current_step"],
    }
