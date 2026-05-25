# Graxia OS — Baseline Implementation Inventory

Generated: 2026-05-25
Branch: staging
Alembic head: 1e9db9a3b0ba

---

## 1. Repository Structure

```
/graxia os/
├── backend/           # FastAPI async backend
│   ├── app/
│   │   ├── api/       # REST route modules
│   │   ├── models/    # SQLAlchemy models
│   │   ├── schemas/   # Pydantic schemas
│   │   ├── core/      # Auth, LLM, event bus, security
│   │   ├── services/  # Business logic
│   │   ├── agents/    # AI agents
│   │   ├── tasks/     # Celery tasks
│   │   └── middleware/
│   ├── alembic/       # Database migrations
│   └── tests/         # Canonical test suite
├── frontend/          # React 18/TS/Vite SPA
├── config/            # Docker, PM2, Redis configs
├── scripts/           # Operational/deployment scripts
│   ├── ops/           # Production ops scripts
│   └── tests/         # Test helper scripts
├── docs/              # Runbooks, guides, reports
├── identity/          # Operator profile, positioning
└── graxia/            # Legacy graxia module
```

## 2. Existing Models

| Model | File | Status |
|-------|------|--------|
| User | `backend/app/models/user.py` | ✅ With TenantMixin |
| Organization | `backend/app/models/organization.py` | ✅ |
| Contact | `backend/app/models/contact.py` | ✅ With TenantMixin |
| Opportunity | `backend/app/models/opportunity.py` | ✅ With TenantMixin |
| Submission | `backend/app/models/submission.py` | ✅ With TenantMixin |
| ContentDraft | `backend/app/models/content_draft.py` | ✅ |
| ApprovalRequest | `backend/app/models/approval_request.py` | ✅ |
| **DigitalProduct** | `backend/app/models/funnel.py` | **✅ NEW** |
| **DeliveryAsset** | `backend/app/models/funnel.py` | **✅ NEW** |
| **FunnelCheckoutSession** | `backend/app/models/funnel.py` | **✅ NEW** |
| **FunnelOrder** | `backend/app/models/funnel.py` | **✅ NEW** |
| **FunnelOrderItem** | `backend/app/models/funnel.py` | **✅ NEW** |
| **DeliveryAccess** | `backend/app/models/funnel.py` | **✅ NEW** |
| **ConversionEvent** | `backend/app/models/funnel.py` | **✅ NEW** |

### Missing Models (per V5 spec)

| Missing Model | Needed For |
|---------------|-----------|
| DeliveryEmailEvent | Track sent/failed delivery emails |
| LeadMagnet | Digital lead magnet entities |
| LeadCapture | Captured leads from magnets |
| FunnelRecommendation | AI recommendations on funnel |
| MCPToolAuditLog | Audit every MCP tool call |
| ContextPack | Token-efficient context packs |
| AgentWorkflowRun | Agent workflow executions |
| AgentWorkflowStep | Individual workflow steps |
| GoogleWorkspaceMockAction | Mock workspace provider actions |

## 3. Existing API Routes

| Router | Prefix | Status |
|--------|--------|--------|
| auth | `/api/v1/auth` | ✅ |
| system | `/api/v1/system` | ✅ |
| approvals | `/api/v1/approvals` | ✅ |
| contacts | `/api/v1/contacts` | ✅ |
| opportunities | `/api/v1/opportunities` | ✅ |
| drafts | `/api/v1/drafts` | ✅ |
| admin | `/api/v1/admin` | ✅ |
| agents | `/api/v1/agents` | ✅ |
| billing | `/api/v1/billing` | ✅ |
| calendar | `/api/v1/calendar` | ✅ |
| cognitive | `/api/v1/cognitive` | ✅ |
| commands | `/api/v1/commands` | ✅ |
| costs | `/api/v1/costs` | ✅ |
| events | `/api/v1/events` | ✅ |
| inbox | `/api/v1/inbox` | ✅ |
| integrations | `/api/v1/integrations` | ✅ |
| jobs | `/api/v1/jobs` | ✅ |
| metrics | `/api/v1/metrics` | ✅ |
| obsidian | `/api/v1/obsidian` | ✅ |
| onboarding | `/api/v1/onboarding` | ✅ |
| outreach | `/api/v1/outreach` | ✅ |
| runs | `/api/v1/runs` | ✅ |
| scrapers | `/api/v1/scrapers` | ✅ |
| skills | `/api/v1/skills` | ✅ |
| content_engine | `/api/v1/content` | ✅ |
| orchestration | `/api/v1/orchestration` | ✅ |

### Missing API Routes

| Missing Route | Needed For |
|---------------|-----------|
| funnel delivery | Delivery access admin/public APIs |
| funnel analytics | Analytics summary endpoints |
| funnel lead magnets | Lead magnet management |
| funnel recommendations | Recommendation APIs |
| MCP HTTP | Agent control plane HTTP transport |

## 4. Existing Funnel Schemas

| Schema | Status |
|--------|--------|
| DigitalProductBase, Create, Read, Update | ✅ |
| DeliveryAssetBase, Create, Read | ✅ |
| FunnelCheckoutSessionRead | ✅ |
| FunnelOrderItemRead, FunnelOrderRead | ✅ |
| DeliveryAccessRead | ✅ |
| ConversionEventCreate, Read | ✅ |

## 5. Existing Tests

| Test File | Status |
|-----------|--------|
| `test_funnel_foundation.py` | ✅ 10 tests pass |
| `test_approval_flow_contracts.py` | ✅ |
| `test_control_plane_contracts.py` | ✅ |
| `test_api_surface_contracts.py` | ✅ |
| `test_tenancy.py` | ✅ |
| `test_soft_delete_contracts.py` | ✅ |
| Various other contract tests | ✅ |

## 6. Migration Status

- Alembic head: `1e9db9a3b0ba` (merge)
- 30 migration files total
- Latest additions: `019_content_engine.py`, `020_add_funnel_foundation.py`, merge commits

## 7. Missing Modules Summary

See companion documents for detailed implementation plans:
- `docs/FUNNEL_E2E_RUNBOOK.md`
- `docs/MCP_CONTROL_PLANE.md`
- `docs/TOKEN_EFFICIENT_CONTEXT_PROTOCOL.md`
- `docs/LOCAL_AGENT_SETUP.md`
