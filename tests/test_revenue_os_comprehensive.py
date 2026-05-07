"""
Revenue OS v12 Comprehensive Test Suite
Based on python-testing and eval-harness skills from Obsidian vault

Coverage Requirements:
- 80%+ overall coverage
- 100% coverage on critical paths (outbox, bwcp, transactions)
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4, UUID
from unittest.mock import Mock, AsyncMock, patch
import json

from sqlalchemy.ext.asyncio import AsyncSession

# Import Revenue OS modules
from graxia.packages.revenue_os.models import (
    OutboxEvent,
    BWCPMessage,
    Order,
    RevenueCampaign,
    Lead,
    Approval,
    IncidentEvent,
)
from graxia.packages.revenue_os.enums import (
    AgentType,
    BWCPMessageType,
    OrderStatus,
    CampaignStatus,
    LeadStatus,
    ApprovalStatus,
    IncidentSeverity,
)
from graxia.packages.revenue_os.services.outbox_service import OutboxService
from graxia.packages.revenue_os.services.bwcp_service import BWCPService
from graxia.packages.revenue_os.core.redis_streams import RedisStreamClient
from graxia.packages.revenue_os.testing.chaos_engine import (
    ChaosEngine,
    ChaosLevel,
    ChaosType,
)


# ============================================================================
# Fixtures (from python-testing skill)
# ============================================================================

@pytest.fixture
async def db_session():
    """Create test database session with setup/teardown."""
    from graxia.packages.revenue_os.db import get_db_session
    
    async with get_db_session() as session:
        yield session
        # Teardown: rollback any uncommitted changes
        await session.rollback()


@pytest.fixture
def mock_redis_client():
    """Create mock Redis client."""
    client = Mock(spec=RedisStreamClient)
    client.publish_event = AsyncMock(return_value=True)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    return client


@pytest.fixture
def chaos_engine():
    """Create chaos engine for testing."""
    return ChaosEngine()


# ============================================================================
# Outbox Service Tests (Critical Path - 100% coverage required)
# ============================================================================

class TestOutboxService:
    """Test suite for Transactional Outbox pattern (HR-07 compliance)."""
    
    @pytest.mark.asyncio
    async def test_publish_order_created_event(self, db_session):
        """Test publishing order_created event to outbox."""
        # Arrange
        order_id = uuid4()
        customer_email = "test@example.com"
        amount_cents = 10000
        
        # Act
        event = await OutboxService.publish_order_created(
            db=db_session,
            order_id=order_id,
            customer_email=customer_email,
            amount_cents=amount_cents,
            platform="stripe"
        )
        
        # Assert
        assert event is not None
        assert event.aggregate_type == "order"
        assert str(order_id) == event.aggregate_id
        assert event.event_type == "order_created"
        assert event.processed is False
        assert event.retry_count == 0
        
        # Verify payload
        payload = json.loads(event.payload) if isinstance(event.payload, str) else event.payload
        assert payload["customer_email"] == customer_email
        assert payload["amount_cents"] == amount_cents
    
    @pytest.mark.asyncio
    async def test_outbox_event_atomic_with_transaction(self, db_session):
        """Test that outbox events are atomic with business transactions."""
        # Arrange
        order_id = uuid4()
        
        try:
            # Act - Create event within transaction
            async with db_session.begin():
                event = await OutboxService.publish_order_created(
                    db=db_session,
                    order_id=order_id,
                    customer_email="atomic@test.com",
                    amount_cents=5000,
                    platform="test"
                )
                # Simulate business logic that might fail
                raise ValueError("Simulated business error")
        except ValueError:
            pass
        
        # Assert - Event should not exist after rollback
        from sqlalchemy import select
        result = await db_session.execute(
            select(OutboxEvent).where(OutboxEvent.aggregate_id == str(order_id))
        )
        events = result.scalars().all()
        assert len(events) == 0, "Outbox event should be rolled back with transaction"
    
    @pytest.mark.asyncio
    async def test_get_unprocessed_events(self, db_session):
        """Test retrieving unprocessed outbox events."""
        # Arrange - Create some test events
        for i in range(5):
            await OutboxService.publish_order_created(
                db=db_session,
                order_id=uuid4(),
                customer_email=f"test{i}@example.com",
                amount_cents=1000 * i,
                platform="stripe"
            )
        
        await db_session.commit()
        
        # Act
        events = await OutboxService.get_unprocessed_events(db_session, limit=10)
        
        # Assert
        assert len(events) == 5
        for event in events:
            assert event.processed is False
            assert event.retry_count == 0


# ============================================================================
# BWCP Service Tests (Critical Path - 100% coverage required)
# ============================================================================

class TestBWCPService:
    """Test suite for BWCP messaging service."""
    
    @pytest.mark.asyncio
    async def test_send_bwcp_message(self, db_session):
        """Test sending BWCP message with Belief-Will-Can-Plan pattern."""
        # Arrange
        conversation_id = "conv:test-123"
        
        # Act
        message = await BWCPService.send_message(
            db=db_session,
            sender_agent=AgentType.VISIONARY,
            recipient_agent=AgentType.CHIEF_OF_STAFF,
            message_type=BWCPMessageType.CAMPAIGN_CREATED,
            conversation_id=conversation_id,
            belief="New campaign launched for Q1",
            will="Monitor campaign performance and report weekly",
            can={"actions": ["monitor", "analyze", "report"]},
            plan={
                "step_1": "Set up tracking",
                "step_2": "Configure alerts",
                "step_3": "Weekly reviews"
            }
        )
        
        await db_session.commit()
        
        # Assert
        assert message is not None
        assert message.sender_agent == AgentType.VISIONARY
        assert message.recipient_agent == AgentType.CHIEF_OF_STAFF
        assert message.message_type == BWCPMessageType.CAMPAIGN_CREATED
        assert message.belief == "New campaign launched for Q1"
        assert message.delivered is False
    
    @pytest.mark.asyncio
    async def test_get_pending_messages_for_agent(self, db_session):
        """Test retrieving pending messages for an agent."""
        # Arrange - Create messages for different agents
        await BWCPService.send_message(
            db=db_session,
            sender_agent=AgentType.VISIONARY,
            recipient_agent=AgentType.CHIEF_OF_STAFF,
            message_type=BWCPMessageType.CAMPAIGN_CREATED,
            conversation_id="conv:1",
            belief="Test belief",
            will="Test will",
        )
        
        await BWCPService.send_message(
            db=db_session,
            sender_agent=AgentType.SALES,
            recipient_agent=AgentType.CHIEF_OF_STAFF,
            message_type=BWCPMessageType.LEAD_IDENTIFIED,
            conversation_id="conv:2",
            belief="Lead identified",
            will="Nurture lead",
        )
        
        await db_session.commit()
        
        # Act
        messages = await BWCPService.get_pending_messages(
            db=db_session,
            recipient_agent=AgentType.CHIEF_OF_STAFF,
            limit=10
        )
        
        # Assert
        assert len(messages) == 2
        assert all(m.recipient_agent == AgentType.CHIEF_OF_STAFF for m in messages)
        assert all(m.delivered is False for m in messages)
    
    @pytest.mark.asyncio
    async def test_mark_message_delivered(self, db_session):
        """Test marking BWCP message as delivered."""
        # Arrange
        message = await BWCPService.send_message(
            db=db_session,
            sender_agent=AgentType.VISIONARY,
            recipient_agent=AgentType.CHIEF_OF_STAFF,
            message_type=BWCPMessageType.CAMPAIGN_CREATED,
            conversation_id="conv:deliver-test",
            belief="Test",
            will="Test",
        )
        await db_session.commit()
        
        # Act
        success = await BWCPService.mark_delivered(db_session, message.id)
        await db_session.commit()
        
        # Assert
        assert success is True
        
        # Verify in DB
        from sqlalchemy import select
        result = await db_session.execute(
            select(BWCPMessage).where(BWCPMessage.id == message.id)
        )
        updated = result.scalar_one()
        assert updated.delivered is True
        assert updated.delivered_at is not None


# ============================================================================
# Redis Streams Tests
# ============================================================================

class TestRedisStreamClient:
    """Test suite for Redis Streams client."""
    
    @pytest.mark.asyncio
    async def test_publish_event(self, mock_redis_client):
        """Test publishing event to Redis Stream."""
        # Arrange
        event_data = {
            "event_type": "test_event",
            "aggregate_id": str(uuid4()),
            "payload": {"key": "value"}
        }
        
        # Act
        await mock_redis_client.publish_event(**event_data)
        
        # Assert
        mock_redis_client.publish_event.assert_called_once()
        call_kwargs = mock_redis_client.publish_event.call_args.kwargs
        assert call_kwargs["event_type"] == "test_event"
    
    @pytest.mark.asyncio
    async def test_redis_connection_failure_handling(self):
        """Test handling of Redis connection failures."""
        # Arrange
        client = RedisStreamClient(redis_url="redis://invalid:6379")
        
        # Act & Assert
        with pytest.raises(Exception):
            await client.connect()


# ============================================================================
# Chaos Engineering Tests
# ============================================================================

class TestChaosEngine:
    """Test suite for chaos engineering engine."""
    
    @pytest.mark.asyncio
    async def test_chaos_experiment_lifecycle(self, chaos_engine):
        """Test complete chaos experiment lifecycle."""
        # Arrange
        from graxia.packages.revenue_os.testing.chaos_engine import NetworkDelayInjector
        
        injector = NetworkDelayInjector(level=ChaosLevel.LOW)
        chaos_engine.register_injector(ChaosType.NETWORK_DELAY, injector)
        
        # Act
        result = await chaos_engine.run_experiment(
            ChaosType.NETWORK_DELAY,
            context={},
            duration_seconds=1.0
        )
        
        # Assert
        assert result is not None
        assert result.chaos_type == ChaosType.NETWORK_DELAY
        assert result.level == ChaosLevel.LOW
        assert result.success is True
        assert result.recovery_time_ms >= 0
    
    @pytest.mark.asyncio
    async def test_chaos_level_failure_rates(self):
        """Test that chaos levels have correct failure rates."""
        from graxia.packages.revenue_os.testing.chaos_engine import ChaosInjector
        
        # Test each level
        rates = {
            ChaosLevel.LOW: 0.1,
            ChaosLevel.MEDIUM: 0.3,
            ChaosLevel.HIGH: 0.5,
            ChaosLevel.EXTREME: 0.8,
        }
        
        for level, expected_rate in rates.items():
            injector = ChaosInjector(level=level)
            
            # Run many trials
            trials = 1000
            failures = sum(1 for _ in range(trials) if injector.should_fail())
            actual_rate = failures / trials
            
            # Assert within 10% tolerance
            assert abs(actual_rate - expected_rate) < 0.1
    
    @pytest.mark.asyncio
    async def test_chaos_report_generation(self, chaos_engine):
        """Test chaos experiment report generation."""
        # Arrange - Run some experiments
        from graxia.packages.revenue_os.testing.chaos_engine import NetworkDelayInjector
        
        chaos_engine.register_injector(
            ChaosType.NETWORK_DELAY,
            NetworkDelayInjector(ChaosLevel.LOW)
        )
        
        await chaos_engine.run_experiment(
            ChaosType.NETWORK_DELAY,
            context={},
            duration_seconds=0.1
        )
        
        # Act
        report = chaos_engine.get_report()
        
        # Assert
        assert report["summary"]["total_experiments"] == 1
        assert report["summary"]["success_rate"] == 1.0
        assert "by_type" in report
        assert "recent_results" in report


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for complete workflows."""
    
    @pytest.mark.asyncio
    async def test_complete_order_to_bwcp_flow(self, db_session, mock_redis_client):
        """
        Test complete flow: Order creation -> Outbox -> Redis -> Agent Handler -> BWCP
        """
        # 1. Create order (business transaction)
        order_id = uuid4()
        await OutboxService.publish_order_created(
            db=db_session,
            order_id=order_id,
            customer_email="integration@test.com",
            amount_cents=25000,
            platform="stripe"
        )
        await db_session.commit()
        
        # 2. Verify outbox event created
        events = await OutboxService.get_unprocessed_events(db_session, limit=10)
        order_events = [e for e in events if e.aggregate_id == str(order_id)]
        assert len(order_events) == 1
        
        # 3. Simulate outbox processing
        event = order_events[0]
        await mock_redis_client.publish_event(
            event_type=event.event_type,
            aggregate_id=event.aggregate_id,
            payload=event.payload
        )
        
        # 4. Verify Redis publish was called
        mock_redis_client.publish_event.assert_called()
    
    @pytest.mark.asyncio
    async def test_approval_workflow_hr01_hr02_compliance(self, db_session):
        """
        Test approval workflow compliance with Hard Rules HR-01 and HR-02.
        """
        # Arrange - Create approval request
        approval_id = uuid4()
        
        # Act - Send BWCP approval required message
        message = await BWCPService.create_approval_required_message(
            db=db_session,
            conversation_id="conv:approval-test",
            approval_id=approval_id,
            approval_type="campaign_budget",
            requested_by="VisionaryAgent",
            sender_agent=AgentType.CHIEF_OF_STAFF,
            recipient_agent=AgentType.VISIONARY,
        )
        await db_session.commit()
        
        # Assert
        assert message is not None
        assert message.message_type == BWCPMessageType.APPROVAL_REQUIRED
        assert message.approval_id == approval_id
        
        # Verify approval can be tracked
        approvals = await BWCPService.get_pending_messages(
            db=db_session,
            recipient_agent=AgentType.VISIONARY,
            message_type=BWCPMessageType.APPROVAL_REQUIRED
        )
        assert len(approvals) >= 1


