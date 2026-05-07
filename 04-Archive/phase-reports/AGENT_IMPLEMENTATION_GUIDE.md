# Agent Implementation Guide — Personal Sovereign OS v3

**Complete reference for implementing/testing all 18 agents**

---

## AGENT ARCHITECTURE

### Base Class: `BaseAgent`

Location: `backend/app/agents/base.py`

```python
class BaseAgent:
    """All agents inherit from this."""
    
    def __init__(self):
        self.llm = LLMClient()              # Shared LLM instance
        self.bus = EventBus()               # Event bus (publish domain events)
        self.agent_context = identity.get_agent_context()  # User context
        
    async def log_audit(self, action: str, details: dict):
        """Write to audit_logs table for compliance."""
        pass
    
    async def run(self, *args, **kwargs):
        """Main execution method (subclasses implement)."""
        pass
```

### Event Flow Pattern

```
1. Agent receives input (via event bus or direct call)
2. Call LLM (with system prompt + user message)
3. Parse response (JSON, structured text)
4. Validate output
5. Publish domain event (agent.event_name)
6. Log audit trail
7. Return result
```

### Error Handling Pattern

Every agent must implement:
```python
try:
    result = await self.llm.complete(system, user)
    if not result:
        await self.bus.publish(AgentFailedEvent(...))
        return None
    # Parse + validate
    validated = self.validate(result)
    return validated
except Exception as e:
    logger.error(f"Agent error: {e}")
    await self.bus.publish(AgentErrorEvent(...))
    return None
```

---

## AGENTS IMPLEMENTATION STATUS & REQUIREMENTS

### TIER 1: TACTICAL AGENTS (Finding & Scoring Opportunities)

#### 1. **Competition Scout** (`backend/app/agents/competition_scout.py`)
**Status:** ✓ COMPLETE  
**Purpose:** Discover opportunities from scrapers (DevPost, FastWork, EventPop, etc)

**Implementation:**
```python
class CompetitionScout(BaseAgent):
    async def run(self):
        # 1. Fetch recent opportunities from DB (unscoredScore = null)
        # 2. For each:
        #    - Check duplication (SHA256 of URL + title)
        #    - Publish opportunity.found event
        # 3. Return count
```

**Tests Required:**
- [ ] Unit: Mock scraper data, verify opportunity.found events
- [ ] Integration: Real DB, verify opportunities stored
- [ ] Error: Handle scraper failures gracefully

**Success Criteria:**
- Discovers 5-10 opportunities per day
- Zero duplicate opportunities
- Latency < 5s (100 opportunities)

---

#### 2. **Scorer Agent** (`backend/app/agents/scorer.py`)
**Status:** ✓ COMPLETE  
**Purpose:** Analyze opportunity against user goals, assign 0-100 score

**Scoring Algorithm:**
```
Base Score (50):
  + User alignment (20): Does it match user's skills + interests?
  + Timeline fit (15): Reasonable deadline relative to other opportunities?
  + Value potential (10): Est. income/learning potential?
  + Competition level (5): How many similar opportunities?

Constraints:
  - Score < 30: SKIP (not worth time)
  - Score 30-70: WAIT (monitor, may improve timing)
  - Score 70+: DO_NOW (prioritize)
```

**Implementation:**
```python
class Scorer(BaseAgent):
    async def run(self, opportunity: Opportunity):
        system_prompt = f"""
You are an opportunity analyst. Rate this opportunity 0-100 based on:
- Alignment with user goals: {self.agent_context}
- Timeline feasibility
- Potential impact
- Competition level

Respond with JSON: {{"score": 0-100, "reasoning": "..."}}
        """
        
        user_msg = f"Opportunity: {opportunity.title}\n{opportunity.description}"
        result = await self.llm.complete_json(system_prompt, user_msg)
        
        if not result:
            return None
        
        score = int(result.get("score", 0))
        reasoning = result.get("reasoning", "")
        
        # Store score
        opportunity.score = score
        opportunity.score_reasoning = reasoning
        await db.commit()
        
        # Publish event
        await self.bus.publish(OpportunityScoredEvent(
            opportunity_id=opportunity.id,
            score=score,
            reasoning=reasoning
        ))
        
        return score
```

**Tests Required:**
- [ ] Unit: Mock opportunities, verify scoring logic
- [ ] Integration: Scorer → Decision Engine → Drafter flow
- [ ] Boundary: Score = 30, 70 (thresholds)
- [ ] Performance: P50 < 1s, P99 < 5s per opportunity

