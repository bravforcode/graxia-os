# Requirements Document: Personal AI Assistant Integration

## Executive Summary

### Vision Statement
ขยายระบบ BRAVOS ที่มีอยู่ให้เป็น Personal Sovereign Enterprise OS ที่ช่วยจัดการชีวิตและงานอัตโนมัติ โดยเริ่มจาก MVP ที่ buildable ใน 2 เดือน แล้วค่อยขยายเป็น phases

### Target Personas

**Persona 1: Solo Founder Sorawit**
- อายุ 28-35 ปี, freelance developer/consultant
- ต้องการ passive income และ automate งานซ้ำๆ
- งบประมาณจำกัด ($50-100/เดือน)
- ทำงานคนเดียว ต้องการ AI ช่วยจัดการทุกอย่าง
- Pain points: หางานใช้เวลามาก, ลืม follow-up, จัดการ network ไม่ทัน

**Persona 2: Builder Bee**
- อายุ 25-32 ปี, กำลังสร้าง SaaS/startup
- ต้องการ network + investors + co-founders
- งบประมาณปานกลาง ($100-300/เดือน)
- ต้องการ scale ตัวเองและทีม
- Pain points: หา co-founder ยาก, pitch investors ไม่ได้, ไม่มีเวลา networking

### Success Metrics (KPIs)

**Phase 1 (MVP - Month 1-2):**
- Job opportunities found: 50+ per week
- Application success rate: >10% (5+ interviews per month)
- Time saved: 10+ hours per week
- System uptime: >99%
- AI cost: <$50/month (revised from $30)

**KPI Source Breakdown:**

| KPI | Source Agent | Platform Distribution | Calculation Method |
|-----|-------------|----------------------|-------------------|
| 50+ jobs/week | Job Hunter | FastWork (15) + LinkedIn (10) + Upwork (10) + Fiverr (5) + Devpost (5) + RSS (5) | 2 runs/day × 3.5 jobs/run × 7 days |
| 10+ contacts/month | Network Builder | LinkedIn (10) | 1 run/day × 0.33 contacts/run × 30 days |
| 10+ hours saved/week | All Agents | Email (4h) + Job Search (3h) + Task Management (3h) | Manual time - Automated time |
| >99% uptime | System | All components | (Total time - Downtime) / Total time |
| <$50/month cost | OpenClaw + Gemini | OpenClaw ($30-50) + Gemini ($5-10) | Sum of all API costs |

**Phase 2 (Month 3-4):**
- Network growth: 20+ quality connections per month
- Passive income: $500+/month from automated funnels
- Content published: 15+ posts per week (automated)
- Email response time: <2 hours (automated)

**Phase 3 (Month 5-6):**
- Total opportunities: 200+ per month (jobs + clients + speaking)
- Network size: 500+ quality contacts
- Passive income: $2000+/month
- ROI: 10x (revenue vs system cost)

## Glossary