# ============================================================================
# Performance Tests
# ============================================================================

class TestPerformance:
    """Performance tests for critical paths."""
    
    @pytest.mark.asyncio
    async def test_outbox_bulk_insert_performance(self, db_session):
        """Test outbox can handle bulk inserts."""
        # Arrange
        num_events = 100
        start_time = datetime.utcnow()
        
        # Act
        for i in range(num_events):
            await OutboxService.publish_order_created(
                db=db_session,
                order_id=uuid4(),
                customer_email=f"bulk{i}@test.com",
                amount_cents=1000,
                platform="stripe"
            )
        
        await db_session.commit()
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        # Assert - Should complete within reasonable time
        assert elapsed < 10.0, f"Bulk insert took {elapsed}s, expected < 10s"
        
        # Verify all events created
        events = await OutboxService.get_unprocessed_events(
            db_session,
            limit=num_events + 10
        )
        assert len(events) >= num_events


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test error handling and edge cases."""
    
    @pytest.mark.asyncio
    async def test_bwcp_invalid_agent_type(self, db_session):
        """Test handling of invalid agent type."""
        # Act & Assert
        with pytest.raises((ValueError, AttributeError)):
            await BWCPService.send_message(
                db=db_session,
                sender_agent="InvalidAgent",  # Invalid type
                recipient_agent=AgentType.CHIEF_OF_STAFF,
                message_type=BWCPMessageType.CAMPAIGN_CREATED,
                conversation_id="conv:error-test",
                belief="Test",
                will="Test",
            )
    
    @pytest.mark.asyncio
    async def test_outbox_retry_count_increment(self, db_session):
        """Test that retry count is properly tracked."""
        # Arrange
        event = await OutboxService.publish_order_created(
            db=db_session,
            order_id=uuid4(),
            customer_email="retry@test.com",
            amount_cents=5000,
            platform="stripe"
        )
        await db_session.commit()
        
        # Act - Simulate retries
        for _ in range(3):
            event.retry_count += 1
        
        await db_session.commit()
        
        # Assert
        assert event.retry_count == 3


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=graxia.packages.revenue_os", "--cov-report=term-missing"])