**Success Criteria:**
- Scores 100+ opportunities reliably
- Score consistency (same opportunity = same score)
- Reasoning aligned with scoring

---

#### 3. **Lead Hunter** (`backend/app/agents/lead_hunter.py`)
**Status:** ✓ COMPLETE  
**Purpose:** Discover contacts for networking + collaboration

**Implementation:**
```python
class LeadHunter(BaseAgent):
    async def run(self, opportunity: Opportunity):
        # 1. Extract relevant contacts/companies
        # 2. Search LinkedIn API / email database
        # 3. Publish lead.found events
        # 4. Store in contacts table
```

**Tests Required:**
- [ ] Unit: Mock opportunity data
- [ ] Integration: Real API calls (with API key)
- [ ] Error: Handle API rate limits, 403 errors

---

### TIER 2: EXECUTIVE AGENTS (Decision & Approval)

#### 4. **Decision Engine** (`backend/app/agents/decision_engine.py`)
**Status:** ✓ COMPLETE  
**Purpose:** Decide action on scored opportunity (do_now / delay / skip)

**Decision Logic:**
```
IF score >= 70 AND deadline > 3 days AND user_capacity < 0.8:
    action = "do_now"
    reasoning = "High score, sufficient time, user available"

ELIF score >= 70 AND deadline < 3 days:
    action = "do_now"
    reasoning = "High score but tight deadline, act now"

ELIF score >= 50 AND score < 70:
    action = "delay"
    reasoning = "Moderate score, monitor for timing improvement"

ELSE:
    action = "skip"
    reasoning = "Score too low or user at capacity"
```

**Implementation:**
```python
class DecisionEngine(BaseAgent):
    async def run(self, opportunity: Opportunity):
        if not opportunity.score:
            return None  # Scorer must run first
        
        # Get user capacity
        pending_count = await self.count_pending_opportunities()
        user_capacity = pending_count / 10  # max 10 concurrent
        
        # Get deadline
        days_to_deadline = (opportunity.deadline - datetime.now()).days
        
        # Decision logic (as above)
        if opportunity.score >= 70 and days_to_deadline > 3 and user_capacity < 0.8:
            action = "do_now"
        # ... other conditions ...
        
        # Publish event
        await self.bus.publish(OpportunityDecidedEvent(
            opportunity_id=opportunity.id,
            decision=action,
            reasoning=reason
        ))
        
        return {"decision": action, "reasoning": reason}
```

**Tests Required:**
- [ ] Unit: Test decision thresholds (score=30, 50, 70, 90)
- [ ] Unit: Test deadline edge cases (0 days, 3 days, 30 days)
- [ ] Unit: Test capacity logic
- [ ] Integration: Decision chain (scorer → decision → drafter)

**Success Criteria:**
- Decision matches scoring quality
- No "do_now" on low scores (< 50)
- Correct handling of capacity limits

---

#### 5. **Drafter Agent** (`backend/app/agents/drafter.py`)
**Status:** ✓ COMPLETE  
**Purpose:** Create proposal draft for user approval

**Prompt Template:**
```
Create a concise proposal for this opportunity:

Title: {opportunity.title}
Deadline: {opportunity.deadline}
Description: {opportunity.description}

Proposal should include:
1. Why this opportunity (2-3 sentences)
2. Your approach (3-5 bullet points)
3. Estimated timeline
4. Expected outcome

Respond with JSON: {{"proposal": "...", "confidence": 0.0-1.0}}
```

**Implementation:**
```python
class Drafter(BaseAgent):
    async def run(self, opportunity: Opportunity):
        system = """Create professional proposal draft."""
        user = f"Opportunity: {opportunity.title}..."
        
        result = await self.llm.complete_json(system, user)
        
        if not result:
            return None
        
        draft = ContentDraft(
            opportunity_id=opportunity.id,
            content=result.get("proposal"),
            status="pending_approval",
            created_by="drafter"
        )
        await db.add(draft)
        await db.commit()
        
        await self.bus.publish(DraftCreatedEvent(
            draft_id=draft.id,
            opportunity_id=opportunity.id
        ))
        
        return draft
```

**Tests Required:**
- [ ] Unit: Draft quality (includes key sections)
- [ ] Integration: Draft stored in DB correctly
- [ ] Error: Handle LLM failures gracefully

**Success Criteria:**
- Draft includes all required sections
- Professional tone
- Actionable next steps

---

#### 6. **Briefer Agent** (`backend/app/agents/briefer.py`)
**Status:** ✓ COMPLETE  
**Purpose:** Generate morning brief + send Telegram notification

