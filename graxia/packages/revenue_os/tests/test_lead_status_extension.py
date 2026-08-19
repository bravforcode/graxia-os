"""LeadStatus extension (spec G4): demo/trial/paid for lead→paid KPI."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import LeadStatus
from ..models import Lead


def test_lead_status_has_new_states():
    assert LeadStatus.DEMO == "demo"
    assert LeadStatus.TRIAL == "trial"
    assert LeadStatus.PAID == "paid"


@pytest.mark.asyncio
async def test_lead_accepts_paid_status(db_session: AsyncSession):
    lead = Lead(
        email="lead@example.com",
        name="Test Lead",
        source="organic_search",
        score=50,
        status=LeadStatus.PAID,
    )
    db_session.add(lead)
    await db_session.flush()
    assert lead.status == LeadStatus.PAID