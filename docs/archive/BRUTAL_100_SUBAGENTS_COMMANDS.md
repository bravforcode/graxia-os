# BRUTAL 100 Features — Subagent Commands

รวมคำสั่งสำหรับรัน Subagents ทั้งหมดใน BRUTAL 100 Features Project

## 🚀 Quick Start

```powershell
# รัน Core Skills Specialist (Features 4-10)
.\.claude\activate-core-skills.ps1

# รันทั้งหมดพร้อมกัน (ทุก Phase)
.\.claude\activate-all-subagents.ps1
```

---

## 📋 Subagent List

### Subagent 1: Core Skills Specialist
**File:** `.claude/agents/core-skills-specialist.md`

**Features:**
- ✅ Feature 1-3: Version Control, Forking, Merging (DONE)
- ⏳ Feature 4: Dependency Graph
- ⏳ Feature 5: Skill Templates
- ⏳ Feature 6: Validation System
- ⏳ Feature 7: Testing Framework
- ⏳ Feature 8: A/B Testing
- ⏳ Feature 9: Rollback System
- ⏳ Feature 10: Draft Mode

**Activate:**
```powershell
.\.claude\activate-core-skills.ps1
```

---

### Subagent 2: AI Engine Specialist
**File:** `.claude/agents/ai-engine-specialist.md`

**Features:**
- Feature 11: Auto-Skill Generation
- Feature 12: Smart Skill Chaining
- Feature 13: Skill Embeddings
- Feature 14: Conversational Interface
- Feature 15: Code Generation
- Feature 16: Skill Improvement AI
- Feature 17: Context-Aware Recommendations
- Feature 18: Natural Language Skill Search
- Feature 19: Skill Summarization
- Feature 20: Skill Translation
- Feature 21: Skill Documentation AI
- Feature 22: Skill Debugging AI
- Feature 23: Skill Performance AI
- Feature 24: Skill Security AI
- Feature 25: Skill Marketplace AI

**Activate:**
```powershell
# สร้างคำสั่งนี้ก่อน
.\.claude\activate-ai-engine.ps1
```

---

### Subagent 3: Analytics Specialist
**File:** `.claude/agents/analytics-specialist.md`

**Features:**
- Feature 41: Usage Dashboards
- Feature 42: ROI Calculator
- Feature 43: Skill Trend Analysis
- Feature 44: Agent Learning Analytics
- Feature 45: Performance Predictions
- Feature 46: Custom Reports
- Feature 47: Real-time Metrics
- Feature 48: Export Capabilities
- Feature 49: Alert System
- Feature 50: Data Retention
- Feature 51: Privacy Controls
- Feature 52: Audit Logging
- Feature 53: Cost Tracking
- Feature 54: Billing Integration
- Feature 55: Usage Quotas

**Activate:**
```powershell
.\.claude\activate-analytics.ps1
```

---

### Subagent 4: Integrations Specialist
**File:** `.claude/agents/integrations-specialist.md`

**Features:**
- Feature 71: IDE Integration (VS Code, JetBrains)
- Feature 72: GitHub Integration
- Feature 73: Slack Integration
- Feature 74: Jira Integration
- Feature 75: Notion Integration
- Feature 76: API Gateway
- Feature 77: SSO Integration
- Feature 78: Webhook System
- Feature 79: Zapier Integration
- Feature 80: Custom Connectors

**Activate:**
```powershell
.\.claude\activate-integrations.ps1
```

---

### Subagent 5: UX Specialist
**File:** `.claude/agents/ux-specialist.md`

**Features:**
- Feature 81: Visual Skill Builder
- Feature 82: Interactive Playground
- Feature 83: Tutorial System
- Feature 84: Skill Gallery
- Feature 85: Template Library
- Feature 86: Advanced Search
- Feature 87: Skill Collections
- Feature 88: Collaborative Editing
- Feature 89: Comments & Feedback
- Feature 90: Gamification

**Activate:**
```powershell
.\.claude\activate-ux.ps1
```

---

### Subagent 6: Advanced Features Specialist
**File:** `.claude/agents/advanced-features-specialist.md`

**Features:**
- Feature 91: Skill NFTs
- Feature 92: Monetization System
- Feature 93: Skill Licensing
- Feature 94: Audit Trail
- Feature 95: Compliance Controls
- Feature 96: Security Scanning
- Feature 97: Disaster Recovery
- Feature 98: Federation Protocol
- Feature 99: DAO Governance
- Feature 100: Blockchain Verification

**Activate:**
```powershell
.\.claude\activate-advanced.ps1
```

---

### Subagent 7: Testing & QA Specialist
**File:** `.claude/agents/testing-qa-specialist.md`

**Responsibilities:**
- Unit Tests (90%+ coverage)
- Integration Tests
- E2E Tests (Playwright)
- Performance Tests
- Security Tests
- Regression Tests
- Load Tests
- Chaos Engineering

**Activate:**
```powershell
.\.claude\activate-testing.ps1
```

---

## 🔧 Master Coordinator

**File:** `.claude/agents/brutal-master-coordinator.md`

**Responsibilities:**
- Orchestrate all subagents
- Quality review
- Integration management
- Error resolution
- Progress reporting

**Activate:**
```powershell
# รันทั้งหมดตามลำดับ
.\.claude\activate-master-coordinator.ps1 --all

# รันบาง Phase พร้อมกัน
.\.claude\activate-master-coordinator.ps1 --phases 1,2,3
```

---

## 📊 Current Progress

```
Phase 1: Core Skills (Features 1-10)
├── ✅ 1-3: Version Control, Forking, Merging
├── ⏳ 4-10: Dependency Graph → Draft Mode (Running)
└── Status: IN PROGRESS

Phase 2: AI Engine (Features 11-25)
└── Status: PENDING

Phase 3: Analytics (Features 41-55)
└── Status: PENDING

Phase 4: Integrations (Features 71-80)
└── Status: PENDING

Phase 5: UX Layer (Features 81-90)
└── Status: PENDING

Phase 6: Advanced (Features 91-100)
└── Status: PENDING

Phase 7: Testing & QA
└── Status: PENDING
```

---

## 🎯 Success Metrics

- **Code Coverage:** ≥ 90%
- **API Response Time:** < 100ms (p95)
- **Database Query Time:** < 50ms (p95)
- **Uptime:** 99.9%
- **Error Rate:** < 0.1%
- **Documentation Coverage:** 100%
- **Type Safety:** 100% strict

---

## 🚀 Run Commands Now

### Option 1: Run Core Skills (Features 4-10)
```powershell
cd "c:\Users\menum\graxia os"
.\.claude\activate-core-skills.ps1
```

### Option 2: Run All Subagents in Parallel
```powershell
cd "c:\Users\menum\graxia os"
.\.claude\activate-master-coordinator.ps1 --all --parallel
```

### Option 3: Run Specific Phases
```powershell
cd "c:\Users\menum\graxia os"
.\.claude\activate-master-coordinator.ps1 --phases 1,2
```

---

## 📝 Notes

- All subagents follow **Brutal Mode** standards
- Zero tolerance for errors
- All code must pass quality gates
- Tests written before implementation
- Documentation required for every feature

## 🔗 Related Files

- Master Plan: `docs/BRUTAL_ULTRA_MASTER_PLAN.md`
- Implementation Status: `docs/BRUTAL_100_FEATURES_IMPLEMENTATION_STATUS.md`
- Agent Registry: `.claude/references/agents-registry.md`
- Ultra Review: `docs/ULTRA_REVIEW_COMPLETE_SUMMARY.md`
