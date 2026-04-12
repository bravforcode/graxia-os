# Personal Sovereign Enterprise OS v3 — Complete Design Spec

**Date:** 2026-04-08  
**Author:** Claude Code + Phirawit Jitnarong (P)  
**Status:** Design Approved  
**Timeline:** 8-12 weeks total (Phase 1: 4-6 weeks, Phase 2: 4-6 weeks)

---

## EXECUTIVE SUMMARY

Transform **Personal Sovereign OS** from a functional prototype (85% built) into a production-grade, enterprise-class autonomous opportunity management system. This spec covers two sequential phases:

1. **Phase 1: Backend Stabilization & LLM Integration (4-6 weeks)**
   - Replace Claude/Gemini with Gemma 4 + Qwen 3.6 (local + cloud fallback)
   - Enterprise-grade infrastructure (Ollama, observability, security)
   - Complete all agent implementations + testing
   - Deploy on NVIDIA RTX 2050 locally with cloud fallback

2. **Phase 2: Frontend Redesign (4-6 weeks)**
   - Rebuild React SPA with A+C design (Claude Code Dark + Mission Control HUD)
   - Real-time WebSocket for agent activity streams
   - Component library + Storybook documentation
   - Performance optimized (Lighthouse 90+)

**Expected Outcome:** Enterprise-grade Personal OS that autonomously discovers, scores, drafts, and manages opportunities with real-time visibility and human approval gates.

---

## CONTEXT & REQUIREMENTS

### Current State
- **Backend:** FastAPI (162 files), 18 agents, 11 scrapers, 19 API routes, 27 models — 85% complete
- **Frontend:** React SPA (13 pages) with Tailwind CSS — functional but needs redesign
- **Infrastructure:** Docker Compose ready, PostgreSQL + Redis + Celery
- **LLM:** Currently uses OpenClaw (Claude) + Gemini → **switching to Gemma 4 + Qwen 3.6**
- **Deployment:** Running in Docker at localhost:8000, no API keys configured yet
- **User:** Phirawit Jitnarong (P), Bangkok, Computer Engineering student + founder, 25 hrs/week available

### Design Goals
1. **Fully Autonomous** — System manages everything without constant user input
2. **Enterprise-Grade** — Production-quality code, testing, monitoring, security
3. **Real-Time Visibility** — Agent activity streamed live to user
4. **Intelligent Fallback** — Local LLM primary, cloud API fallback, graceful degradation
5. **Zero Setup Friction** — Single command to bootstrap everything
6. **Developer Experience** — Clear documentation, easy to extend agents/scrapers

### Non-Goals
- Multi-tenancy (single-user system)
- Mobile-first design (desktop primary)
- GraphQL (REST APIs sufficient)
- Kubernetes (Docker Compose sufficient)

---

## PHASE 1: BACKEND STABILIZATION & ENTERPRISE HARDENING (4-6 weeks)

### 1. Infrastructure & Deployment

#### 1.1 Local Development Environment
**Setup Automation (`setup.sh`):**
- Auto-detect OS + Python 3.11+, Docker, Ollama
- Clone `.env` from `.env.example`
- Create PostgreSQL + Redis instances
- Run Alembic migrations
- Download Ollama models (gemma:4b, qwen:3.6)
- Verify all services healthy
- Optional: Seed test data

**Docker Compose Enhancements:**
```yaml
services:
  postgres:
    image: postgres:15-alpine
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "$POSTGRES_USER"]
      interval: 10s
      timeout: 5s
      retries: 5
  
  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
  
  backend:
    build: ./backend
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      - LLM_PROVIDER=ollama  # or together_ai fallback
      - OLLAMA_BASE_URL=http://ollama:11434
    volumes:
      - ./identity:/app/identity:ro  # Read-only
  
  ollama:
    image: ollama/ollama:latest
    runtime: nvidia  # GPU passthrough
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
    volumes:
      - ollama_data:/root/.ollama
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
  
  celery:
    build: ./backend
    command: celery -A app.tasks.celery_app worker -l info
    depends_on:
      - redis
      - backend

volumes:
  ollama_data:
```

