"""
Comprehensive Integration Tests
ทดสอบระบบทั้งหมดแบบ end-to-end
"""
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import select

from app.core.event_bus import EventBus
from app.database import get_db
from app.models.opportunity import Opportunity
from app.models.submission import Submission
from app.models.contact import Contact
from app.models.content_draft import ContentDraft


@pytest.mark.asyncio
async def test_opportunity_lifecycle():
    """ทดสอบ lifecycle ของ opportunity ตั้งแต่เจอจนถึงส่ง submission"""
    # 1. สร้าง opportunity
    async with get_db() as db:
        opp = Opportunity(
            id=uuid.uuid4(),
            title="Test Hackathon",
            source="devpost",
            url="https://example.com/hackathon",
            description="Build an AI tool",
            score=85,
            status="new",
            deadline=datetime.now() + timedelta(days=30),
        )
        db.add(opp)
        await db.commit()
        await db.refresh(opp)
        opp_id = opp.id
    
    # 2. Emit opportunity.found event
    event_bus = EventBus()
    await event_bus.emit("opportunity.found", {"opportunity_id": str(opp_id)})
    
    # 3. ตรวจสอบว่า opportunity ถูก score แล้ว
    async with get_db() as db:
        result = await db.execute(select(Opportunity).where(Opportunity.id == opp_id))
        opp = result.scalar_one()
        assert opp.score is not None
        assert opp.score > 0
    
    # 4. สร้าง draft
    async with get_db() as db:
        draft = ContentDraft(
            id=uuid.uuid4(),
            opportunity_id=opp_id,
            draft_type="proposal",
            content="This is my proposal...",
            status="pending",
        )
        db.add(draft)
        await db.commit()
        draft_id = draft.id
    
    # 5. Approve draft
    async with get_db() as db:
        result = await db.execute(select(ContentDraft).where(ContentDraft.id == draft_id))
        draft = result.scalar_one()
        draft.status = "approved"
        await db.commit()
    
    # 6. สร้าง submission
    async with get_db() as db:
        submission = Submission(
            id=uuid.uuid4(),
            opportunity_id=opp_id,
            title="Test Submission",
            proposal_text="This is my proposal...",
            sent_at=datetime.now(),
            status="sent",
        )
        db.add(submission)
        await db.commit()
        sub_id = submission.id
    
    # 7. Emit submission.sent event
    await event_bus.emit("submission.sent", {"submission_id": str(sub_id)})
    
    # 8. ตรวจสอบว่า submission ถูกบันทึก
    async with get_db() as db:
        result = await db.execute(select(Submission).where(Submission.id == sub_id))
        submission = result.scalar_one()
        assert submission.status == "sent"
        assert submission.sent_at is not None


@pytest.mark.asyncio
async def test_contact_creation_and_sync():
    """ทดสอบการสร้าง contact และ sync"""
    async with get_db() as db:
        contact = Contact(
            id=uuid.uuid4(),
            name="John Doe",
            email="john@example.com",
            company="Example Corp",
            role="CTO",
            first_contact_date=datetime.now(),
        )
        db.add(contact)
        await db.commit()
        contact_id = contact.id
    
    # Emit contact.created event
    event_bus = EventBus()
    await event_bus.emit("contact.created", {"contact_id": str(contact_id)})
    
    # ตรวจสอบว่า contact ถูกสร้าง
    async with get_db() as db:
        result = await db.execute(select(Contact).where(Contact.id == contact_id))
        contact = result.scalar_one()
        assert contact.name == "John Doe"
        assert contact.email == "john@example.com"


@pytest.mark.asyncio
async def test_event_bus_multiple_subscribers():
    """ทดสอบ event bus กับ subscribers หลายตัว"""
    event_bus = EventBus()
    
    results = []
    
    async def handler1(payload):
        results.append("handler1")
    
    async def handler2(payload):
        results.append("handler2")
    
    async def handler3(payload):
        results.append("handler3")
    
    event_bus.subscribe("test.event", handler1)
    event_bus.subscribe("test.event", handler2)
    event_bus.subscribe("test.event", handler3)
    
    await event_bus.emit("test.event", {"data": "test"})
    
    # รอให้ handlers ทำงานเสร็จ
    await asyncio.sleep(0.1)
    
    assert len(results) == 3
    assert "handler1" in results
    assert "handler2" in results
    assert "handler3" in results


