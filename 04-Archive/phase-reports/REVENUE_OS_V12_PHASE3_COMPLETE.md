# Revenue OS v12 - PHASE 3 Complete

## Summary
PHASE 3 (Agent Choreography & BWCP Integration) has been completed. Event-driven agent communication via Redis Streams + BWCP messaging.

## What Was Built

### 1. Redis Streams Client (`core/redis_streams.py`)

**RedisStreamClient** - Full-featured Redis Streams implementation:

```python
# Producer (Celery process_outbox)
await client.publish_event(
    event_type="order_created",
    aggregate_type="order",
    aggregate_id=str(order_id),
    payload={...},
    correlation_id=corr_id,
)

# Consumer (Agent handlers)
await client.consume_events(
    consumer_name="visionary_agent",
    handler=handle_event,
    block_ms=5000,
    count=10,
)
```

**Features:**
- Producer with JSON serialization
- Consumer groups for load balancing
- Automatic message acknowledgement
- Pending message claiming (dead consumer recovery)
- Stream statistics and monitoring

**Stream Key:** `revenue_os:events`
**Consumer Group:** `revenue_os:agents`

### 2. BWCP Service (`services/bwcp_service.py`)

**BWCPService** - Belief-Will-Can-Plan message management:

| Field | Purpose |
|-------|---------|
| `belief` | Agent's understanding of situation |
| `will` | Agent's intended action |
| `can` | Agent's capabilities (JSON) |
| `plan` | Step-by-step execution plan (JSON) |

**API:**
- `send_message()` - Generic BWCP message
- `get_pending_messages()` - Inbox for agent
- `mark_delivered()` / `mark_read()` - Delivery tracking
- `get_conversation_history()` - Thread view
- Specialized methods for each message type

**ConversationManager:**
- `generate_conversation_id()` - Unique thread IDs
- `generate_correlation_id()` - Distributed tracing

### 3. Agent Event Handlers (`agents/event_handlers.py`)

Three agent handlers consuming from Redis Streams:

#### VisionaryAgentHandler
**Consumes:** `campaign_created`, `campaign_target_hit`, `campaign_paused`, `incident_created`

```python
# Campaign created → Notify ChiefOfStaff
campaign_created → BWCPMessage(
    sender=VisionaryAgent,
    recipient=ChiefOfStaffAgent,
    type=CAMPAIGN_CREATED,
    belief="New campaign launched...",
    will="Monitor and report...",
    can={"monitor", "analyze", "report"},
)
```

#### SalesAgentHandler
**Consumes:** `lead_identified`, `lead_converted`, `order_created`, `order_fulfilled`

```python
# Lead identified → Self-trackinglead_identified → BWCPMessage(
    sender=SalesAgent,
    recipient=SalesAgent,
    type=LEAD_IDENTIFIED,
    belief="High-value lead: email@...",
    will="Nurture through funnel",
    can={"email", "score", "track"},
)
```

#### ChiefOfStaffHandler
**Consumes:** `approval_required`, `approval_approved`, `approval_rejected`, `incident_created`, `order_refunded`

```python
# Critical incident → Immediate CEO escalation (HR-14)
incident_created (severity=critical) → BWCPMessage(
    sender=ChiefOfStaffAgent,
    recipient=VisionaryAgent,  # CEO proxy
    type=INCIDENT_CREATED,
    belief="CRITICAL INCIDENT...",
    will="Coordinate emergency response...",
    can={"escalate", "coordinate", "brief"},
)
```

### 4. Agent Consumers Celery Task (`celery/tasks/agent_consumers.py`)

**Runs every 30 seconds** to:
1. Connect to Redis
2. Run all 3 agent consumers concurrently
3. Claim pending messages from dead consumers
4. Route events to appropriate handlers

**Metrics tracked:**
- Events processed per agent
- Errors per agent
- Pending messages claimed
- Total throughput

### 5. Celery Integration Updates

**Beat Schedule:**
```python
"agent-consumers": {
    "task": "graxia.packages.revenue_os.celery.tasks.agent_consumers",
    "schedule": 30.0,  # Every 30 seconds
    "options": {"queue": "critical"},
}
```

## Architecture Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Order Service  │────▶│  OutboxEvent     │────▶│  Celery         │
│  (Transaction)  │     │  (Same TX)       │     │  process_outbox │
└─────────────────┘     └──────────────────┘     │  (every 60s)    │
                                                └────────┬────────┘
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │  Redis Streams  │
                                                │  revenue_os:    │
                                                │  events         │
                                                └────────┬────────┘
                                                         │
                              ┌──────────────────────────┼────────────────┐
                              │                          │                │
                              ▼                          ▼                ▼
                    ┌─────────────────┐         ┌─────────────────┐  ┌─────────────────┐
                    │ VisionaryAgent  │         │   SalesAgent    │  │ ChiefOfStaff    │
                    │   Consumer      │         │   Consumer      │  │   Consumer      │
                    │   (30s poll)    │         │   (30s poll)    │  │   (30s poll)    │
                    └────────┬────────┘         └────────┬────────┘  └────────┬────────┘
                             │                          │                  │
                             ▼                          ▼                  ▼
                    ┌─────────────────┐         ┌─────────────────┐  ┌─────────────────┐
                    │  BWCPMessage    │         │  BWCPMessage    │  │  BWCPMessage    │
                    │  (campaigns,   │         │  (leads, orders)│  │  (approvals,    │
                    │   incidents)    │         │                 │  │   incidents)    │
                    └─────────────────┘         └─────────────────┘  └─────────────────┘