**Environment Configuration (`backend/config.py` refactor):**
```python
# Split into: config/base.py, config/dev.py, config/prod.py
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = Field(default="postgresql+asyncpg://...")
    
    # LLM Providers
    LLM_PROVIDER: str = Field(default="ollama")  # or "together_ai"
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434")
    TOGETHER_API_KEY: str | None = Field(default=None)
    TOGETHER_BASE_URL: str = Field(default="https://api.together.xyz")
    
    # Model Selection
    OLLAMA_MODEL: str = Field(default="gemma:4b")
    OLLAMA_MODEL_FALLBACK: str = Field(default="qwen:3.6")
    CLOUD_MODEL: str = Field(default="meta-llama/Llama-2-70b-chat-hf")
    
    # Cost Controls
    MAX_DAILY_COST_USD: float = Field(default=10.0)
    MAX_MONTHLY_COST_USD: float = Field(default=200.0)
    
    @field_validator('LLM_PROVIDER')
    def validate_llm_provider(cls, v):
        if v not in ['ollama', 'together_ai', 'huggingface']:
            raise ValueError('Invalid LLM provider')
        return v
    
    class Config:
        env_file = '.env'
        case_sensitive = True
```

#### 1.2 Ollama + Multi-LLM Integration

**Ollama Setup (Local Inference):**
```bash
# Install Ollama (macOS/Linux/Windows)
curl https://ollama.ai/install.sh | sh

# Pull models for RTX 2050
ollama pull gemma:4b          # 2.9GB, 4-bit quantized
ollama pull qwen:3.6          # 3.5GB quantized

# Run service
ollama serve --listen 0.0.0.0:11434
```

**LLM Client Rewrite (`backend/app/core/llm.py`):**
```python
from abc import ABC, abstractmethod
import httpx
import logging

class LLMProvider(ABC):
    """Base class for all LLM providers"""
    
    @abstractmethod
    async def complete(self, system: str, user: str) -> str | None:
        """Generate completion, return None if failed"""
        pass
    
    @abstractmethod
    async def complete_json(self, system: str, user: str) -> dict | None:
        """Generate JSON response"""
        pass
    
    @abstractmethod
    async def health(self) -> bool:
        """Health check"""
        pass

class OllamaProvider(LLMProvider):
    """Local inference via Ollama"""
    
    def __init__(self, base_url: str = "http://localhost:11434", 
                 model: str = "gemma:4b"):
        self.base_url = base_url
        self.model = model
        self.client = httpx.AsyncClient(timeout=300.0)
        self.logger = logging.getLogger(__name__)
    
    async def complete(self, system: str, user: str) -> str | None:
        try:
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": f"{system}\n\nUser: {user}",
                    "stream": False,
                    "temperature": 0.7,
                },
                timeout=300.0
            )
            result = response.json()
            return result.get("response", "").strip() or None
        except Exception as e:
            self.logger.error(f"Ollama error: {e}")
            return None
    
    async def health(self) -> bool:
        try:
            response = await self.client.get(
                f"{self.base_url}/api/tags",
                timeout=5.0
            )
            return response.status_code == 200
        except:
            return False

class TogetherAIProvider(LLMProvider):
    """Cloud fallback via Together.ai"""
    
    def __init__(self, api_key: str, model: str = "meta-llama/Llama-2-70b-chat-hf"):
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0
        )
    
    async def complete(self, system: str, user: str) -> str | None:
        try:
            response = await self.client.post(
                "https://api.together.xyz/inference",
                json={
                    "model": self.model,
                    "prompt": f"{system}\n\nUser: {user}",
                    "max_tokens": 1024,
                    "temperature": 0.7,
                }
            )
            result = response.json()
            return result.get("output", {}).get("choices", [{}])[0].get("text", "").strip() or None
        except Exception as e:
            self.logger.error(f"Together.ai error: {e}")
            return None
    
    async def health(self) -> bool:
        try:
            response = await self.client.get(
                "https://api.together.xyz/status"
            )
            return response.status_code == 200
        except:
            return False

class LLMRouter:
    """Smart routing: Local → Cloud → Degraded"""
    
    def __init__(self, ollama: OllamaProvider, together: TogetherAIProvider | None):
        self.ollama = ollama
        self.together = together
        self.cache = RedisCache()
        self.logger = logging.getLogger(__name__)
        self.degraded_mode = False
    
    async def complete(self, system: str, user: str, task: str = "general") -> str | None:
        # Check cache first
        cache_key = f"llm:{hashlib.sha256((system + user).encode()).hexdigest()}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        # Try Ollama (local, fast)
        if await self.ollama.health():
            result = await self.ollama.complete(system, user)
            if result:
                await self.cache.set(cache_key, result, ttl=86400)
                return result
        
        # Fallback to Together.ai (cloud)
        if self.together and await self.together.health():
            result = await self.together.complete(system, user)
            if result:
                await self.cache.set(cache_key, result, ttl=86400)
                return result
        
        # Degraded mode
        self.logger.warning("Both LLM providers down, entering degraded mode")
        self.degraded_mode = True
        return None
```