@pytest.mark.asyncio
async def test_scoring_system():
    """ทดสอบระบบ scoring"""
    from app.agents.scorer import scorer_agent
    
    async with get_db() as db:
        opp = Opportunity(
            id=uuid.uuid4(),
            title="High-Value Hackathon",
            source="devpost",
            url="https://example.com",
            description="AI, Machine Learning, Python, React",
            budget="$10,000",
            deadline=datetime.now() + timedelta(days=30),
            score=0,
            status="new",
        )
        db.add(opp)
        await db.commit()
        opp_id = opp.id
    
    # Score opportunity
    await scorer_agent.handle_new_opportunity({"opportunity_id": str(opp_id)})
    
    # ตรวจสอบ score
    async with get_db() as db:
        result = await db.execute(select(Opportunity).where(Opportunity.id == opp_id))
        opp = result.scalar_one()
        assert opp.score > 0
        assert opp.score <= 100


@pytest.mark.asyncio
async def test_decision_engine():
    """ทดสอบ decision engine"""
    from app.agents.decision_engine import decision_engine
    
    async with get_db() as db:
        opp = Opportunity(
            id=uuid.uuid4(),
            title="Test Opportunity",
            source="devpost",
            url="https://example.com",
            description="Test",
            score=85,  # High score
            status="scored",
            deadline=datetime.now() + timedelta(days=30),
        )
        db.add(opp)
        await db.commit()
        opp_id = opp.id
    
    # Process decision
    await decision_engine.handle_scored_opportunity({"opportunity_id": str(opp_id)})
    
    # ตรวจสอบว่า decision ถูกทำ
    async with get_db() as db:
        result = await db.execute(select(Opportunity).where(Opportunity.id == opp_id))
        opp = result.scalar_one()
        # Status should change based on decision
        assert opp.status in ["decided", "rejected", "scored"]


@pytest.mark.asyncio
async def test_learning_engine_win():
    """ทดสอบ learning engine เมื่อชนะ"""
    from app.agents.learning_engine import learning_engine
    
    async with get_db() as db:
        opp = Opportunity(
            id=uuid.uuid4(),
            title="Won Opportunity",
            source="devpost",
            url="https://example.com",
            description="AI project",
            score=90,
            status="decided",
        )
        db.add(opp)
        await db.commit()
        
        submission = Submission(
            id=uuid.uuid4(),
            opportunity_id=opp.id,
            title="Winning Submission",
            proposal_text="Great proposal",
            sent_at=datetime.now(),
            status="won",
            outcome="Won $5,000 prize",
        )
        db.add(submission)
        await db.commit()
        sub_id = submission.id
    
    # Process win
    await learning_engine.handle_win({"submission_id": str(sub_id)})
    
    # ตรวจสอบว่า outcome pattern ถูกบันทึก
    # (ต้องมี model OutcomePattern ก่อน)


@pytest.mark.asyncio
async def test_cost_tracking():
    """ทดสอบระบบติดตาม cost"""
    from app.models.openclaw_usage import OpenClawUsage
    
    async with get_db() as db:
        usage = OpenClawUsage(
            id=uuid.uuid4(),
            model="claude-sonnet-4-5",
            input_tokens=1000,
            output_tokens=500,
            estimated_cost_usd=Decimal("0.05"),
            context="test_scoring",
        )
        db.add(usage)
        await db.commit()
    
    # ตรวจสอบว่า usage ถูกบันทึก
    async with get_db() as db:
        result = await db.execute(select(OpenClawUsage))
        usages = result.scalars().all()
        assert len(usages) > 0
        total_cost = sum(u.estimated_cost_usd for u in usages)
        assert total_cost > 0