- **BRAVOS_System**: ระบบ Backend ที่มีอยู่แล้ว ประกอบด้วย FastAPI, PostgreSQL, SQLAlchemy async, EventBus, และ Agents
- **Personal_Assistant**: Agent ที่ทำหน้าที่เป็นเลขาส่วนตัว จัดการทุกอย่างในชีวิตประจำวัน
- **Email_Manager**: Agent ที่จัดการ email (อ่าน จัดหมวดหมู่ ตอบอัตโนมัติ)
- **Job_Hunter**: Agent ที่หางานให้อัตโนมัติจากทุกแพลตฟอร์ม
- **Network_Builder**: Agent ที่สร้างและดูแล network อัตโนมัติ
- **OpenClaw_Integration**: การเชื่อมต่อกับ OpenClaw สำหรับ web scraping และ automation ขั้นสูง
- **Obsidian_Integration**: การเชื่อมต่อกับ Obsidian สำหรับ knowledge management
- **EventBus**: ระบบ event-driven communication ที่มีอยู่แล้วใน BRAVOS
- **Approval_Flow**: กระบวนการอนุมัติก่อนดำเนินการอัตโนมัติเพื่อความปลอดภัย
- **Scraper**: โมดูลที่ดึงข้อมูลจากแหล่งภายนอก
- **Agent**: โมดูล autonomous ที่ทำงานตาม event และตัดสินใจได้
- **Tactical_Layer**: ชั้นที่ทำงานเฉพาะทาง (scrapers, parsers)
- **Executive_Layer**: ชั้นที่ตัดสินใจและวางแผน (decision_engine, strategy_agent)
- **Learning_Layer**: ชั้นที่เรียนรู้และปรับปรุง (learning_engine, compound_engine)
- **SLA**: Service Level Agreement - ข้อตกลงระดับการให้บริการ
- **P95**: 95th percentile - 95% ของ requests ต้องเร็วกว่าค่านี้
- **P99**: 99th percentile - 99% ของ requests ต้องเร็วกว่าค่านี้
- **Circuit Breaker**: กลไกหยุดการเรียก service ที่ล้มเหลวซ้ำๆ เพื่อป้องกัน cascade failure
- **Idempotent**: การทำงานที่ทำซ้ำกี่ครั้งก็ได้ผลลัพธ์เหมือนเดิม
- **ACID**: Atomicity, Consistency, Isolation, Durability - คุณสมบัติของ database transaction
- **GDPR**: General Data Protection Regulation - กฎหมายคุ้มครองข้อมูลส่วนบุคคลของ EU
- **PII**: Personally Identifiable Information - ข้อมูลที่ระบุตัวบุคคลได้
- **MFA**: Multi-Factor Authentication - การยืนยันตัวตนหลายขั้นตอน
- **JWT**: JSON Web Token - token สำหรับ authentication
- **WCAG**: Web Content Accessibility Guidelines - มาตรฐานการเข้าถึงเว็บไซต์
- **TTL**: Time To Live - ระยะเวลาที่ cache มีอายุ
- **NER**: Named Entity Recognition - การระบุ entities (dates, names, amounts) จาก text
- **AES-256**: Advanced Encryption Standard 256-bit - มาตรฐานการเข้ารหัสที่แข็งแกร่ง
- **Exponential Backoff**: การเพิ่ม delay แบบเลขยกกำลัง (1s, 2s, 4s, 8s) สำหรับ retry
- **Half-Open**: สถานะของ circuit breaker ที่ทดลองส่ง request 1 ครั้งเพื่อตรวจสอบว่า service กลับมาทำงานแล้วหรือไม่
- **Graceful Shutdown**: การปิดระบบอย่างสุภาพโดย cleanup resources ก่อน
- **Event Replay**: การเล่น events ที่ล้มเหลวใหม่อีกครั้ง
- **Deduplication**: การกำจัด duplicates โดยใช้ hash หรือ unique key
- **Source Hash**: SHA256 hash ของ (source + source_id) สำหรับ deduplication
- **Fit Score**: คะแนน (0-10) ที่บอกว่างานเหมาะกับ user มากน้อยแค่ไหน
- **Value Score**: คะแนน (0-10) ที่บอกว่า contact มีคุณค่ามากน้อยแค่ไหน
- **Relationship Strength**: ค่า (0.0-1.0) ที่บอกความแข็งแกร่งของความสัมพันธ์
- **Bridge Node**: Contact ที่เชื่อมต่อ 2+ network clusters
- **Network Cluster**: กลุ่มของ contacts ที่มีความสัมพันธ์กันแน่นแฟ้น
- **Action Priority**: ระดับความสำคัญของงาน (do_now, consider, skip)
- **Approval Request**: คำขออนุมัติจาก agent ก่อนทำ action
- **Daily Briefing**: สรุปงานประจำวันที่ส่งให้ user ทุกเช้า
- **Telegram Bot**: Bot ที่ใช้สำหรับ notifications และ approvals
- **OpenClaw**: Service สำหรับ browser automation และ web scraping ขั้นสูง
- **Gemini**: Google's AI model สำหรับ text generation และ analysis
- **Redis**: In-memory data store สำหรับ caching และ queue
- **Celery**: Distributed task queue สำหรับ background jobs
- **Alembic**: Database migration tool สำหรับ SQLAlchemy
- **Pydantic**: Data validation library สำหรับ Python
- **Hypothesis**: Property-based testing library สำหรับ Python
- **FastAPI**: Modern web framework สำหรับ building APIs
- **SQLAlchemy**: SQL toolkit และ ORM สำหรับ Python
- **PostgreSQL**: Relational database management system
- **Supabase**: Open source Firebase alternative (PostgreSQL + APIs)
- **Railway**: Platform-as-a-Service สำหรับ deploying applications
- **Upstash**: Serverless Redis platform
- **MoSCoW**: Prioritization method (Must have, Should have, Could have, Won't have)
- **MVP**: Minimum Viable Product - ผลิตภัณฑ์ขั้นต่ำที่ใช้งานได้
- **KPI**: Key Performance Indicator - ตัวชี้วัดความสำเร็จ
- **ROI**: Return on Investment - ผลตอบแทนจากการลงทุน
- **ADR**: Architecture Decision Record - บันทึกการตัดสินใจทางสถาปัตยกรรม
- **RACI**: Responsible, Accountable, Consulted, Informed - matrix สำหรับกำหนดบทบาท
- **NFR**: Non-Functional Requirements - ความต้องการที่ไม่ใช่ฟีเจอร์
- **OWASP**: Open Web Application Security Project - องค์กรด้าน web security
- **CI/CD**: Continuous Integration / Continuous Deployment - การ deploy อัตโนมัติ

### Budget Constraints

**Solo Developer Assumptions:**
- Timeline: 6-12 months for full system
- MVP: 2 months (Phase 1)
- Working hours: 20-30 hours/week (part-time)
- Infrastructure budget: $50-100/month
- AI API budget: $30-50/month (Phase 1), $100-200/month (Phase 3)

**Monthly Cost Breakdown (Phase 1):**
- Database (Supabase/Railway): $0-25
- Redis (Upstash): $0-10
- OpenClaw API: $30-50 (revised, with aggressive caching)
- Gemini API: $5-10
- Telegram Bot: $0
- Total: $35-95/month (revised from $25-75)

### Timeline

**Phase 1 (Month 1-2): Core MVP**
- Week 1-2: Database schema + Job Hunter (parallel)
- Week 3: Network Builder (independent, can run parallel)
- Week 4: Email Manager (must complete before Personal Assistant)
- Week 5: Personal Assistant (depends on Email Manager)
- Week 6: Approval Flow (depends on Personal Assistant)
- Week 7-8: Testing + Integration + Bug fixes

**Phase 2 (Month 3-4): Growth**
- Week 9-10: Content automation + Social media
- Week 11-12: Funnel automation + Lead generation
- Week 13-14: Knowledge management + Obsidian
- Week 15-16: Optimization + Learning

**Phase 3 (Month 5-6): Scale**
- Week 17-18: Advanced integrations (n8n, CRM)
- Week 19-20: Analytics + Reporting
- Week 21-22: Security + Compliance
- Week 23-24: Performance optimization

## System Architecture Overview

### 3-Layer Agent Architecture (Existing)

```
┌─────────────────────────────────────────────────────────┐
│                   Learning Layer                         │
│  - Learning Engine (existing)                           │
│  - Compound Engine (existing)                           │
│  - Failure Analysis (existing)                          │
│  - Playbook Capture (existing)                          │
└─────────────────────────────────────────────────────────┘
                           ↑
┌─────────────────────────────────────────────────────────┐
│                  Executive Layer                         │
│  - Decision Engine (existing)                           │
│  - Strategy Agent (existing)                            │
│  - Briefer Agent (existing)                             │
│  + Personal Assistant (NEW)                             │
│  + Network Builder (NEW)                                │
└─────────────────────────────────────────────────────────┘
                           ↑
┌─────────────────────────────────────────────────────────┐
│                   Tactical Layer                         │
│  - Scorer Agent (existing)                              │
│  - Drafter Agent (existing)                             │
│  + Job Hunter (NEW)                                     │
│  + Email Manager (NEW)                                  │
│  + Enhanced Scrapers (NEW)                              │
└─────────────────────────────────────────────────────────┘
                           ↑
┌─────────────────────────────────────────────────────────┐
│                     EventBus (existing)                  │
│  - Async event processing                               │
│  - Retry mechanism                                      │
│  - Event queue                                          │
└─────────────────────────────────────────────────────────┘
```

### Data Flow Overview

```
External Sources → Scrapers → EventBus → Agents → Database
                                  ↓
                            Approval Flow → Telegram → User
                                  ↓
                            Actions → External APIs
```

### Technology Stack Decisions (ADR)

**ADR-001: Use OpenClaw for Advanced Scraping**
- Decision: Use OpenClaw API for LinkedIn, Upwork, Fiverr scraping
- Rationale: Anti-bot protection ต้องใช้ browser automation
- Alternatives: Selenium (slow, resource-heavy), Playwright (complex setup)
- **Cost Calculation (REVISED):**
  - Job Hunter (LinkedIn): 1 run/day × 50 pages = 50 req/day = 1500/month → $30-75/month
  - Network Builder (LinkedIn): 1 run/day × 20 pages = 20 req/day = 600/month → $12-30/month
  - **Total: $42-105/month** (EXCEEDS $30 budget)
- **Mitigation Options:**
  - Option A: Reduce frequency (LinkedIn 3x/week not daily) → $18-36/month
  - Option B: Aggressive caching (4 hours TTL not 1 hour) → $25-50/month
  - Option C: Increase budget to $80/month
  - Option D: Use LinkedIn API where possible (free tier)
  - **CHOSEN: Option A + B** → Target $30-50/month
- Fallback: Direct HTTP scraping สำหรับ sites ที่ไม่มี anti-bot

**ADR-002: PostgreSQL for Primary Database**
- Decision: ใช้ PostgreSQL ที่มีอยู่แล้ว
- Rationale: ACID compliance, JSON support, mature ecosystem
- Existing: มี Alembic migrations, SQLAlchemy models
- No change needed

**ADR-003: Redis for Caching and Queue**
- Decision: ใช้ Redis สำหรับ cache scraping results และ Celery queue
- Rationale: Fast, simple, cost-effective
- Cost: $0-10/month (Upstash free tier)

**ADR-004: Telegram for Notifications and Approvals**
- Decision: ใช้ Telegram Bot ที่มีอยู่แล้ว
- Rationale: Real-time, free, inline keyboards สำหรับ approvals
- Existing: มี telegram_bot module แล้ว

**ADR-005: Obsidian for Knowledge Management**
- Decision: Sync กับ Obsidian vault ผ่าน file system
- Rationale: Local-first, markdown-based, powerful linking
- Implementation: File watcher + markdown parser

### Agent Responsibilities (RACI Matrix)

| Task | Job Hunter | Network Builder | Email Manager | Personal Assistant | Decision Engine |
|------|-----------|----------------|---------------|-------------------|----------------|
| Find jobs | **R,A** | I | - | C | C |
| Score jobs | C | - | - | I | **R,A** |
| Apply to jobs | C | - | - | I | **R,A** |
| Find contacts | I | **R,A** | - | C | C |
| Send outreach | - | C | **R** | I | **A** |
| Manage inbox | - | - | **R,A** | C | I |
| Schedule tasks | - | - | I | **R,A** | C |
| Send alerts | - | - | - | **R,A** | I |
| Learn patterns | I | I | I | I | **R,A** |
| Write audit_logs | **R** | **R** | **R** | **R** | **R** |
| Read skill_profile | **R** | **R** | - | I | **R** |
| Budget tracking | C | C | - | **R,A** | C |
| Telegram notifications | - | - | - | **R,A** | I |
| Rate limiting | C | C | C | I | **R,A** |

**Legend:** R=Responsible, A=Accountable, C=Consulted, I=Informed

**Additional Responsibilities:**
- **Notification_Rate_Limiter**: Personal_Assistant (R,A) - ป้องกัน Telegram flood (max 10 messages/hour)
- **Cost_Monitor**: Personal_Assistant (R,A) - ติดตาม OpenClaw + AI costs real-time
- **Circuit_Breaker**: Decision_Engine (R,A) - หยุด agents ที่ fail ซ้ำๆ

### Conflict Resolution Rules

1. **Email Sending:** Email_Manager owns, others request via EventBus
2. **Contact Management:** Network_Builder owns contacts table, CRM_Integrator syncs only
3. **Content Creation:** Content_Generator owns, others distribute
4. **Scoring:** Decision_Engine is final authority
5. **Approvals:** Personal_Assistant routes, User decides

### Failure Cascade Prevention

1. **Circuit Breaker:** หยุด agent ถ้า fail 3 ครั้งติดต่อกัน
2. **Graceful Degradation:** ถ้า OpenClaw down → fallback to direct scraping
3. **Event Replay:** เก็บ failed events ใน queue สำหรับ retry
4. **Alert Escalation:** Critical failures → Telegram alert ทันที
5. **Health Checks:** ตรวจสอบ agent health ทุก 5 นาที

## Phased Roadmap with MoSCoW Prioritization

### Phase 1: Core MVP (Month 1-2) - MUST HAVE

**Goal:** สร้าง foundation ที่ใช้งานได้จริง ประหยัดเวลา 10+ ชั่วโมง/สัปดาห์

**Core Features (15 requirements):**
1. ✅ Job Hunter - หางาน freelance/full-time อัตโนมัติ
2. ✅ Enhanced Scrapers - ดึงข้อมูลจาก 5-7 platforms
3. ✅ OpenClaw Integration - scraping ขั้นสูง
4. ✅ Network Builder - หาและจัดการ contacts
5. ✅ Email Manager - อ่านและจัดหมวดหมู่ email
6. ✅ Personal Assistant - daily briefing + task management
7. ✅ Approval Flow - อนุมัติก่อนส่ง
8. ✅ Database Schema - tables ใหม่ 8 tables
9. ✅ EventBus Extensions - events ใหม่
10. ✅ API Endpoints - 8 endpoints สำหรับ frontend
11. ✅ Configuration - settings และ validation
12. ✅ Monitoring - metrics และ health checks
13. ✅ Error Handling - retry และ circuit breaker
14. ✅ Security - encryption และ rate limiting
15. ✅ Testing - unit + integration tests

**Success Criteria:**
- 50+ jobs found per week
- 10+ quality contacts per month
- 95% uptime
- <$50/month cost
- 10+ hours saved per week

### Phase 2: Growth (Month 3-4) - SHOULD HAVE

**Goal:** ขยายความสามารถ สร้าง passive income และ content automation

**Features (10 requirements):**
1. ✅ Content Generator - blog posts, social media
2. ✅ Social Media Manager - schedule และ post
3. ✅ Funnel Builder - landing pages + email sequences
4. ✅ Lead Generator - หา potential clients
5. ✅ Obsidian Integration - knowledge management
6. ✅ Meeting Manager - calendar + transcription
7. ✅ Portfolio Generator - resume + portfolio
8. ✅ Application Tracker - track applications
9. ✅ Learning Engine Extensions - learn from outcomes
10. ✅ Dashboard Extensions - analytics และ reports

**Success Criteria:**
- $500+/month passive income
- 15+ posts per week (automated)
- 20+ leads per month
- 200+ notes in Obsidian

### Phase 3: Scale (Month 5-6) - COULD HAVE

**Goal:** Scale และ optimize ทุกอย่าง

**Features (8 requirements):**
1. ✅ N8N Integration - workflow automation
2. ✅ Advanced Analytics - ROI tracking
3. ✅ Multi-platform UI - mobile app
4. ✅ Advanced Security - compliance (GDPR)
5. ✅ Performance Optimization - caching, CDN
6. ✅ Advanced Integrations - CRM, payment
7. ✅ Community Builder - Discord/Slack automation
8. ✅ Advanced Learning - reinforcement learning

**Success Criteria:**
- $2000+/month passive income
- 500+ quality contacts
- 200+ opportunities per month
- 10x ROI

### Future Roadmap - WON'T HAVE (Yet)

**Phase 4+ (Month 7+):**
- Voice interface (Alexa, Google Assistant)
- Video generation และ editing
- NFT และ crypto automation
- Print on demand
- Advanced AI models (fine-tuning)
- Multi-tenant support
- White-label solution
- Mobile apps (iOS/Android native)
- Desktop apps (Electron)
- Browser extensions
- VS Code extensions


## Complete Database Schema (30 Tables)

### Existing Tables (Keep - 16 tables)
1. `opportunities` - งานที่พบ (existing)
2. `contacts` - contacts และ network (existing)
3. `submissions` - applications ที่ส่งไป (existing)
4. `content_drafts` - drafts ที่รออนุมัติ (existing)
5. `approval_requests` - approval flow (existing)
6. `automation_runs` - agent execution history (existing)
7. `metrics` - system metrics (existing)
8. `cognitive_state` - AI state (existing)
9. `audit_logs` - audit trail (existing)
10. `scoring_weight_history` - scoring weights (existing)
11. `outcome_patterns` - learning patterns (existing)
12. `scraper_health` - scraper status (existing)
13. `skill_profiles` - user skills (existing)
14. `identity_snapshots` - identity versions (existing)
15. `knowledge_items` - knowledge base (existing)
16. `contact_edges` - network graph (existing)

### New Tables (Phase 1 - MVP - 8 tables)

**17. job_postings**
```sql
CREATE TABLE job_postings (
  id UUID PRIMARY KEY,
  source VARCHAR(100) NOT NULL,  -- 'upwork', 'linkedin', 'fastwork'
  source_id VARCHAR(255),
  source_url TEXT NOT NULL,
  source_hash VARCHAR(64) UNIQUE,  -- SHA256 for deduplication
  title VARCHAR(500) NOT NULL,
  description TEXT,
  company VARCHAR(255),
  location VARCHAR(255),
  job_type VARCHAR(50),  -- 'freelance', 'full-time', 'contract'
  salary_min DECIMAL(12,2),
  salary_max DECIMAL(12,2),
  salary_currency VARCHAR(3) DEFAULT 'USD',
  skills JSONB,  -- ['Python', 'FastAPI']
  requirements TEXT,
  posted_at TIMESTAMP,
  deadline TIMESTAMP,
  fit_score DECIMAL(3,2),  -- 0.00-10.00
  action_priority VARCHAR(20),  -- 'do_now', 'consider', 'skip'
  status VARCHAR(50) DEFAULT 'new',  -- 'new', 'scored', 'applied', 'rejected'
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_job_source_hash ON job_postings(source_hash);
CREATE INDEX idx_job_fit_score ON job_postings(fit_score DESC);
CREATE INDEX idx_job_status ON job_postings(status);
CREATE INDEX idx_job_posted ON job_postings(posted_at DESC);
```

**18. email_threads**
```sql
CREATE TABLE email_threads (
  id UUID PRIMARY KEY,
  thread_id VARCHAR(255) UNIQUE,  -- Gmail thread ID
  subject VARCHAR(500),
  participants JSONB,  -- [{'email': 'x@y.com', 'name': 'X'}]
  category VARCHAR(50),  -- 'urgent', 'important', 'normal', 'spam', 'newsletter'
  priority INTEGER DEFAULT 5,  -- 1-10
  last_message_at TIMESTAMP,
  unread_count INTEGER DEFAULT 0,
  has_attachments BOOLEAN DEFAULT FALSE,
  action_items JSONB,  -- [{'task': 'Reply', 'due': '2024-01-01'}]
  status VARCHAR(50) DEFAULT 'unread',  -- 'unread', 'read', 'replied', 'archived'
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_email_category ON email_threads(category);
CREATE INDEX idx_email_priority ON email_threads(priority DESC);
CREATE INDEX idx_email_status ON email_threads(status);
CREATE INDEX idx_email_last_message ON email_threads(last_message_at DESC);
```

**19. email_messages**
```sql
CREATE TABLE email_messages (
  id UUID PRIMARY KEY,
  thread_id UUID REFERENCES email_threads(id),
  message_id VARCHAR(255) UNIQUE,  -- Gmail message ID
  from_email VARCHAR(255),
  from_name VARCHAR(255),
  to_emails JSONB,
  cc_emails JSONB,
  subject VARCHAR(500),
  body_text TEXT,
  body_html TEXT,
  received_at TIMESTAMP,
  is_from_me BOOLEAN DEFAULT FALSE,
  sentiment VARCHAR(20),  -- 'positive', 'neutral', 'negative'
  extracted_data JSONB,  -- {'dates': [], 'amounts': [], 'links': []}
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_email_msg_thread ON email_messages(thread_id);
CREATE INDEX idx_email_msg_received ON email_messages(received_at DESC);
```

**20. assistant_tasks**
```sql
CREATE TABLE assistant_tasks (
  id UUID PRIMARY KEY,
  title VARCHAR(500) NOT NULL,
  description TEXT,
  task_type VARCHAR(50),  -- 'email', 'application', 'follow_up', 'meeting'
  priority INTEGER DEFAULT 5,  -- 1-10
  status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'in_progress', 'completed', 'cancelled'
  due_date TIMESTAMP,
  related_entity_type VARCHAR(50),  -- 'job_posting', 'contact', 'email_thread'
  related_entity_id UUID,
  assigned_to VARCHAR(100) DEFAULT 'user',  -- 'user', 'agent_name'
  completed_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_task_status ON assistant_tasks(status);
CREATE INDEX idx_task_priority ON assistant_tasks(priority DESC);
CREATE INDEX idx_task_due_date ON assistant_tasks(due_date);
CREATE INDEX idx_task_related ON assistant_tasks(related_entity_type, related_entity_id);
CREATE INDEX idx_task_status_priority ON assistant_tasks(status, priority DESC);
```

**21. network_interactions**
```sql
CREATE TABLE network_interactions (
  id UUID PRIMARY KEY,
  contact_id UUID REFERENCES contacts(id),
  interaction_type VARCHAR(50),  -- 'email', 'linkedin_message', 'meeting', 'call'
  direction VARCHAR(20),  -- 'outbound', 'inbound'
  channel VARCHAR(50),  -- 'email', 'linkedin', 'twitter', 'phone'
  subject VARCHAR(500),
  content TEXT,
  sentiment VARCHAR(20),  -- 'positive', 'neutral', 'negative'
  outcome VARCHAR(100),  -- 'replied', 'no_response', 'meeting_scheduled'
  interaction_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_interaction_contact ON network_interactions(contact_id);
CREATE INDEX idx_interaction_type ON network_interactions(interaction_type);
CREATE INDEX idx_interaction_at ON network_interactions(interaction_at DESC);
CREATE INDEX idx_interaction_contact_at ON network_interactions(contact_id, interaction_at DESC);
```

**22. openclaw_usage**
```sql
CREATE TABLE openclaw_usage (
  id UUID PRIMARY KEY,
  request_type VARCHAR(50),  -- 'scrape', 'screenshot', 'pdf'
  target_url TEXT,
  target_platform VARCHAR(100),  -- 'linkedin', 'upwork', 'fiverr'
  tokens_used INTEGER,
  cost_usd DECIMAL(10,4),
  duration_ms INTEGER,
  status VARCHAR(50),  -- 'success', 'error', 'timeout'
  error_message TEXT,
  response_size_bytes INTEGER,
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_openclaw_platform ON openclaw_usage(target_platform);
CREATE INDEX idx_openclaw_status ON openclaw_usage(status);
CREATE INDEX idx_openclaw_created ON openclaw_usage(created_at DESC);
```

**23. scraper_runs**
```sql
CREATE TABLE scraper_runs (
  id UUID PRIMARY KEY,
  scraper_name VARCHAR(100) NOT NULL,
  platform VARCHAR(100),
  run_type VARCHAR(50),  -- 'scheduled', 'manual', 'retry'
  items_found INTEGER DEFAULT 0,
  items_new INTEGER DEFAULT 0,
  items_updated INTEGER DEFAULT 0,
  duration_seconds INTEGER,
  status VARCHAR(50),  -- 'success', 'partial', 'failed'
  error_message TEXT,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_scraper_name ON scraper_runs(scraper_name);
CREATE INDEX idx_scraper_status ON scraper_runs(status);
CREATE INDEX idx_scraper_started ON scraper_runs(started_at DESC);
```

**24. api_rate_limits**
```sql
CREATE TABLE api_rate_limits (
  id UUID PRIMARY KEY,
  service_name VARCHAR(100) NOT NULL,  -- 'openclaw', 'gemini', 'gmail'
  limit_type VARCHAR(50),  -- 'requests_per_minute', 'tokens_per_day', 'cost_per_month'
  limit_value INTEGER,
  current_value INTEGER DEFAULT 0,
  reset_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(service_name, limit_type)
);
```

### New Tables (Phase 2 - Growth - 6 tables)

**25. obsidian_notes**
```sql
CREATE TABLE obsidian_notes (
  id UUID PRIMARY KEY,
  file_path VARCHAR(500) UNIQUE,
  title VARCHAR(500),
  content TEXT,
  frontmatter JSONB,  -- YAML frontmatter
  tags VARCHAR(255)[],
  backlinks VARCHAR(500)[],  -- [[note_name]]
  word_count INTEGER,
  last_modified_at TIMESTAMP,
  synced_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_note_tags ON obsidian_notes USING GIN(tags);
CREATE INDEX idx_note_modified ON obsidian_notes(last_modified_at DESC);
```

**26. content_calendar**
```sql
CREATE TABLE content_calendar (
  id UUID PRIMARY KEY,
  content_type VARCHAR(50),  -- 'blog', 'twitter', 'linkedin', 'newsletter'
  title VARCHAR(500),
  content TEXT,
  platforms VARCHAR(50)[],  -- ['twitter', 'linkedin']
  scheduled_for TIMESTAMP,
  status VARCHAR(50) DEFAULT 'draft',  -- 'draft', 'scheduled', 'published', 'failed'
  published_at TIMESTAMP,
  engagement_metrics JSONB,  -- {'likes': 10, 'shares': 5}
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_content_scheduled ON content_calendar(scheduled_for);
CREATE INDEX idx_content_status ON content_calendar(status);
```

**27. leads**
```sql
CREATE TABLE leads (
  id UUID PRIMARY KEY,
  email VARCHAR(255) UNIQUE,
  name VARCHAR(255),
  company VARCHAR(255),
  source VARCHAR(100),  -- 'linkedin', 'twitter', 'website'
  funnel_name VARCHAR(100),
  current_stage VARCHAR(100),
  lead_score INTEGER,  -- 0-100
  tags VARCHAR(100)[],
  custom_fields JSONB,
  last_contacted_at TIMESTAMP,
  next_followup_at TIMESTAMP,
  status VARCHAR(50) DEFAULT 'new',  -- 'new', 'contacted', 'qualified', 'converted', 'lost'
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_lead_status ON leads(status);
CREATE INDEX idx_lead_score ON leads(lead_score DESC);
CREATE INDEX idx_lead_next_followup ON leads(next_followup_at);
```

**28. meeting_transcripts**
```sql
CREATE TABLE meeting_transcripts (
  id UUID PRIMARY KEY,
  calendar_event_id VARCHAR(255),
  meeting_title VARCHAR(500),
  participants JSONB,
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  duration_minutes INTEGER,
  transcript_text TEXT,
  summary TEXT,
  action_items JSONB,  -- [{'task': 'X', 'owner': 'Y', 'due': 'Z'}]
  key_decisions JSONB,
  recording_url TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_meeting_started ON meeting_transcripts(started_at DESC);
```

**29. application_history**
```sql
CREATE TABLE application_history (
  id UUID PRIMARY KEY,
  job_posting_id UUID REFERENCES job_postings(id),
  submission_id UUID REFERENCES submissions(id),
  status VARCHAR(50),  -- 'submitted', 'viewed', 'interview_requested', 'offer', 'rejected'
  status_changed_at TIMESTAMP,
  notes TEXT,
  next_action VARCHAR(255),
  next_action_due TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_app_history_job ON application_history(job_posting_id);
CREATE INDEX idx_app_history_status ON application_history(status);
CREATE INDEX idx_app_history_next_action ON application_history(next_action_due);
```

**30. n8n_workflows** (Phase 3)
```sql
CREATE TABLE n8n_workflows (
  id UUID PRIMARY KEY,
  workflow_id VARCHAR(255) UNIQUE,
  workflow_name VARCHAR(255),
  description TEXT,
  trigger_type VARCHAR(100),  -- 'webhook', 'schedule', 'manual'
  webhook_url TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  last_executed_at TIMESTAMP,
  execution_count INTEGER DEFAULT 0,
  success_count INTEGER DEFAULT 0,
  error_count INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

### Index Strategy

**High-Priority Indexes (Phase 1):**
- `job_postings.source_hash` - deduplication (UNIQUE)
- `job_postings.fit_score` - sorting (DESC)
- `email_threads.priority` - sorting (DESC)
- `assistant_tasks.due_date` - scheduling
- `network_interactions.contact_id` - joins
- `openclaw_usage.created_at` - cost tracking

**Composite Indexes:**
- `(status, priority DESC)` on assistant_tasks
- `(contact_id, interaction_at DESC)` on network_interactions
- `(service_name, limit_type)` on api_rate_limits

### Partitioning Plan (Phase 3)

**Time-based Partitioning:**
- `email_messages` - partition by month (received_at)
- `network_interactions` - partition by quarter (interaction_at)
- `openclaw_usage` - partition by month (created_at)
- `scraper_runs` - partition by month (started_at)

### Archival Strategy

**Retention Policies:**
- `email_messages` - archive after 1 year → cold storage
- `network_interactions` - keep all (relationship history)
- `openclaw_usage` - aggregate monthly → delete details after 3 months
- `scraper_runs` - keep last 1000 runs per scraper
- `audit_logs` - archive after 6 months → compliance storage


## Security Threat Model

### Threat Categories

**1. API Key Exposure**
- **Threat:** API keys (OpenClaw, Gemini, Gmail) leaked ใน logs/code
- **Impact:** High - unauthorized usage, cost explosion
- **Likelihood:** Medium
- **Mitigation:** 
  - Encrypt keys ใน database (AES-256)
  - Never log keys
  - Rotate keys monthly
  - Use environment variables only
- **Detection:** Monitor unusual API usage patterns

**2. Prompt Injection**
- **Threat:** Malicious input ใน email/job descriptions → AI ทำงานผิด
- **Impact:** Medium - wrong decisions, data leakage
- **Likelihood:** Medium
- **Mitigation:**
  - Sanitize all inputs
  - Use structured prompts
  - Validate AI outputs
  - Approval flow สำหรับ critical actions
- **Detection:** Log all AI inputs/outputs

**3. Data Leakage**
- **Threat:** PII (emails, contacts) leaked ผ่าน AI APIs
- **Impact:** High - GDPR violations, privacy breach
- **Likelihood:** Low
- **Mitigation:**
  - Anonymize data before sending to AI
  - Use local models สำหรับ sensitive data (Phase 3)
  - Encrypt data at rest และ in transit
  - Audit all data access
- **Detection:** Data access logs

**4. Scraper Detection and Blocking**
- **Threat:** LinkedIn/Upwork block scrapers → no data
- **Impact:** Medium - feature degradation
- **Likelihood:** High
- **Mitigation:**
  - Use OpenClaw (browser automation)
  - Rotate IPs/user agents
  - Respect rate limits
  - Fallback to manual input
- **Detection:** Scraper health metrics

**5. Cost Explosion**
- **Threat:** Infinite loop → OpenAI/OpenClaw cost explosion
- **Impact:** High - budget overrun
- **Likelihood:** Medium
- **Mitigation:**
  - Hard limits per service ($50/month)
  - Circuit breaker after 3 failures
  - Alert at 80% budget
  - Rate limiting
- **Detection:** Real-time cost tracking

**6. Unauthorized Access**
- **Threat:** Attacker access API/database
- **Impact:** Critical - full system compromise
- **Likelihood:** Low
- **Mitigation:**
  - API authentication (JWT tokens)
  - Database credentials rotation
  - Network isolation (VPC)
  - MFA for admin access (Phase 2)
- **Detection:** Failed login attempts

### 4-Tier Fallback Strategy (Platform-Specific)

**Platform Routing Strategy:**

```
LinkedIn, Upwork, Fiverr (Anti-bot sites):
├── Tier 1: OpenClaw (Primary) - 95% success rate, $0.02-0.05/req, 30-60s latency
│   └── Fallback: Cached Data (Tier 2) - 50% success (stale), $0, <1s latency
│       └── Fallback: Alert User (Tier 3) - 100% success (manual), $0, minutes-hours latency

FastWork, Devpost, RSS (Direct scraping sites):
├── Tier 1: Direct Scraper (Primary) - 70-80% success rate, $0, <10s latency
│   └── Fallback: OpenClaw (Tier 2) - 95% success, $0.02-0.05/req, 30-60s latency
│       └── Fallback: Cached Data (Tier 3) - 50% success (stale), $0, <1s latency
│           └── Fallback: Alert User (Tier 4) - 100% success (manual), $0, minutes-hours latency
```

**Fallback Decision Logic:**
1. **Check platform type** → Route to appropriate Tier 1
2. **If Tier 1 fails** → Check cache (TTL 4 hours)
3. **If cache miss/stale** → Try next tier
4. **If all tiers fail** → Alert user via Telegram

**Cache Strategy:**
- **TTL:** 4 hours (aggressive caching to reduce costs)
- **Cache key:** `{platform}:{search_query}:{page}`
- **Cache hit target:** >= 40% (reduces API calls by 40%)

**Cost Impact:**
- Without cache: $42-105/month
- With 40% cache hit: $25-63/month ✅ Within budget

### API Key Rotation Policy

**Monthly Rotation (Automated):**
- OpenClaw API key
- Gemini API key
- Telegram Bot token

**Quarterly Rotation (Manual):**
- Database credentials
- Gmail OAuth tokens
- Webhook secrets

**Immediate Rotation (On Breach):**
- All keys and tokens
- Notify all services
- Audit all access logs

### Agent Permissions Matrix

| Agent | Database Write | External API | Send Email | Spend Money |
|-------|---------------|--------------|------------|-------------|
| Job Hunter | ✅ (jobs table) | ✅ (OpenClaw) | ❌ | ✅ ($0.10/request) |
| Network Builder | ✅ (contacts) | ✅ (LinkedIn) | ❌ | ✅ ($0.05/request) |
| Email Manager | ✅ (emails) | ✅ (Gmail) | ⚠️ (approval) | ❌ |
| Personal Assistant | ✅ (tasks) | ❌ | ⚠️ (approval) | ❌ |
| Decision Engine | ✅ (all) | ❌ | ❌ | ❌ |

**Legend:** ✅ = Allowed, ❌ = Denied, ⚠️ = Requires approval

### Prompt Injection Protection

**Input Sanitization:**
```python
def sanitize_input(text: str) -> str:
    # Remove system prompts
    text = re.sub(r'(system:|assistant:|user:)', '', text, flags=re.IGNORECASE)
    # Remove code blocks
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    # Limit length
    return text[:5000]
```

**Structured Prompts:**
```python
prompt = f"""
You are a job scoring assistant. Score this job posting.

Job Title: {sanitize_input(job.title)}
Description: {sanitize_input(job.description)}

Output JSON only: {{"score": 0-10, "reason": "..."}}
"""
```

### PII Handling

**PII Categories:**
- **High Sensitivity:** Passwords, API keys, credit cards
- **Medium Sensitivity:** Email addresses, phone numbers, names
- **Low Sensitivity:** Company names, job titles

**Handling Rules:**
1. **Never log** high sensitivity data
2. **Encrypt at rest** all PII (AES-256)
3. **Anonymize** before sending to AI APIs
4. **Audit** all PII access
5. **Delete** on user request (GDPR right to be forgotten)

**Anonymization Strategy:**
- Replace emails with `user_<hash>@example.com`
- Replace names with `Person_<id>`
- Replace phone numbers with `+XX-XXX-XXXX`

## Non-Functional Requirements (NFR)

### Performance Requirements

**API Response Times (P95):**
- GET endpoints: <200ms
- POST endpoints: <500ms
- Agent execution: <30 seconds
- Scraper execution: <2 minutes

**Database Query Times (P95):**
- Simple queries: <50ms
- Complex joins: <200ms
- Aggregations: <500ms

**Throughput:**
- API requests: 100 req/sec
- Concurrent agents: 10 agents
- Scraper jobs: 50 jobs/hour

**SLA Targets:**
- Uptime: 99.9% (43 minutes downtime/month)
- Data durability: 99.999%
- Backup recovery: <1 hour

### Scalability Requirements

**Phase 1 (MVP):**
- Users: 1 user (solo developer)
- Jobs: 500 jobs/week
- Contacts: 100 contacts/month
- Emails: 1000 emails/month
- Database: <1 GB
- API calls: 10,000/month

**Phase 2 (Growth):**
- Users: 1 user
- Jobs: 2000 jobs/week
- Contacts: 500 contacts/month
- Emails: 5000 emails/month
- Database: <5 GB
- API calls: 50,000/month

**Phase 3 (Scale):**
- Users: 1-5 users (team)
- Jobs: 10,000 jobs/week
- Contacts: 2000 contacts/month
- Emails: 20,000 emails/month
- Database: <20 GB
- API calls: 200,000/month

**Design for Future:**
- 100 concurrent users
- 1M jobs/month
- 100 GB database
- Horizontal scaling ready

### Cost Requirements

**Phase 1 Budget (Monthly):**
- Infrastructure: $25-50
  - Database (Supabase): $0-25
  - Redis (Upstash): $0-10
  - Hosting (Railway): $0-15
- AI APIs: $35-60
  - OpenClaw: $30-50 (with aggressive caching)
  - Gemini: $5-10
- **Total: $60-110/month** (revised from $45-80)
- **Target: <$80/month** (with optimization)

**Phase 2 Budget (Monthly):**
- Infrastructure: $50-100
- AI APIs: $50-100
- **Total: $100-200/month**

**Phase 3 Budget (Monthly):**
- Infrastructure: $100-200
- AI APIs: $100-200
- **Total: $200-400/month**

**Cost Optimization Strategies:**
- Aggressive caching (4 hour TTL) → Save 40% on API calls
- Reduce scraping frequency (3x/week not daily) → Save 50% on OpenClaw
- Use Gemini Flash instead of Pro → Save 50% on AI costs
- Batch operations → Reduce database connections
- Archive old data → Reduce storage costs

**Cost Alerts:**
- Warning at 80% budget ($64/month for Phase 1)
- Hard stop at 100% budget ($80/month for Phase 1)
- Daily cost reports via Telegram
- Weekly cost review and optimization

### Reliability Requirements

**Error Rates:**
- API errors: <1%
- Agent failures: <5%
- Scraper failures: <10%

**Recovery:**
- Automatic retry: 3 attempts with exponential backoff (1s, 2s, 4s)
- Circuit breaker: Open after 3 consecutive failures, half-open after 60s
- Graceful degradation: Fallback to cached data
- Manual intervention: Alert user after all retries fail

**Data Integrity:**
- ACID transactions for critical operations
- Idempotent operations (safe to retry)
- Deduplication (source_hash)
- Audit trail for all changes

### Availability Requirements

**Uptime Targets:**
- API: 99.9% (43 min downtime/month)
- Database: 99.95% (22 min downtime/month)
- Scrapers: 95% (best effort)

**Maintenance Windows:**
- Scheduled: Sundays 2-4 AM UTC
- Emergency: Anytime with 15-min notice via Telegram

**Monitoring:**
- Health checks every 5 minutes
- Alert on 2 consecutive failures
- Telegram notifications for critical issues

### Usability Requirements

**Response Times:**
- Telegram bot: <5 seconds
- Dashboard load: <2 seconds
- Search results: <1 second

**Accessibility (Phase 2):**
- WCAG 2.1 Level AA compliance
- Keyboard navigation
- Screen reader support
- High contrast mode

**Internationalization:**
- Thai language (primary)
- English language (secondary)
- UTF-8 support
- Timezone handling (Asia/Bangkok)

### Maintainability Requirements

**Code Quality:**
- Test coverage: >80%
- Type hints: 100% (Python)
- Linting: Pass (ruff, mypy)
- Documentation: All public APIs

**Deployment:**
- Zero-downtime deployments
- Rollback in <5 minutes
- Database migrations (Alembic)
- Environment parity (dev/staging/prod)

**Monitoring:**
- Structured logging (JSON)
- Distributed tracing (OpenTelemetry) - Phase 3
- Metrics (Prometheus) - Phase 3
- Dashboards (Grafana) - Phase 3


## Testing Strategy

### Unit Tests (>80% coverage)

**Scoring Algorithms:**
- Property: `score(job) >= 0 AND score(job) <= 10`
- Property: `score(job_with_all_skills) > score(job_with_some_skills)`
- Example: Job with Python + FastAPI → score > 7.0

**Data Transformations:**
- Property: Round-trip `parse(format(job)) == job`
- Property: Idempotence `deduplicate(deduplicate(jobs)) == deduplicate(jobs)`
- Edge case: Empty job list, null values, special characters

**Agent Logic:**
- Unit test: Job Hunter filters by fit_score
- Unit test: Email Manager categorizes by keywords
- Mock: External APIs (OpenClaw, Gmail)

### Contract Tests

**API Integrations:**
- OpenClaw API: Verify request/response schema
- Gmail API: Verify OAuth flow
- Telegram API: Verify webhook payload

**Database:**
- Schema validation: All tables exist
- Foreign keys: Referential integrity
- Indexes: Performance benchmarks

### Integration Tests

**End-to-End Workflows:**
1. Job found → Scored → Approved → Applied
2. Email received → Categorized → Task created → Replied
3. Contact discovered → Scored → Outreach sent → Interaction logged

**Database Operations:**
- Transaction rollback on error
- Concurrent writes (race conditions)
- Query performance (<200ms)

### Chaos Tests (Phase 2)

**Agent Failure:**
- Kill agent mid-execution → verify recovery
- Database connection lost → verify reconnect
- OpenClaw timeout → verify fallback

**Load Tests:**
- 100 concurrent scraper jobs
- 1000 emails processed in 1 minute
- 50 agents running simultaneously

### Security Tests (Phase 2)

**OWASP Top 10:**
- SQL injection: Parameterized queries
- XSS: Input sanitization
- CSRF: Token validation
- Authentication: JWT expiration
- Authorization: Permission checks

**Prompt Injection:**
- Malicious job descriptions
- Email with system prompts
- Special characters in inputs

### Property-Based Tests (PBT)

**When to Use PBT:**
✅ Scoring algorithms (varies with input)
✅ Data transformations (parse/format)
✅ Deduplication logic
✅ Network graph algorithms
❌ External API calls (use mocks)
❌ Configuration validation (use examples)

**Example PBT:**
```python
@given(st.text(min_size=1, max_size=500))
def test_job_title_sanitization(title):
    sanitized = sanitize_input(title)
    assert len(sanitized) <= 500
    assert '<script>' not in sanitized.lower()
    assert 'system:' not in sanitized.lower()
```

### Regression Tests

**Automated Regression Suite:**
- Run full Phase 1 test suite before Phase 2 deployment
- Automated regression on every PR (GitHub Actions)
- Baseline performance benchmarks measured weekly
- Compare against baseline: response time, throughput, error rate
- Alert if regression detected (>10% slower, >1% more errors)

**Regression Test Scope:**
- All Phase 1 critical workflows (job found → applied, email → replied)
- All API endpoints (GET /jobs, GET /contacts, etc.)
- All database operations (CRUD, transactions)
- All agent executions (Job Hunter, Email Manager, etc.)

**Regression Prevention:**
- Version control for test data
- Snapshot testing for UI components
- Contract testing for API changes
- Performance budgets (response time <200ms)

## Definition of Done

**For Each Requirement:**
- [ ] Unit tests pass (>80% coverage)
- [ ] Integration test passes
- [ ] Error handling complete (try/except, retry, fallback)
- [ ] Metrics emitted (execution time, success rate, cost)
- [ ] Telegram alerts work (success, failure, warnings)
- [ ] Code reviewed (self-review checklist)
- [ ] Documentation updated (docstrings, README)
- [ ] Database migration created (if schema changes)
- [ ] API endpoint documented (if new endpoint)
- [ ] Manual testing done (happy path + edge cases)

**For Phase Completion:**
- [ ] All requirements in phase completed
- [ ] Success criteria met (KPIs)
- [ ] Performance benchmarks met (SLAs)
- [ ] Security review done
- [ ] User acceptance testing done
- [ ] Deployment successful (staging → production)
- [ ] Monitoring dashboards updated
- [ ] Runbook updated (troubleshooting guide)

## Dependency Map

```
Phase 1 Dependencies:
├── Database Schema (Week 1)
│   └── All agents depend on this
├── EventBus Extensions (Week 1)
│   └── All agents depend on this
├── OpenClaw Integration (Week 2)
│   ├── Job Hunter depends on this
│   └── Network Builder depends on this
├── Job Hunter (Week 2)
│   └── Decision Engine depends on this
├── Network Builder (Week 3)
│   └── Independent (can run parallel)
├── Email Manager (Week 4)
│   └── Personal Assistant depends on this
├── Personal Assistant (Week 5)
│   └── Approval Flow depends on this
└── Approval Flow (Week 6)
    └── All sending actions depend on this

Phase 2 Dependencies:
├── Obsidian Integration (Week 13)
│   └── Knowledge Manager depends on this
├── Content Generator (Week 9)
│   └── Social Media Manager depends on this
└── Funnel Builder (Week 11)
    └── Lead Generator depends on this

Phase 3 Dependencies:
├── N8N Integration (Week 17)
│   └── All workflow automation depends on this
└── Advanced Analytics (Week 19)
    └── ROI tracking depends on this
```

## Rollback Plan

### Phase 1 Go/No-Go Gate Criteria

**✅ Go Criteria (Proceed to Phase 2):**
- Jobs found: >30 jobs/week
- Contacts added: >5 contacts/month
- System uptime: >95%
- Cost: <$80/month
- Critical bugs: 0
- User satisfaction: Positive feedback

**⚠️ Conditional Go (Fix in first 2 weeks of Phase 2):**
- Jobs found: 20-30 jobs/week
- Contacts added: 3-5 contacts/month
- System uptime: 90-95%
- Cost: $80-100/month
- Minor bugs: <5
- Action: Identify root cause, implement fixes, re-evaluate after 2 weeks

**❌ No-Go (Investigate before proceeding):**
- Jobs found: <20 jobs/week
- Contacts added: <3 contacts/month
- System uptime: <90%
- Cost: >$100/month
- Critical bugs: >0
- Action: Stop Phase 2 development, focus on fixing Phase 1 issues

### Rollback Procedures

**Database Rollback:**
1. Stop all agents (graceful shutdown)
2. Run Alembic downgrade: `alembic downgrade -1`
3. Verify data integrity
4. Restart agents
5. Time: <10 minutes

**Code Rollback:**
1. Git revert to previous stable commit
2. Redeploy via Railway/Docker
3. Run smoke tests
4. Time: <5 minutes

**Configuration Rollback:**
1. Restore previous .env file from backup
2. Restart services
3. Verify configuration
4. Time: <2 minutes

**Full System Rollback:**
1. Database rollback (10 min)
2. Code rollback (5 min)
3. Configuration rollback (2 min)
4. Full system test (10 min)
5. Total time: <30 minutes

### Rollback Testing

**Pre-deployment Checklist:**
- [ ] Database backup created
- [ ] Configuration backup created
- [ ] Rollback procedure tested in staging
- [ ] Rollback time measured (<30 min)
- [ ] Monitoring alerts configured
- [ ] Telegram notification tested

**Post-rollback Verification:**
- [ ] Database integrity check passed
- [ ] All agents running
- [ ] API endpoints responding
- [ ] No data loss
- [ ] Metrics collection working
- [ ] User notified of rollback

## Operational Runbook

### Common Scenarios and Solutions

#### 1. Job Hunter Stops Finding Jobs

**Symptoms:**
- `scraper_runs.items_found = 0` for 3+ consecutive runs
- No new jobs in `job_postings` table for 24 hours

**Diagnosis Steps:**
1. Check scraper_runs table: `SELECT * FROM scraper_runs WHERE scraper_name='job_hunter' ORDER BY started_at DESC LIMIT 10`
2. Check status and error_message
3. If status='failed': Check error_message for details
4. If OpenClaw error: Check openclaw_usage table for rate limits
5. Check Redis cache: `redis-cli GET "linkedin:jobs:*"`

**Solutions:**
- **If rate limited:** Wait 1 hour, reduce frequency to 3x/week
- **If OpenClaw down:** Fallback to FastWork only (direct scraper)
- **If scraper broken:** Check CSS selectors, update if site changed
- **If persistent:** Manual job input via API, investigate root cause

**Prevention:**
- Monitor scraper_health metrics
- Alert on 2 consecutive failures
- Maintain 4-tier fallback strategy

---

#### 2. OpenClaw Budget Near Limit

**Symptoms:**
- `SUM(cost_usd) FROM openclaw_usage` approaching $50/month
- Telegram alert: "OpenClaw budget at 80%"

**Diagnosis Steps:**
1. Check current spend: `SELECT SUM(cost_usd) FROM openclaw_usage WHERE created_at >= date_trunc('month', NOW())`
2. Check daily burn rate: `SELECT DATE(created_at), SUM(cost_usd) FROM openclaw_usage GROUP BY DATE(created_at) ORDER BY DATE DESC LIMIT 7`
3. Identify top consumers: `SELECT target_platform, COUNT(*), SUM(cost_usd) FROM openclaw_usage GROUP BY target_platform`

**Solutions:**
- **If >$40:** Pause LinkedIn scraping immediately
- **If >$45:** Pause all OpenClaw scraping, use cache only
- Increase cache TTL to 8 hours
- Reduce scraping frequency (daily → 3x/week)
- Switch to direct scrapers where possible

**Prevention:**
- Set hard limit at $50 in code
- Alert at $40 (80% threshold)
- Monitor daily burn rate
- Optimize cache hit rate (target 50%+)

---

#### 3. Database Is Slow

**Symptoms:**
- API response time >500ms (P95)
- Query time >200ms in logs
- Connection pool exhausted

**Diagnosis Steps:**
1. Check slow queries: `SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10`
2. Check connection pool: `SELECT count(*) FROM pg_stat_activity`
3. Check table sizes: `SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) FROM pg_tables ORDER BY pg_total_relation_size DESC LIMIT 10`
4. Check missing indexes: `SELECT schemaname, tablename, attname FROM pg_stats WHERE n_distinct < 100 AND null_frac < 0.1`

**Solutions:**
- **Add indexes** for slow queries (CREATE INDEX CONCURRENTLY)
- **Increase connection pool** size (default 10 → 20)
- **Restart Celery workers** if pool full
- **Archive old data** (email_messages >1 year)
- **Vacuum tables** if bloated: `VACUUM ANALYZE`

**Prevention:**
- Monitor query performance weekly
- Set up pg_stat_statements
- Regular VACUUM ANALYZE (weekly)
- Partition large tables (Phase 3)

---

#### 4. Email Manager Not Processing Emails

**Symptoms:**
- No new emails in `email_threads` table for 1+ hours
- Gmail API errors in logs
- Unread count not updating

**Diagnosis Steps:**
1. Check Gmail API quota: Check Google Cloud Console
2. Check OAuth token: Verify token not expired
3. Check email_threads: `SELECT COUNT(*) FROM email_threads WHERE created_at > NOW() - INTERVAL '1 hour'`
4. Check agent status: `SELECT * FROM automation_runs WHERE agent_name='email_manager' ORDER BY started_at DESC LIMIT 5`

**Solutions:**
- **If quota exceeded:** Wait for reset (daily quota)
- **If token expired:** Refresh OAuth token manually
- **If agent crashed:** Restart agent, check error logs
- **If Gmail API down:** Wait for Google to fix, use cached data

**Prevention:**
- Monitor Gmail API quota daily
- Set up token auto-refresh
- Alert on 2 consecutive failures
- Implement exponential backoff

---

#### 5. Telegram Bot Not Responding

**Symptoms:**
- User sends message, no response
- Approval requests not delivered
- Webhook errors in logs

**Diagnosis Steps:**
1. Check Telegram webhook: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
2. Check bot status: Test with `/start` command
3. Check logs for webhook errors
4. Check network connectivity

**Solutions:**
- **If webhook broken:** Re-register webhook
- **If bot blocked:** Contact Telegram support
- **If network issue:** Check firewall, DNS
- **If rate limited:** Reduce notification frequency

**Prevention:**
- Monitor webhook health
- Implement notification rate limiting (10/hour)
- Fallback to email notifications
- Test bot weekly

---

#### 6. High Memory Usage

**Symptoms:**
- Memory usage >80%
- OOM (Out of Memory) errors
- Slow performance

**Diagnosis Steps:**
1. Check memory usage: `free -h`
2. Check process memory: `ps aux --sort=-%mem | head -10`
3. Check Redis memory: `redis-cli INFO memory`
4. Check Python memory: Use memory_profiler

**Solutions:**
- **Restart services** to free memory
- **Clear Redis cache:** `redis-cli FLUSHDB`
- **Reduce Celery workers** (10 → 5)
- **Optimize queries** to reduce memory usage
- **Upgrade server** if persistent

**Prevention:**
- Monitor memory usage
- Set up alerts at 80%
- Regular cache cleanup
- Optimize data structures

---

#### 7. Cost Explosion Alert

**Symptoms:**
- Total cost >$80/month
- Unexpected charges
- Budget alert triggered

**Diagnosis Steps:**
1. Check OpenClaw costs: `SELECT SUM(cost_usd) FROM openclaw_usage WHERE created_at >= date_trunc('month', NOW())`
2. Check Gemini costs: Check Google Cloud Console
3. Check infrastructure costs: Check Railway/Supabase dashboard
4. Identify anomalies: Compare with previous months

**Solutions:**
- **Pause all AI agents** immediately
- **Investigate root cause** (infinite loop? bug?)
- **Reduce frequency** of expensive operations
- **Switch to cheaper alternatives** (Gemini Flash)
- **Increase cache TTL** to reduce API calls

**Prevention:**
- Set hard limits in code
- Monitor costs daily
- Alert at 80% budget
- Review costs weekly

---

### Emergency Contacts

**Critical Issues:**
- Developer: [Your contact]
- Telegram: @your_username
- Email: your_email@example.com

**Service Status Pages:**
- OpenClaw: https://status.openclaw.com
- Railway: https://status.railway.app
- Supabase: https://status.supabase.com
- Telegram: https://telegram.org/status

### Monitoring Checklist (Daily)

- [ ] Check scraper_runs (jobs found today)
- [ ] Check openclaw_usage (cost today)
- [ ] Check system uptime (>99%)
- [ ] Check error logs (critical errors)
- [ ] Check Telegram bot (test message)
- [ ] Check API health endpoint
- [ ] Review Telegram alerts

### Monitoring Checklist (Weekly)

- [ ] Review total costs (vs budget)
- [ ] Review KPIs (jobs, contacts, time saved)
- [ ] Review slow queries (optimize)
- [ ] Review error patterns (fix bugs)
- [ ] Backup database
- [ ] Update documentation
- [ ] Plan next week's work

## Risk Register

| Risk | Impact | Likelihood | Mitigation | Owner |
|------|--------|-----------|------------|-------|
| LinkedIn blocks scraping | High | High | Use OpenClaw + 4-tier fallback | Job Hunter |
| OpenAI cost explosion | High | Medium | Hard limits + circuit breaker | All Agents |
| Developer burnout | High | High | Realistic timeline + MVP focus | Developer |
| GDPR compliance issues | High | Low | Anonymize data + audit logs | Security |
| Database performance | Medium | Medium | Indexes + partitioning (Phase 3) | Database |
| OpenClaw API downtime | Medium | Low | 4-tier fallback + cached data | OpenClaw Integration |
| Gmail API rate limits | Medium | Medium | Respect limits + backoff | Email Manager |
| Telegram bot blocked | Low | Low | Fallback to email notifications | Personal Assistant |
| Redis downtime | Low | Low | Graceful degradation | All Agents |
| Scope creep | High | High | Strict MoSCoW + phase gates | Developer |

**Risk Mitigation Actions:**
1. **LinkedIn Blocking (High/High):**
   - Implement 4-tier fallback immediately
   - Monitor scraper health metrics
   - Have manual input UI ready

2. **Cost Explosion (High/Medium):**
   - Set hard limits in code ($50/month)
   - Alert at 80% budget
   - Circuit breaker after 3 failures

3. **Developer Burnout (High/High):**
   - Focus on MVP only (15 requirements)
   - 20-30 hours/week max
   - Take breaks between phases

4. **Scope Creep (High/High):**
   - Strict MoSCoW prioritization
   - Phase gates (no Phase 2 until Phase 1 done)
   - Say NO to new features during MVP


## Core Requirements (Phase 1 - MVP)

### Requirement 1: Job Hunter Agent

**User Story:** ในฐานะผู้ใช้ ฉันต้องการให้ระบบหางานให้ฉันอัตโนมัติ เพื่อเพิ่มโอกาสในการหารายได้และประหยัดเวลา

#### Acceptance Criteria (Measurable)

1. THE Job_Hunter SHALL ค้นหางาน freelance จาก Fastwork ทุก 6 ชั่วโมง และพบอย่างน้อย 10 งานใหม่ต่อสัปดาห์
2. THE Job_Hunter SHALL ค้นหางาน full-time จาก LinkedIn (via OpenClaw) ทุก 12 ชั่วโมง และพบอย่างน้อย 5 งานใหม่ต่อสัปดาห์
3. WHEN พบงานใหม่, THE Job_Hunter SHALL ประเมิน fit_score (0-10) ภายใน 30 วินาที โดยใช้ skill_profile และ identity
4. WHEN งานมี fit_score >= 7.0, THE Job_Hunter SHALL emit event "job.found" ไปยัง EventBus ภายใน 5 วินาที
5. THE Job_Hunter SHALL บันทึกงานลงใน job_postings table พร้อม source_hash สำหรับ deduplication โดยมี duplicate rate < 5%
6. THE Job_Hunter SHALL ตรวจสอบ duplicate โดยใช้ SHA256(source + source_id) ก่อนบันทึก
7. THE Job_Hunter SHALL บันทึก scraper_runs metrics (items_found, items_new, duration_seconds) ทุกครั้งที่รัน
8. THE Job_Hunter SHALL มี success rate >= 90% (scraper runs ที่สำเร็จ / total runs)

**Performance SLAs:**
- Scraper execution time: <2 minutes (P95)
- Fit score calculation: <30 seconds per job
- Database write: <100ms per job
- Throughput: 50+ jobs per hour

**Cost SLAs:**
- OpenClaw cost: <$0.10 per job found
- Total cost: <$20/month for 200 jobs/week

### Requirement 2: Enhanced Scrapers with OpenClaw

**User Story:** ในฐานะระบบ ฉันต้องการขยายความสามารถของ Scrapers ด้วย OpenClaw เพื่อดึงข้อมูลจาก sites ที่มี anti-bot protection

#### Acceptance Criteria (Measurable)

1. THE Enhanced_Scrapers SHALL ใช้ OpenClaw สำหรับ scraping LinkedIn, Upwork, Fiverr โดยมี success rate >= 95%
2. THE Enhanced_Scrapers SHALL ใช้ existing scrapers (fastwork, devpost, eventpop) ร่วมกับ OpenClaw โดยมี success rate >= 90%
3. WHEN scraping ล้มเหลวด้วย traditional method, THE Enhanced_Scrapers SHALL fallback ไปใช้ OpenClaw ภายใน 10 วินาที
4. THE Enhanced_Scrapers SHALL extract structured data จาก HTML ด้วย CSS selectors และ XPath โดยมี accuracy >= 95%
5. THE Enhanced_Scrapers SHALL จัดการ pagination อัตโนมัติ และดึงข้อมูลได้สูงสุด 100 items ต่อ run
6. WHEN ตรวจจับ rate limiting (HTTP 429), THE Enhanced_Scrapers SHALL backoff ด้วย exponential delay (1s, 2s, 4s, 8s)
7. THE Enhanced_Scrapers SHALL บันทึก scraper_health metrics (uptime, success_rate, avg_duration) ลงใน scraper_health table
8. WHEN scraper ล้มเหลวติดต่อกัน 3 ครั้ง, THE Enhanced_Scrapers SHALL emit event "scraper.failed" และส่ง Telegram alert

**Performance SLAs:**
- Scraper execution: <2 minutes per platform (P95)
- OpenClaw request: <60 seconds (P95)
- Fallback time: <10 seconds
- Throughput: 50 jobs/hour across all platforms

**Cost SLAs:**
- OpenClaw cost: <$0.05 per request
- Total scraping cost: <$30/month

### Requirement 3: OpenClaw Integration

**User Story:** ในฐานะระบบ ฉันต้องการเชื่อมต่อกับ OpenClaw API เพื่อ web scraping ขั้นสูง

#### Acceptance Criteria (Measurable)

1. THE OpenClaw_Integration SHALL เชื่อมต่อกับ OpenClaw API ผ่าน HTTP client โดยมี connection timeout 30 วินาที
2. THE OpenClaw_Integration SHALL จัดการ authentication token และ refresh token อัตโนมัติ โดยมี token expiry check ทุก request
3. WHEN Scraper ต้องการดึงข้อมูล, THE OpenClaw_Integration SHALL ส่ง request และรอผลลัพธ์ภายใน 60 วินาที (P95)
4. IF OpenClaw ส่ง error response (4xx, 5xx), THEN THE OpenClaw_Integration SHALL retry สูงสุด 3 ครั้งด้วย exponential backoff (1s, 2s, 4s)
5. THE OpenClaw_Integration SHALL บันทึก usage metrics (requests, tokens, cost_usd, duration_ms) ลงใน openclaw_usage table ทุก request
6. WHEN usage cost เกิน $40/month (80% of $50 budget), THE OpenClaw_Integration SHALL emit event "ai.cost_limit_reached" และส่ง Telegram alert
7. THE OpenClaw_Integration SHALL cache ผลลัพธ์ใน Redis เป็นเวลา 4 ชั่วโมง (TTL=14400) เพื่อลด API calls โดยมี cache hit rate >= 40%
8. THE OpenClaw_Integration SHALL มี circuit breaker ที่ open หลัง 3 consecutive failures และ half-open หลัง 60 วินาที

**Performance SLAs:**
- API request time: <60 seconds (P95)
- Cache lookup: <100ms
- Retry delay: 1s, 2s, 4s (exponential backoff)
- Circuit breaker recovery: 60 seconds

**Cost SLAs:**
- Cost per request: <$0.05
- Monthly budget: <$50
- Alert threshold: $40 (80%)

### Requirement 4: Network Builder Agent

**User Story:** ในฐานะผู้ใช้ ฉันต้องการให้ระบบหาและสร้างคอนเนคชั่นให้ฉัน เพื่อขยายเครือข่ายและเพิ่มโอกาสทางธุรกิจ

#### Acceptance Criteria (Measurable)

1. THE Network_Builder SHALL ค้นหา potential contacts จาก LinkedIn (via OpenClaw) ตาม target profile และพบอย่างน้อย 10 contacts ต่อสัปดาห์
2. WHEN พบ contact ใหม่, THE Network_Builder SHALL ประเมิน value_score (0-10) ภายใน 20 วินาที ตาม network strategy
3. WHEN contact มี value_score >= 7, THE Network_Builder SHALL สร้าง personalized outreach message ภายใน 30 วินาที
4. THE Network_Builder SHALL บันทึก contact ลงใน contacts table พร้อม relationship_strength เริ่มต้น (0.0-1.0)
5. THE Network_Builder SHALL คำนวณ next_followup_date โดยใช้ formula: today + (30 days / relationship_strength)
6. WHEN ถึง next_followup_date, THE Network_Builder SHALL สร้าง follow-up message และส่งเข้า approval_requests table
7. THE Network_Builder SHALL วิเคราะห์ network graph และระบุ bridge_nodes (contacts ที่เชื่อม 2+ clusters) ทุก 7 วัน
8. THE Network_Builder SHALL จัดกลุ่ม contacts เป็น network_cluster โดยใช้ community detection algorithm

**Performance SLAs:**
- Contact discovery: 10+ per week
- Value score calculation: <20 seconds
- Message generation: <30 seconds
- Network graph analysis: <5 minutes (weekly)

**Cost SLAs:**
- OpenClaw cost: <$0.05 per contact
- Total cost: <$10/month for 40 contacts/month

### Requirement 5: Email Manager Agent

**User Story:** ในฐานะผู้ใช้ ฉันต้องการให้ระบบจัดการ email ให้ฉันอัตโนมัติ เพื่อประหยัดเวลาและไม่พลาดข้อความสำคัญ

#### Acceptance Criteria (Measurable)

1. THE Email_Manager SHALL อ่าน emails จาก Gmail ทุก 5 นาที โดยใช้ Gmail API และดึงได้สูงสุด 100 emails ต่อ batch
2. THE Email_Manager SHALL จัดหมวดหมู่ emails เป็น (urgent, important, normal, spam, newsletter) ภายใน 10 วินาที ต่อ email โดยใช้ AI
3. WHEN มี urgent email (priority >= 9), THE Email_Manager SHALL แจ้งเตือนผู้ใช้ทันทีผ่าน Telegram ภายใน 30 วินาที
4. THE Email_Manager SHALL สร้าง draft replies สำหรับ common email types (acknowledgment, meeting request, question) ภายใน 30 วินาที
5. THE Email_Manager SHALL extract action items จาก emails (dates, tasks, amounts) โดยใช้ NER และบันทึกลงใน assistant_tasks table
6. THE Email_Manager SHALL track email threads และคำนวณ next_followup_date สำหรับ threads ที่ไม่มีการตอบกลับ > 3 วัน
7. THE Email_Manager SHALL บันทึก emails ลงใน email_threads และ email_messages tables โดยมี deduplication rate >= 99%
8. THE Email_Manager SHALL มี processing rate >= 95% ของ emails ที่ได้รับ (processed / total received)

**Performance SLAs:**
- Email fetch interval: 5 minutes
- Categorization time: <10 seconds per email
- Urgent alert time: <30 seconds
- Draft generation: <30 seconds
- Throughput: 100 emails per batch

**Cost SLAs:**
- Gmail API: $0 (free tier)
- AI categorization: <$0.01 per email
- Total cost: <$10/month for 1000 emails

### Requirement 6: Personal Assistant Agent

**User Story:** ในฐานะผู้ใช้ ฉันต้องการให้ระบบทำหน้าที่เป็นเลขาส่วนตัว เพื่อจัดการงาน ตารางเวลา และการสื่อสารให้ฉันอัตโนมัติ

#### Acceptance Criteria (Measurable)

1. THE Personal_Assistant SHALL จัดการ task list โดยอัตโนมัติจาก inbox, calendar และ opportunities และสร้างอย่างน้อย 5 tasks ต่อวัน
2. WHEN มี deadline ใกล้เข้ามา (<= 3 วัน), THE Personal_Assistant SHALL ส่งการแจ้งเตือนผ่าน Telegram ภายใน 1 ชั่วโมงหลังตรวจสอบ
3. WHEN มีงานที่ต้องทำในวันนั้น (due_date = today), THE Personal_Assistant SHALL สร้าง daily briefing และส่งให้ผู้ใช้ทุกเช้า 8:00 AM
4. THE Personal_Assistant SHALL ติดตามสถานะของ submissions และ drafts ที่รออนุมัติ และแจ้งเตือนถ้ารอเกิน 24 ชั่วโมง
5. WHEN มีข้อความสำคัญใน inbox (priority >= 8), THE Personal_Assistant SHALL จัดลำดับความสำคัญและแจ้งเตือนผู้ใช้ภายใน 15 นาที
6. THE Personal_Assistant SHALL ตรวจสอบ calendar conflicts (overlapping events) ทุก 1 ชั่วโมง และเสนอเวลาทางเลือก
7. WHEN ผู้ใช้ขอความช่วยเหลือผ่าน Telegram, THE Personal_Assistant SHALL ตอบกลับภายใน 5 วินาที โดยใช้ cached data หรือ AI
8. THE Personal_Assistant SHALL บันทึก audit log ของทุกการดำเนินการลงใน audit_logs table โดยมี log coverage >= 100% สำหรับ critical actions

**Performance SLAs:**
- Task creation: 5+ per day
- Deadline alert: <1 hour after check
- Daily briefing: 8:00 AM ± 5 minutes
- Urgent message alert: <15 minutes
- Telegram response: <5 seconds
- Calendar conflict check: every 1 hour

**Cost SLAs:**
- AI cost: <$0.05 per day
- Total cost: <$5/month

### Requirement 7: Approval Flow for Automation

**User Story:** ในฐานะผู้ใช้ ฉันต้องการ approval flow สำหรับการดำเนินการอัตโนมัติที่สำคัญ เพื่อความปลอดภัยและควบคุมได้

#### Acceptance Criteria (Measurable)

1. WHEN Agent ต้องการส่ง email, message หรือ application, THE Approval_Flow SHALL สร้าง approval_request และส่งไปยัง Telegram ภายใน 10 วินาที
2. THE Approval_Flow SHALL ส่ง approval request พร้อม inline keyboard (Approve/Reject/Edit) และ preview ของ action
3. WHEN ผู้ใช้กด approve, THE Approval_Flow SHALL execute action ภายใน 30 วินาที และบันทึก audit log
4. WHEN ผู้ใช้กด reject, THE Approval_Flow SHALL cancel action ภายใน 5 วินาที และบันทึกเหตุผล (ถ้ามี)
5. THE Approval_Flow SHALL มี timeout 24 ชั่วโมง สำหรับ approval requests
6. IF approval request timeout (>24 hours), THEN THE Approval_Flow SHALL auto-reject และแจ้งเตือนผู้ใช้ผ่าน Telegram
7. THE Approval_Flow SHALL รองรับ bulk approval สำหรับ multiple requests (สูงสุด 10 requests) พร้อมกัน
8. THE Approval_Flow SHALL แสดง preview ของ action (email body, message content, application details) ก่อนให้ผู้ใช้ตัดสินใจ

**Performance SLAs:**
- Request creation: <10 seconds
- Telegram delivery: <5 seconds
- Action execution: <30 seconds (after approval)
- Timeout: 24 hours
- Bulk approval: 10 requests max

**Cost SLAs:**
- Telegram API: $0 (free)
- Total cost: $0/month

### Requirement 8: Database Schema Extensions

**User Story:** ในฐานะระบบ ฉันต้องการขยาย database schema เพื่อรองรับฟีเจอร์ใหม่ทั้งหมด

#### Acceptance Criteria (Measurable)

1. THE Database SHALL มี table job_postings พร้อม 20 columns และ 4 indexes (source_hash, fit_score, status, posted_at)
2. THE Database SHALL มี table email_threads พร้อม 12 columns และ 4 indexes (category, priority, status, last_message_at)
3. THE Database SHALL มี table email_messages พร้อม 14 columns และ 2 indexes (thread_id, received_at)
4. THE Database SHALL มี table assistant_tasks พร้อม 12 columns และ 5 indexes (status, priority, due_date, related, composite)
5. THE Database SHALL มี table network_interactions พร้อม 10 columns และ 4 indexes (contact_id, type, interaction_at, composite)
6. THE Database SHALL มี table openclaw_usage พร้อม 10 columns และ 3 indexes (platform, status, created_at)
7. THE Database SHALL มี table scraper_runs พร้อม 11 columns และ 3 indexes (scraper_name, status, started_at)
8. THE Database SHALL มี table api_rate_limits พร้อม 7 columns และ 1 unique constraint (service_name, limit_type)
9. THE Database SHALL มี foreign keys สำหรับ referential integrity (email_messages.thread_id, network_interactions.contact_id, etc.)
10. THE Database SHALL มี Alembic migration scripts สำหรับทุก schema changes

**Performance SLAs:**
- Simple query: <50ms (P95)
- Join query: <200ms (P95)
- Index creation: <10 seconds
- Migration execution: <1 minute

**Data Integrity:**
- Foreign key violations: 0
- Duplicate rate: <1% (with source_hash)
- Data loss: 0 (ACID transactions)

### Requirement 9: Event-Driven Communication

**User Story:** ในฐานะระบบ ฉันต้องการใช้ EventBus สำหรับ communication ระหว่าง Agents เพื่อให้ระบบทำงานแบบ loosely coupled

#### Acceptance Criteria (Measurable)

1. THE EventBus SHALL รองรับ events ใหม่ (job.found, contact.discovered, email.urgent, task.due, scraper.failed) พร้อม event schema validation
2. WHEN Job_Hunter พบงานใหม่, THE EventBus SHALL emit event "job.found" และ deliver ไปยัง subscribers ภายใน 1 วินาที
3. WHEN Network_Builder พบ contact ใหม่, THE EventBus SHALL emit event "contact.discovered" และ deliver ภายใน 1 วินาที
4. WHEN Email_Manager พบ urgent email, THE EventBus SHALL emit event "email.urgent" และ deliver ภายใน 1 วินาที
5. THE EventBus SHALL จัดการ event queue และ retry failed handlers สูงสุด 3 ครั้งด้วย exponential backoff (1s, 2s, 4s)
6. THE EventBus SHALL บันทึก event statistics (total_events, successful_deliveries, failed_deliveries, avg_latency) ลงใน metrics table
7. THE EventBus SHALL รองรับ event filtering โดย event_type และ priority (1-10)
8. THE EventBus SHALL มี event delivery rate >= 99% (successful / total)

**Performance SLAs:**
- Event emission: <100ms
- Event delivery: <1 second
- Retry delay: 1s, 2s, 4s
- Throughput: 100 events/second

**Reliability:**
- Delivery rate: >= 99%
- Retry attempts: 3 max
- Event loss: <1%

### Requirement 10: API Endpoints for Frontend

**User Story:** ในฐานะ Frontend Developer ฉันต้องการ API endpoints สำหรับแสดงข้อมูลและควบคุมระบบผ่าน UI

#### Acceptance Criteria (Measurable)

1. THE API SHALL มี endpoint GET /api/v1/jobs พร้อม pagination (limit, offset), filtering (status, fit_score), sorting (posted_at DESC) และ response time <200ms (P95)
2. THE API SHALL มี endpoint GET /api/v1/contacts พร้อม pagination, filtering (value_score, tags), sorting (last_contacted_at DESC) และ response time <200ms (P95)
3. THE API SHALL มี endpoint GET /api/v1/emails พร้อม pagination, filtering (category, priority), sorting (last_message_at DESC) และ response time <200ms (P95)
4. THE API SHALL มี endpoint GET /api/v1/tasks พร้อม pagination, filtering (status, priority), sorting (due_date ASC) และ response time <200ms (P95)
5. THE API SHALL มี endpoint POST /api/v1/tasks สำหรับสร้าง task ใหม่ พร้อม validation และ response time <500ms (P95)
6. THE API SHALL มี endpoint GET /api/v1/metrics/dashboard สำหรับดึง dashboard metrics (jobs_found, contacts_added, emails_processed, tasks_completed) และ response time <500ms (P95)
7. THE API SHALL มี endpoint GET /api/v1/approvals พร้อม pagination และ response time <200ms (P95)
8. THE API SHALL มี endpoint POST /api/v1/approvals/:id/approve สำหรับ approve request และ response time <500ms (P95)
9. THE API SHALL มี OpenAPI/Swagger documentation สำหรับทุก endpoint
10. THE API SHALL มี error handling พร้อม HTTP status codes (400, 401, 403, 404, 500) และ error messages

**Performance SLAs:**
- GET endpoints: <200ms (P95)
- POST endpoints: <500ms (P95)
- Throughput: 100 req/sec
- Error rate: <1%

**Documentation:**
- OpenAPI spec: 100% coverage
- Example requests/responses: All endpoints


### Requirement 11: Configuration and Settings

**User Story:** ในฐานะผู้ใช้ ฉันต้องการปรับแต่ง configuration และ settings ของระบบได้ เพื่อให้ทำงานตามความต้องการของฉัน

#### Acceptance Criteria (Measurable)

1. THE System SHALL อ่าน configuration จาก environment variables และ .env file โดยมี priority: env vars > .env file > defaults
2. THE System SHALL มี settings สำหรับ OpenClaw API (OPENCLAW_API_KEY, OPENCLAW_ENDPOINT, OPENCLAW_RATE_LIMIT=100/day)
3. THE System SHALL มี settings สำหรับ job search preferences (JOB_PLATFORMS=['upwork','linkedin','fastwork'], JOB_MIN_FIT_SCORE=7.0, JOB_SALARY_MIN=50000)
4. THE System SHALL มี settings สำหรับ network building (NETWORK_TARGET_ROLES=['founder','investor','cto'], NETWORK_MIN_VALUE_SCORE=7.0)
5. THE System SHALL มี settings สำหรับ budget limits (MONTHLY_BUDGET_USD=50, OPENCLAW_BUDGET_USD=30, AI_BUDGET_USD=20)
6. THE System SHALL validate configuration ตอน startup และแจ้งเตือนถ้ามี missing required values (OPENCLAW_API_KEY, DATABASE_URL, TELEGRAM_BOT_TOKEN)
7. THE System SHALL รองรับ hot reload สำหรับ non-sensitive settings (JOB_MIN_FIT_SCORE, NETWORK_MIN_VALUE_SCORE) โดยใช้ file watcher และ graceful reload ภายใน 5 นาที โดยไม่ต้อง restart
8. THE System SHALL มี configuration validation schema (Pydantic) สำหรับ type checking และ value ranges

**Performance SLAs:**
- Config load time: <1 second
- Validation time: <100ms
- Hot reload time: <5 seconds

**Security:**
- Sensitive values: Never logged
- API keys: Encrypted at rest
- Validation: All inputs checked

### Requirement 12: Monitoring and Observability

**User Story:** ในฐานะผู้ดูแลระบบ ฉันต้องการ monitoring และ observability เพื่อติดตามสุขภาพและประสิทธิภาพของระบบ

#### Acceptance Criteria (Measurable)

1. THE System SHALL บันทึก metrics สำหรับ agent performance (execution_time, success_rate, error_rate) ลงใน metrics table ทุก 5 นาที
2. THE System SHALL บันทึก metrics สำหรับ scraper health (uptime_percentage, success_rate, items_found_per_hour) ลงใน scraper_health table ทุก 15 นาที
3. THE System SHALL บันทึก metrics สำหรับ API usage (openclaw_requests, openclaw_cost_usd, gemini_tokens, gemini_cost_usd) ลงใน openclaw_usage table ทุก request
4. THE System SHALL บันทึก metrics สำหรับ database performance (query_time_ms, connection_pool_size, active_connections) ลงใน metrics table ทุก 5 นาที
5. THE System SHALL แสดง metrics ใน dashboard (GET /api/v1/metrics/dashboard) พร้อม time series data (last 24 hours, last 7 days, last 30 days)
6. WHEN metric เกิน threshold (error_rate > 5%, cost > 80% budget, query_time > 500ms), THE System SHALL ส่ง alert ผ่าน Telegram ภายใน 1 นาที
7. THE System SHALL เก็บ audit logs สำหรับทุกการดำเนินการที่สำคัญ (job_applied, email_sent, contact_added, approval_granted) ลงใน audit_logs table
8. THE System SHALL มี health check endpoint (GET /health) ที่ตรวจสอบ database, redis, external APIs และ response time <1 second

**Performance SLAs:**
- Metrics collection: every 5 minutes
- Alert delivery: <1 minute
- Health check: <1 second
- Dashboard load: <2 seconds

**Metrics Coverage:**
- Agent metrics: 100%
- Scraper metrics: 100%
- API metrics: 100%
- Database metrics: 100%

### Requirement 13: Error Handling and Recovery

**User Story:** ในฐานะระบบ ฉันต้องการจัดการ errors และ recovery อัตโนมัติ เพื่อให้ระบบทำงานได้อย่างต่อเนื่อง

#### Acceptance Criteria (Measurable)

1. WHEN Agent ล้มเหลว, THE System SHALL บันทึก error log พร้อม stack trace, context และ timestamp ลงใน audit_logs table
2. WHEN Agent ล้มเหลว, THE System SHALL retry ด้วย exponential backoff (1s, 2s, 4s) สูงสุด 3 ครั้ง
3. IF Agent ล้มเหลวทั้ง 3 ครั้ง, THEN THE System SHALL ส่ง error notification ผ่าน Telegram พร้อม error details และ suggested actions
4. WHEN database connection ล้มเหลว, THE System SHALL reconnect อัตโนมัติทุก 5 วินาที สูงสุด 10 ครั้ง
5. WHEN external API ล้มเหลว (OpenClaw, Gmail), THE System SHALL fallback ไปใช้ cached data (ถ้ามี) หรือ skip action และ log warning
6. THE System SHALL มี circuit breaker สำหรับ external services ที่ open หลัง 3 consecutive failures และ half-open หลัง 60 วินาที
7. THE System SHALL มี graceful shutdown ที่ cleanup resources (close connections, flush logs, save state) ภายใน 30 วินาที
8. THE System SHALL มี recovery mechanism สำหรับ incomplete transactions โดยใช้ transaction rollback และ event replay

**Performance SLAs:**
- Retry delay: 1s, 2s, 4s (exponential)
- Database reconnect: every 5 seconds, max 10 attempts
- Circuit breaker recovery: 60 seconds
- Graceful shutdown: <30 seconds

**Reliability:**
- Error recovery rate: >= 80%
- Data loss: 0 (ACID transactions)
- Alert delivery: 100% for critical errors

### Requirement 14: Security and Privacy

**User Story:** ในฐานะผู้ใช้ ฉันต้องการให้ระบบปลอดภัยและปกป้องข้อมูลส่วนตัวของฉัน

#### Acceptance Criteria (Measurable)

1. THE System SHALL เข้ารหัส API keys และ credentials ใน database ด้วย AES-256 encryption
2. THE System SHALL ใช้ HTTPS สำหรับทุก external API calls (OpenClaw, Gmail, Telegram)
3. THE System SHALL validate และ sanitize ทุก user inputs โดยใช้ input validation schema (Pydantic) และ SQL parameterization
4. THE System SHALL มี rate limiting สำหรับ API endpoints (100 requests/minute per IP) โดยใช้ Redis
5. THE System SHALL ใช้ authentication token (JWT) สำหรับ API access พร้อม expiration (24 hours)
6. THE System SHALL ไม่ log sensitive data (passwords, API keys, email content, personal information) ใน logs
7. THE System SHALL มี backup mechanism สำหรับ database (daily backup) และ Obsidian vault (hourly sync)
8. THE System SHALL comply กับ GDPR โดยมี data export (GET /api/v1/export) และ data deletion (DELETE /api/v1/user) endpoints

**Performance SLAs:**
- Encryption/decryption: <10ms
- Rate limiting check: <5ms
- JWT validation: <10ms
- Backup: daily (database), hourly (vault)

**Security:**
- Encryption: AES-256
- HTTPS: 100% of external calls
- Input validation: 100% of inputs
- Rate limiting: 100 req/min per IP

### Requirement 15: Testing and Quality Assurance

**User Story:** ในฐานะ Developer ฉันต้องการ automated tests เพื่อให้มั่นใจว่าระบบทำงานถูกต้อง

#### Acceptance Criteria (Measurable)

1. THE System SHALL มี unit tests สำหรับทุก Agent และ Integration module โดยมี test coverage >= 80%
2. THE System SHALL มี integration tests สำหรับ database operations (CRUD, transactions, rollback) โดยมี test coverage >= 90%
3. THE System SHALL มี end-to-end tests สำหรับ critical workflows (job found → scored → applied, email received → categorized → replied) โดยมี test coverage >= 100%
4. THE System SHALL มี property-based tests สำหรับ data transformations (parse/format, deduplication, scoring) โดยใช้ Hypothesis
5. THE System SHALL มี mock objects สำหรับ external services (OpenClaw, Gmail, Telegram) ใน tests
6. THE System SHALL run tests อัตโนมัติใน CI/CD pipeline (GitHub Actions) ทุกครั้งที่ push code
7. THE System SHALL มี performance tests สำหรับ high-load scenarios (100 concurrent requests, 1000 emails, 50 scraper jobs)
8. THE System SHALL มี test execution time <5 minutes สำหรับ unit tests และ <15 minutes สำหรับ integration tests

**Performance SLAs:**
- Unit test execution: <5 minutes
- Integration test execution: <15 minutes
- E2E test execution: <30 minutes
- CI/CD pipeline: <20 minutes total

**Quality:**
- Test coverage: >= 80% (unit), >= 90% (integration), 100% (E2E)
- Test pass rate: 100%
- Flaky tests: 0

---

## Summary

เอกสาร requirements นี้เป็น **buildable plan** ที่:

✅ มี **MoSCoW prioritization** ชัดเจน (15 MUST, 10 SHOULD, 8 COULD, 20+ WON'T)
✅ มี **phased roadmap** 3 phases (Month 1-2, 3-4, 5-6) พร้อม dependency map ที่แก้ไขแล้ว
✅ มี **measurable acceptance criteria** พร้อม SLAs (response time, throughput, cost)
✅ มี **personas** 2 คน (Solo Founder, Builder Bee)
✅ มี **architecture decisions** (ADR-001 ถึง ADR-005) พร้อม cost calculation ที่ถูกต้อง
✅ มี **RACI matrix** สำหรับ agent responsibilities (เพิ่ม audit_logs, skill_profile, budget tracking, rate limiting)
✅ มี **NFR section** แยกชัดเจน (Performance, Scalability, Cost, Reliability, Availability, Usability, Maintainability)
✅ มี **complete database schema** (30 tables พร้อม indexes, partitioning, archival)
✅ มี **security threat model** (6 threats พร้อม mitigation)
✅ มี **4-tier fallback strategy** แบบ platform-specific (LinkedIn vs FastWork)
✅ มี **testing strategy** (Unit, Integration, E2E, Chaos, Security, PBT, Regression)
✅ มี **budget constraints** ($60-110/month Phase 1, target <$80 with optimization)
✅ มี **definition of done** (10 criteria per requirement)
✅ มี **dependency map** (Phase 1, 2, 3) พร้อม timeline ที่แก้ไขแล้ว
✅ มี **risk register** (10 risks พร้อม mitigation)
✅ มี **rollback plan** พร้อม go/no-go criteria
✅ มี **operational runbook** (7 common scenarios พร้อม solutions)
✅ มี **KPI source table** ที่ระบุ platform distribution ชัดเจน
✅ มี **Glossary** ย้ายไว้หลัง Executive Summary แล้ว

**Bottom Line:**
- **Phase 1 MVP: 15 requirements** ที่ buildable ใน 2 เดือน
- **Success criteria:** 50+ jobs/week, 10+ contacts/month, 10+ hours saved/week, <$80/month (optimized)
- **Realistic:** Solo developer, 20-30 hours/week, existing BRAVOS foundation
- **Measurable:** ทุก acceptance criterion มีตัวเลข SLAs ชัดเจน
- **Cost-aware:** OpenClaw budget recalculated ($30-50/month with caching), total $60-110/month
- **Resilient:** 4-tier fallback strategy, rollback plan, operational runbook
- **Production-ready:** Go/no-go criteria, regression tests, monitoring checklist

**Key Improvements (Feedback Round 2):**
1. ✅ Fixed OpenClaw budget math ($30-50/month with 40% cache hit rate)
2. ✅ Fixed dependency timeline (Week 1-2: DB+Job Hunter, Week 3: Network Builder, Week 4: Email Manager, Week 5: Personal Assistant, Week 6: Approval Flow)
3. ✅ Completed RACI matrix (added audit_logs, skill_profile, budget tracking, rate limiting, Notification_Rate_Limiter)
4. ✅ Clarified OpenClaw fallback strategy (platform-specific routing)
5. ✅ Added KPI source table (platform distribution breakdown)
6. ✅ Separated What vs How (requirements vs technical notes)
7. ✅ Added rollback plan (go/no-go criteria, rollback procedures)
8. ✅ Moved Glossary to top (after Executive Summary)
9. ✅ Clarified hot reload mechanism (file watcher + graceful reload within 5 minutes)
10. ✅ Added regression tests (automated on every PR, baseline benchmarks)
11. ✅ Added operational runbook (7 common scenarios with diagnosis and solutions)
12. ✅ Updated cost requirements (revised budget with optimization strategies)

**Risk Mitigation:**
- OpenClaw cost explosion → Aggressive caching (4h TTL), reduced frequency (3x/week), hard limit ($50)
- LinkedIn blocking → 4-tier fallback (OpenClaw → Cache → Alert)
- Developer burnout → Realistic timeline (20-30h/week), strict MoSCoW
- Scope creep → Phase gates, no Phase 2 until Phase 1 done