**Cost Tracking (`backend/app/core/cost_tracker.py` fixes):**
- Ollama: $0 cost (local)
- Together.ai: Track per 1M tokens ($0.002-0.01 depending on model)
- Daily/monthly budgets with enforcement
- Cost anomaly alerts

### 2. Database & Data Integrity

#### 2.1 Schema Audit & Optimization
- Review all 7 Alembic migrations
- Add missing indexes: `opportunities(user_id, status, created_at)`, `submissions(status, created_at)`
- Implement soft deletes on `opportunities`, `submissions`, `contacts`
- Add audit triggers for compliance

#### 2.2 Backup & Recovery
- Daily PostgreSQL backups (7-day retention)
- S3 storage + local fallback
- Monthly backup restore drill (documented)

### 3. Agents & LLM Integration

#### 3.1 Agent Implementation Status

| Agent | Status | Work Required |
|-------|--------|---------------|
| **scorer** | ✓ Complete | Test with Ollama, verify scoring consistency |
| **decision_engine** | ✓ Complete | Test decision thresholds (do_now/delay/skip) |
| **drafter** | ✓ Complete | Test proposal quality with Ollama |
| **briefer** | ✓ Complete | Test morning brief generation |
| **learning_engine** | 60% | Implement pattern analysis, weight learning |
| **playbook_capture** | 40% | Extract playbooks from wins |
| **failure_analysis** | 40% | Implement post-mortem analysis |
| **compound_engine** | 40% | Weekly metrics aggregation |
| **network_builder** | ✓ Complete | LinkedIn contact discovery |
| **job_hunter** | ✓ Complete | Job scraping (FastWork, LinkedIn, etc) |
| **email_manager** | ✓ Complete | Gmail integration + categorization |
| **personal_assistant** | ✓ Complete | Daily briefing + Telegram commands |

**Each agent requires:**
- Unit tests (mock LLM)
- Integration tests (real Ollama)
- Error handling + retry logic
- Audit logging

#### 3.2 Event Bus Enhancements
- Dead letter queue for failed events
- Event sourcing (all events stored in DB)
- Event replay capability for debugging
- Typed domain events

**Example Event Flow:**
```
opportunity.found 
  → [scorer] → opportunity.scored
    → [decision_engine] → opportunity.decided (do_now)
      → [drafter] + [briefer] (parallel)
        → draft.created
        → brief.generated
        → [telegram_bot] → notify user
      → [learning_engine] (background)
```

### 4. API Layer & Contracts

#### 4.1 Critical Endpoints (Full Test Coverage)
```
POST   /api/v1/opportunities/analyze    # Score an opportunity
GET    /api/v1/opportunities            # List with filters (status, score)
GET    /api/v1/opportunities/{id}       # Details + agent analysis
POST   /api/v1/drafts/{id}/approve      # User approves draft
GET    /api/v1/system/health            # System readiness
GET    /api/v1/system/status            # Runtime state
WS     /ws/agent-stream                 # Real-time events
```

#### 4.2 OpenAPI / Swagger
- FastAPI auto-generates `/docs` + `/redoc`
- Export OpenAPI 3.0 JSON for frontend code generation
- All response codes + error models documented

### 5. Security Hardening

#### 5.1 Authentication & Authorization
- JWT tokens: 1h access, 7d refresh
- Token revocation list (logout)
- Password requirements: 12+ chars, complexity
- Rate limiting: 10 login attempts/min per IP