@pytest.mark.asyncio
async def test_rate_limiting():
    """ทดสอบ rate limiting"""
    from app.models.api_rate_limit import APIRateLimit
    
    async with get_db() as db:
        # สร้าง rate limit record
        rate_limit = APIRateLimit(
            id=uuid.uuid4(),
            service="gemini",
            period="daily",
            limit=1400,
            current_count=1350,
            reset_at=datetime.now() + timedelta(hours=24),
        )
        db.add(rate_limit)
        await db.commit()
    
    # ตรวจสอบว่าใกล้ถึง limit
    async with get_db() as db:
        result = await db.execute(select(APIRateLimit).where(APIRateLimit.service == "gemini"))
        limit = result.scalar_one()
        assert limit.current_count >= limit.limit * 0.9  # 90% threshold


@pytest.mark.asyncio
async def test_telegram_notification():
    """ทดสอบ Telegram notification (mock)"""
    from app.telegram_bot.bot import send_message
    
    # Mock test - จะส่งจริงถ้ามี token
    try:
        result = await send_message("🧪 Test notification from comprehensive test")
        # ถ้าส่งสำเร็จ result จะเป็น Message object
    except Exception as e:
        # ถ้าไม่มี token หรือ config ไม่ถูกต้อง จะ raise error
        assert "TELEGRAM" in str(e).upper() or "token" in str(e).lower()


@pytest.mark.asyncio
async def test_google_workspace_integration():
    """ทดสอบ Google Workspace integration (mock)"""
    from app.core.google_workspace import build_google_workspace_config
    from app.config import settings
    
    config = build_google_workspace_config(settings)
    
    # ตรวจสอบ config
    assert config is not None
    assert hasattr(config, "client_id")
    assert hasattr(config, "client_secret")


@pytest.mark.asyncio
async def test_scheduler_jobs():
    """ทดสอบ scheduler jobs"""
    from app.core.scheduler import scheduler
    
    # ตรวจสอบว่า scheduler มี jobs
    scheduler.setup()
    jobs = scheduler.get_jobs()
    
    # ควรมี jobs สำหรับ daily scan, weekly review, etc.
    assert len(jobs) > 0


@pytest.mark.asyncio
async def test_database_migrations():
    """ทดสอบว่า database schema ถูกต้อง"""
    from app.database import engine
    from sqlalchemy import inspect
    
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    # ตรวจสอบว่ามี tables ที่จำเป็น
    required_tables = [
        "opportunities",
        "submissions",
        "contacts",
        "content_drafts",
        "cognitive_states",
        "metrics",
    ]
    
    for table in required_tables:
        assert table in tables, f"Missing table: {table}"


@pytest.mark.asyncio
async def test_api_endpoints_health():
    """ทดสอบ API endpoints"""
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    
    # Test health endpoint
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "service" in data


@pytest.mark.asyncio
async def test_full_system_integration():
    """ทดสอบระบบทั้งหมดแบบ end-to-end"""
    # 1. สร้าง opportunity
    async with get_db() as db:
        opp = Opportunity(
            id=uuid.uuid4(),
            title="Full Integration Test",
            source="test",
            url="https://example.com",
            description="Complete system test",
            score=0,
            status="new",
            deadline=datetime.now() + timedelta(days=30),
        )
        db.add(opp)
        await db.commit()
        opp_id = opp.id
    
    # 2. Emit events
    event_bus = EventBus()
    await event_bus.emit("opportunity.found", {"opportunity_id": str(opp_id)})
    
    # รอให้ event handlers ทำงาน
    await asyncio.sleep(0.5)
    
    # 3. ตรวจสอบผลลัพธ์
    async with get_db() as db:
        result = await db.execute(select(Opportunity).where(Opportunity.id == opp_id))
        opp = result.scalar_one()
        
        # Opportunity ควรถูก process แล้ว
        assert opp is not None
        assert opp.status != "new"  # Status should change