**Brief Components:**
1. Summary of pending approvals
2. Top 3 opportunities (by score)
3. Cost summary
4. Recommendations

**Implementation:**
```python
class Briefer(BaseAgent):
    async def run(self):
        # 1. Get pending approvals
        pending = await db.query(ContentDraft).filter_by(status="pending_approval").all()
        
        # 2. Get top scoring opportunities
        top = await db.query(Opportunity).order_by(-Opportunity.score).limit(3).all()
        
        # 3. Generate brief
        system = "Create concise morning briefing."
        user = f"Pending: {len(pending)}\nTop opportunities: {top}"
        brief_text = await self.llm.complete(system, user)
        
        # 4. Send to Telegram
        await send_telegram_notification(brief_text)
        
        await self.bus.publish(BriefGeneratedEvent(...))
        
        return {"brief": brief_text, "sent": True}
```

**Tests Required:**
- [ ] Unit: Brief format validation
- [ ] Integration: Telegram send (mock)
- [ ] Error: Handle Telegram API errors

**Success Criteria:**
- Brief sent before 8am
- Includes all required sections
- User can approve/skip from Telegram

---

### TIER 3: SELF-IMPROVING AGENTS (Learning & Adaptation)

#### 7. **Learning Engine** (`backend/app/agents/learning_engine.py`)
**Status:** 60% COMPLETE  
**Purpose:** Extract patterns from wins/losses, adjust scoring weights

**Weight Adjustment Algorithm:**
```
When user submits opportunity:
  1. Check outcome (won/lost/abandoned)
  2. Compare actual score vs actual outcome
  3. Extract successful patterns (e.g., "deadline > 2 weeks → +10 to score")
  4. Update scoring weights in DB
  5. Version weights for rollback capability
```

**Implementation (TODO: Complete):**
```python
class LearningEngine(BaseAgent):
    async def run(self, submission: Submission):
        if not submission.outcome:
            return None
        
        # Extract success patterns
        patterns = await self.extract_patterns(submission)
        
        # Weight adjustments
        adjustments = {}
        for pattern_name, pattern_score in patterns.items():
            if submission.outcome == "won" and pattern_score > 0:
                adjustments[pattern_name] = +0.05
            elif submission.outcome == "lost" and pattern_score > 0:
                adjustments[pattern_name] = -0.05
        
        # Store new weights
        new_weights = await identity.apply_scoring_weights(adjustments)
        
        await self.bus.publish(WeightsAdjustedEvent(...))
        
        return {"adjustments": adjustments, "version": new_weights.version}
```

**Tests Required:**
- [ ] Unit: Weight adjustment logic
- [ ] Integration: Weights used in scorer
- [ ] Regression: Old weights work, new weights improve

**Success Criteria:**
- Weights improve scoring accuracy over time
- No infinite loops (weight oscillation)
- Rollback works correctly

---

#### 8. **Playbook Capture** (`backend/app/agents/playbook_capture.py`)
**Status:** 40% COMPLETE  
**Purpose:** Extract and store successful strategies

**Playbook Schema:**
```json
{
  "name": "FastWork Proposal Template",
  "pattern": "When [user_skill] + [opportunity_type] → do [action]",
  "success_rate": 0.85,
  "examples": [
    {"opportunity": "DevPost Hackathon", "outcome": "won"},
    {"opportunity": "FastWork Project", "outcome": "won"}
  ],
  "next_steps": ["Submit proposal", "Follow up after 3 days"]
}
```

**Implementation (TODO: Complete):**
```python
class PlaybookCapture(BaseAgent):
    async def run(self, submission: Submission):
        if submission.outcome != "won":
            return None
        
        # Extract pattern
        pattern = await self.extract_pattern(submission)
        
        # Create playbook
        playbook = Playbook(
            name=pattern.get("name"),
            pattern=pattern.get("pattern"),
            created_from_submission_id=submission.id
        )
        await db.add(playbook)
        await db.commit()
        
        await self.bus.publish(PlaybookCreatedEvent(...))
        
        return playbook
```

**Tests Required:**
- [ ] Unit: Pattern extraction logic
- [ ] Integration: Playbook stored + retrievable

---

#### 9. **Failure Analysis Agent** (`backend/app/agents/failure_analysis.py`)
**Status:** 40% COMPLETE  
**Purpose:** Post-mortem on lost opportunities