#### 5.2 Input Validation & Sanitization
- Pydantic schemas enforce all inputs
- LLM prompt sanitization (SQL injection prevention)
- Data anonymization in logs (emails, phone numbers)
- CORS: Allow only `localhost:3000` (dev), your domain (prod)

#### 5.3 Secrets Management
- Development: `.env` file (Git ignored)
- Production: AWS Secrets Manager / HashiCorp Vault
- Secret rotation: Every 90 days

### 6. Observability & Monitoring

#### 6.1 Structured Logging
```json
{
  "timestamp": "2026-04-08T10:30:45Z",
  "level": "INFO",
  "service": "personal-os",
  "module": "scorer",
  "event": "opportunity_scored",
  "opportunity_id": "uuid",
  "score": 87,
  "duration_ms": 1234,
  "trace_id": "abc123"
}
```
- Use `structlog` for structured output
- Correlation IDs for request tracing
- Log rotation: Daily, 30-day retention

#### 6.2 Prometheus Metrics
- `llm_requests_total{provider, model}`
- `llm_latency_seconds{provider}`
- `llm_cost_usd{provider}`
- `api_requests_total{endpoint, status}`
- `agent_events_processed{agent, status}`

#### 6.3 Grafana Dashboards
1. System Health (uptime, CPU, memory, disk)
2. LLM Metrics (requests, latency, cost, provider)
3. API Performance (req/s, latency p50/p95/p99)
4. Agent Activity (events, processing time, errors)

#### 6.4 Alerting (PagerDuty / Slack)
- API error rate > 5% → Warning
- LLM latency p95 > 5s → Warning
- Daily cost > budget → Alert
- Service down > 5 min → Critical

### 7. Testing Strategy

#### 7.1 Unit Tests (70% coverage)
- Agent logic with mock LLM
- Scoring algorithms
- Decision logic
- Config loading

#### 7.2 Integration Tests (20%)
- Scorer → Decision Engine → Drafter flow
- LLM provider switching (Ollama → Together.ai)
- Database transactions
- Email processing

#### 7.3 End-to-End Tests (10%)
- Full workflow: opportunity → score → draft → brief
- User approval → submission tracking
- Real-time WebSocket events

#### 7.4 Performance Tests
- Baseline: 100 opportunities/min processing
- Latency: P50 < 1s, P99 < 5s
- Memory: < 1GB sustained
- Load test: 100 concurrent opportunities

#### 7.5 CI/CD Pipeline (GitHub Actions)
```yaml
jobs:
  lint:
    - pylint, black, flake8
  test:
    - pytest (unit + integration + e2e)
    - Coverage > 70% required
  security:
    - bandit (security scan)
    - safety (dependency audit)
  deploy:
    - Build Docker image
    - Deploy to staging
    - Smoke tests
```

### 8. Deployment & Operations

#### 8.1 Deployment Checklist
- [ ] All tests passing
- [ ] No security vulnerabilities
- [ ] Database migrations tested + reversible
- [ ] Environment variables documented
- [ ] Performance benchmarks met
- [ ] Rollback plan defined

#### 8.2 Blue-Green Deployment
- Zero downtime updates
- Canary: 10% → 50% → 100% traffic
- Automatic rollback if error rate > 5%

#### 8.3 Operational Runbooks
Document for:
- LLM provider failover
- Database recovery
- Cache clear
- Agent restart
- Troubleshooting

### 9. Phase 1 Success Criteria

✓ All 18 agents tested + working with Ollama + Together.ai fallback  
✓ All 19 API endpoints functional + documented  
✓ All tests passing (unit + integration + e2e)  
✓ No critical security vulnerabilities  
✓ Monitoring + alerting operational  
✓ Documentation complete  
✓ Performance: P99 latency < 5s  
✓ Cost tracking accurate per provider  
✓ Telegram notifications working  
✓ PostgreSQL + Redis + Ollama healthy  

---

## PHASE 2: FRONTEND REDESIGN — CLAUDE CODE DARK + MISSION CONTROL (4-6 weeks)

### 1. Design System

#### 1.1 A+C Hybrid Visual Language

**Color Palette (GitHub Dark + Neon):**
- Base: `#0d1117` (dark bg), `#161b22` (surfaces)
- Accents: 
  - Green `#3fb950` (active/success)
  - Blue `#58a6ff` (info)
  - Orange `#f0883e` (warning)
  - Red `#da3633` (error)
  - Cyan `#00d4ff` (HUD highlights)
  - Neon green `#00ff9d` (Mission Control)