```

## Hard Rules Compliance

| Rule | Implementation |
|------|----------------|
| **HR-01** | Campaign approval via BWCP `APPROVAL_REQUIRED` → ChiefOfStaff → CEO |
| **HR-02** | Email approval via same workflow |
| **HR-07** | Transactional outbox → Redis Streams → BWCP messages |
| **HR-10** | All financial mutations logged + routed through audit_service |
| **HR-14** | Critical incidents immediately escalated via BWCP to ChiefOfStaff |

## Agent Communication Patterns

### Pattern 1: Event → BWCP (Fire-and-Forget)
```
Redis Event → AgentHandler → BWCPMessage → Database
```

### Pattern 2: Event → BWCP → Escalation
```
Redis Event → AgentHandler → BWCPMessage (self)
                         → BWCPMessage (CEO) if critical
```

### Pattern 3: Conversation Threading
```
All messages share conversation_id for thread tracking
Correlation ID links related events across services
```

## Database Schema (BWCP)

```sql
CREATE TABLE bwcp_messages (
    id UUID PRIMARY KEY,
    conversation_id VARCHAR(255) NOT NULL,
    sender_agent agenttype NOT NULL,
    recipient_agent agenttype NOT NULL,
    message_type bwcpmessagetype NOT NULL,
    belief TEXT,
    will TEXT,
    can JSONB,
    plan JSONB,
    campaign_id UUID REFERENCES revenue_os_campaigns(id),
    lead_id UUID REFERENCES revenue_os_leads(id),
    approval_id UUID REFERENCES revenue_os_approvals(id),
    incident_id UUID REFERENCES revenue_os_incidents(id),
    delivered BOOLEAN DEFAULT FALSE,
    delivered_at TIMESTAMP WITH TIME ZONE,
    read_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## API for Agent Developers

```python
from graxia.packages.revenue_os.services import BWCPService
from graxia.packages.revenue_os.enums import AgentType, BWCPMessageType

# Send message
await BWCPService.send_message(
    db=db,
    sender_agent=AgentType.SALES,
    recipient_agent=AgentType.VISIONARY,
    message_type=BWCPMessageType.LEAD_CONVERTED,
    conversation_id="conv:abc123...",
    belief="Lead converted to customer!",
    will="Update metrics and request testimonial",
    can={"actions": ["update", "notify"]},
    plan={"step_1": "Update CRM"},
    lead_id=lead_uuid,
)

# Get inbox
messages = await BWCPService.get_pending_messages(
    db=db,
    recipient_agent=AgentType.CHIEF_OF_STAFF,
)

# Mark delivered
await BWCPService.mark_delivered(db, message_id)
```

## Testing Commands

```bash
# Check Redis Stream
redis-cli XLEN revenue_os:events
redis-cli XGROUP INFO revenue_os:events revenue_os:agents

# Check BWCP messages
psql $DATABASE_URL -c "
SELECT sender_agent, recipient_agent, message_type, delivered, created_at
FROM bwcp_messages
ORDER BY created_at DESC
LIMIT 10;
"

# Run agent consumers manually
cd backend
python -c "
from graxia.packages.revenue_os.celery.tasks.agent_consumers import agent_consumers
result = agent_consumers(None)
print(result)
"
```

## Next Steps (PHASE 4)

1. **Agent Response Logic**
   - Implement agent decision-making based on BWCP messages
   - Add LangGraph integration for agent workflows

2. **Approval Workflows**
   - CEO dashboard for approval requests
   - Email notifications for pending approvals

3. **Incident Response**
   - Automated incident escalation
   - Slack/Discord notifications

4. **Monitoring**
   - Grafana dashboard for event flow
   - Alert on consumer lag
   - Track BWCP message latency

## Files Created/Modified

| File | Action | Lines |
|------|--------|-------|
| `core/redis_streams.py` | Created | 292 |
| `services/bwcp_service.py` | Created | 361 |
| `agents/event_handlers.py` | Created | 527 |
| `celery/tasks/agent_consumers.py` | Created | 272 |
| `services/__init__.py` | Modified | +2 |
| `agents/__init__.py` | Modified | +10 |
| `celery/tasks/__init__.py` | Modified | +2 |
| `celery/celery_app.py` | Modified | +6 |

## Compliance Checklist
- [x] Redis Streams consumer groups for scalability
- [x] BWCP pattern implemented (Belief/Will/Can/Plan)
- [x] All 3 agent handlers (Visionary, Sales, ChiefOfStaff)
- [x] HR-14 escalation via BWCP
- [x] Event routing to multiple agents
- [x] Conversation threading with correlation IDs
- [x] Dead consumer message reclaiming
- [x] Celery integration (30s schedule)
- [x] Database persistence for audit trail
- [x] Distributed lock prevents concurrent execution