**Analysis Framework:**
```
Why did we lose this opportunity?

1. Execution (40%): Proposal quality, submission timing, follow-up
2. Fit (30%): Wrong skill match, unrealistic scope, timing
3. Competition (20%): Stronger competitors, better timing
4. Luck (10%): Random selection, market conditions

Generate actionable recommendations.
```

**Implementation (TODO: Complete):**
```python
class FailureAnalysis(BaseAgent):
    async def run(self, submission: Submission):
        if submission.outcome != "lost":
            return None
        
        system = """Analyze why this opportunity was lost.
        Categories: Execution, Fit, Competition, Luck
        Provide: Root cause analysis + recommendations
        """
        
        user = f"Opportunity: {submission.opportunity...}"
        
        analysis = await self.llm.complete(system, user)
        
        await self.bus.publish(FailureAnalyzedEvent(
            submission_id=submission.id,
            analysis=analysis
        ))
        
        return analysis
```

**Tests Required:**
- [ ] Unit: Analysis format validation
- [ ] Integration: Analysis stored + retrievable

---

#### 10. **Compound Engine** (`backend/app/agents/compound_engine.py`)
**Status:** 40% COMPLETE  
**Purpose:** Weekly metrics aggregation + strategy synthesis

**Weekly Report:**
```
Week Summary (Mon-Sun):
- Opportunities found: 12
- Opportunities approved: 5 (do_now)
- Submissions: 3
- Wins: 2
- Losses: 1
- Average score: 68

Recommendations:
1. Focus areas
2. Skill gaps
3. Best performing opportunity types
```

**Implementation (TODO: Complete):**
```python
class CompoundEngine(BaseAgent):
    async def run(self):
        # 1. Calculate weekly metrics
        metrics = await self.calculate_weekly_metrics()
        
        # 2. Generate insights
        system = "Synthesize weekly metrics into strategy."
        user = f"Metrics: {metrics}"
        strategy = await self.llm.complete(system, user)
        
        # 3. Store strategy
        await self.bus.publish(StrategyGeneratedEvent(...))
        
        return {"strategy": strategy, "metrics": metrics}
```

**Tests Required:**
- [ ] Unit: Metrics calculation accuracy
- [ ] Integration: Strategy generation + storage

---

### TIER 4: SPECIALIZED AGENTS (Integration Points)

#### 11. **Job Hunter** (`backend/app/agents/job_hunter.py`)
**Status:** ✓ COMPLETE  
**Purpose:** Discover job opportunities from multiple sources

**Sources:**
- FastWork API (`api.fastworkonline.com`)
- LinkedIn Jobs (Selenium scraper)
- Local job boards
- Email referrals

**Tests Required:**
- [ ] Unit: Job parsing logic
- [ ] Integration: API rate limiting, error handling
- [ ] E2E: Job discovery → Scoring → Decision

---

#### 12. **Network Builder** (`backend/app/agents/network_builder.py`)
**Status:** ✓ COMPLETE  
**Purpose:** LinkedIn contact discovery + relationship tracking

**Features:**
- Search relevant contacts by skill/industry
- Track relationship depth
- Identify warm introduction opportunities
- Suggest networking actions

**Tests Required:**
- [ ] Unit: Contact relevance scoring
- [ ] Integration: LinkedIn API calls

---

#### 13. **Email Manager** (`backend/app/agents/email_manager.py`)
**Status:** ✓ COMPLETE  
**Purpose:** Gmail integration + email categorization

**Features:**
- Fetch emails + categorize (opportunity, request, info, spam)
- Extract key information (deadline, budget, contact)
- Generate response drafts
- Track email history

**Implementation:**
```python
class EmailManager(BaseAgent):
    async def run(self):
        # 1. Fetch unread emails from Gmail API
        emails = await self.fetch_gmail_unread()
        
        # 2. Categorize each email
        for email in emails:
            category = await self.categorize(email)
            
            if category == "opportunity":
                await self.bus.publish(OpportunityFoundEvent(...))
        
        # 3. Generate summaries
        summary = await self.generate_email_summary(emails)
        
        return {"processed": len(emails), "summary": summary}
```

**Tests Required:**
- [ ] Unit: Email categorization
- [ ] Integration: Gmail API (with credentials)
- [ ] Error: Handle invalid email, quota exceeded

---

#### 14. **Personal Assistant** (`backend/app/agents/personal_assistant.py`)
**Status:** ✓ COMPLETE  
**Purpose:** Daily briefing + Telegram command handling

**Commands:**
- `/brief` — Send morning briefing
- `/approve {id}` — Approve draft
- `/reject {id}` — Reject draft
- `/cost` — Show today's cost
- `/status` — System status
- `/upcoming` — Next 5 opportunities