**Typography:**
- Body: System font stack (SF Pro, Segoe UI, Roboto)
- Code: JetBrains Mono or Consolas
- Sizes: 12px (small), 14px (body), 16px (heading), 20px (h2), 28px (h1)

**Spacing:** 4px, 8px, 12px, 16px, 24px, 32px (multiples of 4)

**Transitions:** 150ms (fast), 300ms (medium), 500ms (slow)

#### 1.2 Component Library (Storybook)

**Base Components:**
- Button (primary, secondary, danger, loading)
- Input (text, email, select, multiselect, date)
- Card, Badge, Modal, Toast, Spinner, Tooltip, Tabs, Accordion
- DataTable (sortable, filterable, paginated)
- Chart (line, bar, pie using Recharts)

**Composite Components:**
- AuthCard, FormSection, Timeline, Breadcrumb, Avatar

**Storybook:**
- Document each component with props + variants
- Visual regression testing (Percy or Chromatic)
- Accessibility testing

### 2. Page Architecture & Design

#### 2.1 Layout System
```
┌─────────────────────────────────────┐
│  Header (Logo, Search, Notifications) 
├────────────┬──────────────────────┤
│ Sidebar    │ Main Content (80%)   │
│ (Claude    │ (HUD Grid)           │
│ Code       │                      │
│ style)     │                      │
└────────────┴──────────────────────┘
```

**Header:**
- Left: Logo + breadcrumb
- Center: Global search
- Right: Notifications, user menu, settings