**Tests Required:**
- [ ] Unit: Command parsing
- [ ] Integration: Telegram Bot API

---

### TIER 5: ANALYSIS AGENTS (Advanced)

#### 15. **Competition Scout (Advanced)** — Future phase

#### 16-18. **Specialized Domain Agents** — Future phase

---

## TESTING TEMPLATE FOR EACH AGENT

### Unit Test Template

```python
# backend/tests/unit/agents/test_{agent_name}.py

import pytest
from unittest.mock import AsyncMock, patch
from app.agents.{agent_name} import {AgentClass}

class Test{AgentClass}:
    
    @pytest.fixture
    def agent(self):
        return {AgentClass}()
    
    @pytest.mark.asyncio
    async def test_run_success(self, agent):
        """Agent runs successfully."""
        with patch.object(agent.llm, 'complete', return_value="mock response"):
            result = await agent.run(mock_data)
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_run_llm_failure(self, agent):
        """Agent handles LLM failure gracefully."""
        with patch.object(agent.llm, 'complete', return_value=None):
            result = await agent.run(mock_data)
            assert result is None
    
    @pytest.mark.asyncio
    async def test_event_published(self, agent):
        """Agent publishes correct event."""
        with patch.object(agent.bus, 'publish') as mock_pub:
            await agent.run(mock_data)
            mock_pub.assert_called_once()
```

### Integration Test Template

```python
# backend/tests/integration/agents/test_{agent_name}_integration.py

@pytest.mark.asyncio
async def test_{agent_name}_end_to_end(db, ollama_service):
    """Agent works with real DB and Ollama."""
    agent = {AgentClass}()
    
    # Create test data
    test_data = await create_test_opportunity(db)
    
    # Run agent
    result = await agent.run(test_data)
    
    # Verify result
    assert result is not None
    
    # Verify DB state
    updated = await db.get(Opportunity, test_data.id)
    assert updated.score is not None
```

---

## AGENT TESTING CHECKLIST (Tasks 11-25)

For each agent, complete:

- [ ] **Unit Tests** (mock LLM)
  - [ ] Success case
  - [ ] LLM failure case
  - [ ] Validation failure case
  - [ ] Event published correctly

- [ ] **Integration Tests** (real Ollama + DB)
  - [ ] Run with real opportunity data
  - [ ] Result stored in DB
  - [ ] Event published + event consumed

- [ ] **Error Handling**
  - [ ] LLM timeout
  - [ ] Invalid JSON response
  - [ ] Database errors
  - [ ] API rate limits
  - [ ] Network errors

- [ ] **Performance**
  - [ ] Baseline latency (mock LLM)
  - [ ] Real Ollama latency
  - [ ] 100-opportunity batch processing
  - [ ] Memory usage

---

## PRIORITY ORDER FOR IMPLEMENTATION

**Week 1-2: Tactical Agents (High Impact)**
1. ✓ Scorer — Core ranking logic
2. ✓ Decision Engine — Action decisions
3. ✓ Drafter — Proposal generation
4. ✓ Briefer — Daily briefing

**Week 3: Specialized Agents**
5. ✓ Lead Hunter
6. ✓ Email Manager
7. ✓ Job Hunter
8. ✓ Network Builder

**Week 4: Self-Improving Agents**
9. Learning Engine (60% → 100%)
10. Playbook Capture (40% → 100%)
11. Failure Analysis (40% → 100%)
12. Compound Engine (40% → 100%)

**Week 5-6: Testing + Integration**
13. Event bus enhancements
14. Full pipeline testing
15. Performance optimization
16. Deployment preparation

---

## SUCCESS METRICS FOR AGENT TIER

### Tactical Agents (1-6)
- ✓ 100% test coverage
- ✓ All required methods implemented
- ✓ P50 latency < 1s, P99 < 5s
- ✓ Zero critical bugs in integration tests

### Self-Improving Agents (7-10)
- ✓ Learning engine improves scoring over time (5% gain/week)
- ✓ Playbook extracted from 80%+ of wins
- ✓ Failure analysis actionable
- ✓ Weekly strategy synthesis accurate

### Specialized Agents (11-14)
- ✓ All integrations working (Gmail, LinkedIn, job boards)
- ✓ Error handling graceful
- ✓ API rate limits respected
- ✓ Zero authentication issues

---

**Document Version:** 1.0  
**Last Updated:** 2026-04-09  
**Status:** Implementation ready