**Sidebar:**
- Claude Code dark style (#0d1117)
- Icon-only when collapsed
- Navigation: Dashboard, Opportunities, Jobs, Contacts, Emails, Drafts, Metrics, Settings
- Active indicator (left border, accent color)

**Main Area:**
- Responsive grid for cards/panels
- Real-time updates via WebSocket
- HUD-style metrics + charts

#### 2.2 Critical Pages (A+C Design)

**1. Dashboard (Hero Page)**
```
Dashboard > Today

┌─────────────────────┐ ┌───────────────────┐
│ AGENT ACTIVITY      │ │ METRICS MATRIX    │
│ ▶ scorer: analyzing │ │ 12    87    3  28k│
│ ▶ decision: do_now  │ │ OPPS SCORE PEND $│
│ ▶ drafter: draft... │ │                   │
│ ▶ briefer: waiting  │ └───────────────────┘
└─────────────────────┘
Pipeline ฿28,400
[████████░░░░░░░░] 65%
```

**2. Opportunities Page**
- Grid view (cards): title, score, status, deadline, value
- Table view: sortable, filterable
- Detail panel (side drawer)

**3. Agent Activity Log (Terminal-style)**
```
08:47 > [SCORER] opportunity #42
        └─ DevPost Hackathon 2026
        └─ Score: 87/100

08:48 > [DECISION_ENGINE] decision: do_now
        └─ Reasoning: High score + good timing

08:49 > [DRAFTER] proposal draft created
        └─ Draft ID: draft_xyz123

08:50 > [BRIEFER] briefing generated
        └─ Message sent to Telegram
```

**4. Drafts & Approvals**
- Pending approvals (large cards)
- Agent recommendation
- Approve/Edit/Reject buttons
- History view (past drafts)

**5. Contacts & Network**
- Contact directory (search, filter)
- Relationship history
- Network graph (D3.js)

**6. Settings & Admin**
- Profile (identity, goals, skills)
- System settings (LLM providers, budgets)
- Data export/backup

### 3. Real-Time Integration (WebSocket)

#### 3.1 Server-Side WebSocket
```python
class WebSocketManager:
    async def broadcast(self, event: DomainEvent):
        for user_id, ws in self.active_connections:
            if user_id == event.user_id:
                await ws.send_json({
                    "type": event.type,
                    "data": event.to_dict(),
                    "timestamp": datetime.now().isoformat()
                })
```

#### 3.2 Client-Side (React Hook)
```typescript
const useAgentStream = () => {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  
  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/agent-stream');
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setEvents(prev => [data, ...prev].slice(0, 100));
    };
    return () => ws.close();
  }, []);
  
  return events;
};
```

**Events to Stream (Real-Time):**
- `opportunity.found` → Green notification
- `opportunity.scored` → Update score
- `opportunity.decided` (do_now) → Highlight
- `draft.created` → Show approval button
- `draft.approved` → Archive item
- `error.occurred` → Red alert

#### 3.3 Notification System
- Toast notifications (Sonner)
- Notification bell (header) with dropdown
- Notification history page

### 4. React Architecture

#### 4.1 Folder Structure
```
frontend/src/
├── pages/
│   ├── Dashboard.tsx
│   ├── Opportunities/
│   ├── Jobs/
│   ├── Contacts/
│   ├── Emails/
│   ├── Drafts/
│   ├── Metrics/
│   ├── Settings/
│   └── Auth/
├── components/
│   ├── Layout/ (Header, Sidebar, MainLayout)
│   ├── Common/ (Button, Card, Badge, Modal, Toast, etc)
│   ├── AgentStream/ (ActivityLog, StreamItem, Hook)
│   ├── Dashboard/ (MetricsMatrix, PipelineBar, TopOpportunities)
│   └── Charts/
├── hooks/
│   ├── useAuth.ts
│   ├── useAgentStream.ts
│   ├── useFetch.ts
│   └── useLocalStorage.ts
├── contexts/
│   ├── AuthContext.tsx
│   ├── ThemeContext.tsx
│   └── NotificationContext.tsx
├── types/
│   ├── agent.ts
│   ├── opportunity.ts
│   └── contact.ts
├── lib/
│   ├── api.ts (API client)
│   ├── utils.ts
│   ├── formatting.ts
│   └── constants.ts
├── styles/
│   ├── globals.css (Tailwind + dark mode)
│   ├── animations.css
│   └── theme.css
└── App.tsx
```

#### 4.2 State Management
- **Server State:** React Query (TanStack)
- **Client State:** Zustand or Jotai
- Avoid Redux (overkill)

#### 4.3 Performance
- Code splitting (React.lazy by route)
- Image optimization (WebP, srcset)
- Memoization (React.memo, useMemo)
- Virtual scrolling for long lists
- **Target:** Bundle < 500KB (gzipped), Lighthouse 90+

### 5. Styling & Theming

#### 5.1 Tailwind CSS + Dark Mode
```javascript
// tailwind.config.js
module.exports = {
  darkMode: 'class',
  theme: {
    colors: {
      'dark-bg': '#0d1117',
      'dark-surface': '#161b22',
      'accent-green': '#3fb950',
      'accent-blue': '#58a6ff',
      'accent-cyan': '#00d4ff',
    },
  },
};
```

#### 5.2 Animations
- Fade in: 200ms
- Slide: 300ms
- Bounce: Spring physics
- Loading spinner: 1s rotation
- Agent pulse: 0.5s opacity

### 6. Testing Strategy

#### 6.1 Component Tests (Vitest + React Testing Library)
- Unit tests: Rendering, props, events
- Coverage: 80%+

#### 6.2 Integration Tests (Cypress / Playwright)
- Full workflows: Login → Dashboard → Approve Draft
- WebSocket real-time updates

#### 6.3 E2E Tests
- Critical user journeys
- Cross-browser compatibility

### 7. Accessibility (WCAG 2.1 AA)

- Semantic HTML
- ARIA labels
- Keyboard navigation (Tab, Enter, Esc)
- Color contrast: 4.5:1
- Focus indicators visible
- Screen reader support

### 8. Deployment & Optimization

#### 8.1 Build & Bundling (Vite)
- Minify, tree-shake, code split
- Output: HTML (3KB) + JS chunks + CSS
- Hash filenames for cache busting

#### 8.2 CDN & Caching
- S3 / Vercel / GitHub Pages
- CloudFront CDN
- Cache: HTML (5min), JS/CSS (1 year)

#### 8.3 Performance Monitoring
- Sentry error tracking
- LogRocket session replay
- Web Vitals (Lighthouse, SpeedInsights)

### 9. Phase 2 Success Criteria

✓ Complete A+C design system implemented  
✓ All 13 pages redesigned  
✓ Storybook with 40+ components documented  
✓ WebSocket real-time working  
✓ Agent activity stream live  
✓ Responsive (desktop, tablet, mobile)  
✓ Dark mode toggle working  
✓ Accessibility: WCAG 2.1 AA  
✓ Component test coverage: 80%+  
✓ Lighthouse score: 90+ all metrics  
✓ Bundle: < 500KB gzipped  
✓ Performance: LCP < 2.5s, FID < 100ms  

---

## INTEGRATION & DEPLOYMENT

### End-to-End Flow
```
opportunity.found (scraper)
  ↓ [Event Bus]
scorer analyzes
  ↓ [WebSocket → Frontend updates in real-time]
decision_engine decides
  ↓
drafter creates proposal + briefer generates brief
  ↓ [Telegram notification + Frontend alert]
user approves via frontend or Telegram
  ↓
submission tracked + learning_engine learns
```

### Deployment Strategy
1. **Phase 1 → Staging:**
   - Backend API stable, all tests green
   - Deploy to staging, run smoke tests
   - Monitor for 1 week

2. **Phase 1 → Production:**
   - Blue-green deployment
   - Canary rollout: 10% → 50% → 100%

3. **Phase 2 → Staging:**
   - Frontend deployed separately
   - Integration tests with Phase 1 APIs
   - 1-week testing

4. **Phase 2 → Production:**
   - Same canary rollout
   - Rollback plan documented

---

## SUCCESS METRICS

### Phase 1 Metrics
- All agents responding to LLM with < 5s latency
- 0 critical security vulnerabilities
- 100% database migrations passing
- Ollama → Together.ai fallover working (tested)
- Cost tracking accurate to ±5%
- Uptime > 99.9% in staging

### Phase 2 Metrics
- All pages rendering in < 2.5s (LCP)
- Lighthouse 90+ all categories
- WebSocket latency < 200ms
- User approval flow < 10s end-to-end
- Mobile responsive (tested on iPad/iPhone)

### System Metrics (End-to-End)
- Opportunity discovery: 0.5-2 opportunities/day
- Average score quality: 85+
- User approval rate: > 80% for do_now items
- System uptime: > 99.5%
- Cost per opportunity: < $0.05 (Ollama) or < $0.02 (Together.ai)

---

## TIMELINE & RESOURCES

**Total Duration:** 8-12 weeks  
**Team:** 1 full-stack engineer (Claude Code) + 1 product owner (P)

**Phase 1:** 4-6 weeks
- Week 1-2: Infrastructure setup + LLM integration
- Week 2-3: Agent fixes + testing
- Week 3-4: Security hardening + observability
- Week 4-6: Testing + deployment

**Phase 2:** 4-6 weeks
- Week 1-2: Design system + component library
- Week 2-3: Page implementations + WebSocket
- Week 3-4: Testing + accessibility
- Week 4-6: Performance + deployment

---

## RISKS & MITIGATION

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Ollama performance on RTX 2050 | High | Test gemma:4b quantized, profile early |
| LLM quality (Gemma vs Claude) | Medium | Implement human feedback loop, adjust prompts |
| WebSocket scalability | Low | Test with 100+ concurrent connections |
| Frontend complexity | Medium | Use Storybook, component testing, code review |
| Data consistency | Medium | Transaction tests, backup restore drills |

---

## APPENDIX: File Changes Summary

### Phase 1 Files to Modify/Create
- `backend/app/core/llm.py` — Complete rewrite (Ollama + routing)
- `backend/app/core/cost_tracker.py` — Fixes for TODOs
- `backend/config.py` → Split into `backend/config/{base,dev,prod}.py`
- `backend/app/agents/*.py` — Tests + completeness verification
- `docker-compose.yml` — Add Ollama service + health checks
- `setup.sh` — New automation script
- `backend/requirements.txt` — Add structlog, prometheus-client

### Phase 2 Files to Create/Modify
- `frontend/src/**` — Redesign all pages with A+C style
- `frontend/src/components/` — New component library
- `frontend/.storybook/` — Storybook setup
- `frontend/vite.config.ts` — Performance optimizations
- `frontend/tailwind.config.js` — A+C color palette
- `frontend/src/hooks/useAgentStream.ts` — WebSocket hook

---

**Document Version:** 1.0  
**Last Updated:** 2026-04-08  
**Status:** Design Approved, Ready for Implementation
