บทนำเอกสารนี้อธิบายการออกแบบระบบที่จาก โดยเพิ่มความสามารถนการางาอัตโนมัติจัดการ miสร้างtwokและำหน้าทเป็นเลขาสนตัว

**เป้าหมาหลัก:**
- หางาน freelance/full-time อัตโนมัติาก 5-7 platforms (50+ jobs/week)
- จ email สร้ง draft replies 
-หาและสร้างความสัมันธ์กับ contacts ทีีคุณค่า(10+contcts/month)
- ทำหน้าที่เป็น prsoal assisant (daily briefing, takmanagement)
- ประยัดเวลา 10+ ชั่วโง/สัปดาห์
- ควบคุมคาใช้จ่าย<$80/เดือน

**DesignPrincils (จาก BRAVOS Master Desig Pn):**
1.**Decsios Firs** - ให้ us ตัดสินใจสำคัญเสมอ ไม่ auto-execute ทุกอย่าง
2. **Automon Secd** - automateงานซ้ๆ ลงจาก user approve pattern
3. **Explain Every Action** - อธิายทุก action ที่ agent ทำ พร้อมเหตุผล
4. **One-ClickConfidenc** - ทำให้ue prove/reject ได้ง่ายใน 1 clck
5. **Budet Always Visible** -แสดงค่าใชจ่าย real-time ตลอดเวลา
6. **Trust by Layers** - แบ่ง trust levels (Tier 0-3) ตามความเี่ย

---

## 1. High-Level Architecture

### 1.1 System Overview]
        Devpost[Devpost<br/>Browser Automation<br/>Email Access<br/>Notifications]
        Redis[Redis Cache<br/>4h TTL<br/>หางาน + scoring<br/>จัดหมวดหมู่ + draft<br/>5-7 platforms<br/>หา contacts + outreach<br/>briefing + tasks<br/>scoring + decisions<br/>learn patterns<br/>async communication<br/>+8tbls<br/>Jobs/Contacts/Emails<br/>Approvals/AlertsDevpost --> Scrapers
    Redis
    Redis --> 
    **KyDsigDisions:**1.**OpenClawสำหรบ-otSts**LkdI,Upwork, Fvrrต้องใช้browserautati2.**Rdch (4hTTL)**-ลดOpClwossจาก$42-105/mth→$3050/monh3.**EvBusสำหรับCommuncao**-looslycoupld,ayc,rty-be4.**4-TiFalback**OpClaw→Die Srp→ah→lrU5.**ApprovalFlowผ่านTeeam**ilikeybodสำหรับqick prve/rejec


### 1.2 3-Layer Agent Architecture

ระบบใช้สถาปัตยกรรม 3 ชั้นที่มีอยู่แล้วใน BRAVOS:

```mermaid
graph TB
    subgraph "Learning Layer - Existing"
        LE[Learning Engine<br/>เรียนรู้ patterns]
        CE[Compound Engine<br/>optimize strategies]
        FA[Failure Analysis<br/>วิเคราะห์ failures]
        PC[Playbook Capture<br/>บันทึก playbooks]
    end

    subgraph "Executive Layer"
        DE[Decision Engine<br/>Existing]
        SA[Strategy Agent<br/>Existing]
        BA[Briefer Agent<br/>Existing]
        PA[Personal Assistant<br/>NEW]
        NB[Network Builder<br/>NEW]
    end

    subgraph "Tactical Layer"
        SC[Scorer Agent<br/>Existing]
        DR[Drafter Agent<br/>Existing]
        JH[Job Hunter<br/>NEW]
        EM[Email Manager<br/>NEW]
        ES[Enhanced Scrapers<br/>NEW]
    end

    subgraph "Foundation"
        EB[EventBus]
        DB[(Database)]
        RC[(Redis)]
    end

    LE --> DE
    CE --> DE
    FA --> LE
    PC --> LE

    DE --> PA
    DE --> NB
    SA --> PA
    BA --> PA

    PA --> JH
    PA --> EM
    PA --> NB
    NB --> ES
    JH --> ES

    JH --> EB
    EM --> EB
    NB --> EB
    PA --> EB
    DE --> EB

    EB --> DB
    EB --> RC
```

**Agent Responsibilities Matrix:**

| Layer | Agent | Responsibilities | Input | Output | Dependencies |
|-------|-------|-----------------|-------|--------|--------------|
| **Learning** | Learning Engine | เรียนรู้จาก outcomes, ปรับ weights | outcomes, patterns | updated weights | Existing |
| **Learning** | Compound Engine | รวม strategies, optimize | multiple strategies | optimized strategy | Existing |
| **Executive** | Decision Engine | ตัดสินใจ actions, scoring | opportunities, context | decisions, scores | Existing |
| **Executive** | Personal Assistant | Daily briefing, task mgmt, notifications | tasks, emails, jobs | briefings, alerts | NEW - depends on Email Manager |
| **Executive** | Network Builder | หา contacts, outreach, tracking | LinkedIn profiles | contacts, messages | NEW - independent |
| **Tactical** | Job Hunter | หางาน, scoring, deduplication | scraped jobs | scored jobs | NEW - depends on Scrapers |
| **Tactical** | Email Manager | อ่าน/จัดหมวดหมู่/ตอบ emails | Gmail messages | categorized emails, drafts | NEW - independent |
| **Tactical** | Enhanced Scrapers | ดึงข้อมูลจาก 5-7 platforms | platform URLs | raw data | NEW - depends on OpenClaw |

### 1.3 Integration Points กับ BRAVOS

**Existing Components ที่ใช้:**

| Component | Usage | Modifications |
|-----------|-------|---------------|
| EventBus | Agent communication | เพิ่ม 5 event types ใหม่ |
| Database | Data persistence | เพิ่ม 8 tables ใหม่ |
| Telegram Bot | User interface | ขยาย handlers สำหรับ approvals |
| BaseAgent | Agent foundation | Inherit สำหรับ agents ใหม่ |
| Decision Engine | Scoring & decisions | ใช้สำหรับ fit_score, value_score |
| Learning Engine | Pattern learning | เรียนรู้จาก job outcomes |
| Celery | Background tasks | เพิ่ม tasks สำหรับ scrapers |
| Alembic | Database migrations | เพิ่ม migrations สำหรับ tables ใหม่ |

**New Components:**

| Component | Purpose | Technology | Cost |
|-----------|---------|------------|------|
| OpenClaw Integration | Web scraping ขั้นสูง | OpenClaw API | $30-50/month |
| Gmail Integration | Email management | Gmail OAuth API | $0 (free tier) |
| Redis Cache | Cache scraping results | Upstash Redis | $0-10/month |
| Job Hunter Agent | หางานอัตโนมัติ | Python + SQLAlchemy | $0 |
| Network Builder Agent | สร้าง network | Python + SQLAlchemy | $0 |
| Email Manager Agent | จัดการ email | Python + Gmail API | $0 |
| Personal Assistant Agent | เลขาส่วนตัว | Python + Telegram | $0 |
| Enhanced Scrapers | 5-7 platform scrapers | Python + BeautifulSoup | $0 |

### 1.4 Data Flow Diagrams

#### 1.4.1 Job Discovery Flow

```mermaid
sequenceDiagram
    participant Scheduler as Celery Scheduler
    participant Scraper as Enhanced Scraper
    participant OpenClaw as OpenClaw API
    participant Redis as Redis Cache
    participant JobHunter as Job Hunter Agent
    participant DecisionEngine as Decision Engine
    participant EventBus as EventBus
    participant Database as PostgreSQL
    participant Assistant as Personal Assistant
    participant Telegram as Telegram Bot
    participant User as User

    Note over Scheduler: Every 6 hours
    Scheduler->>Scraper: Trigger LinkedIn scrape
    Scraper->>Redis: Check cache (key: linkedin:jobs:page1)
    alt Cache Hit
        Redis-->>Scraper: Cached HTML (4h old)
    else Cache Miss
        Scraper->>OpenClaw: POST /scrape {url, selectors}
        OpenClaw-->>Scraper: HTML content
        Scraper->>Redis: Cache HTML (TTL=4h)
    end
    
    Scraper->>JobHunter: Raw job data (10 jobs)
    loop For each job
        JobHunter->>Database: Check duplicate (source_hash)
        alt Not duplicate
            JobHunter->>DecisionEngine: Calculate fit_score
            DecisionEngine-->>JobHunter: score = 8.5
            JobHunter->>Database: INSERT job_posting
            alt score >= 7.0
                JobHunter->>EventBus: Emit "job.found" event
                EventBus->>Assistant: Handle "job.found"
                Assistant->>Telegram: Send notification
                Telegram-->>User: "🎯 Found high-value job!"
            end
        end
    end
    
    User->>Telegram: /approve job_123
    Telegram->>Assistant: Approval granted
    Assistant->>EventBus: Emit "job.apply"
    EventBus->>Database: CREATE submission
    Database-->>User: Application submitted
```

#### 1.4.2 Email Management Flow

```mermaid
sequenceDiagram
    participant Scheduler as Celery Scheduler
    participant EmailMgr as Email Manager
    participant Gmail as Gmail API
    participant Gemini as Gemini AI
    participant Database as PostgreSQL
    participant EventBus as EventBus
    participant Assistant as Personal Assistant
    participant Telegram as Telegram Bot
    participant User as User

    Note over Scheduler: Every 5 minutes
    Scheduler->>EmailMgr: Check new emails
    EmailMgr->>Gmail: GET /messages (maxResults=100)
    Gmail-->>EmailMgr: 5 new emails
    
    loop For each email
        EmailMgr->>Gemini: Categorize email
        Gemini-->>EmailMgr: category="urgent", priority=9
        EmailMgr->>Database: INSERT email_thread, email_message
        
        alt priority >= 9 (urgent)
            EmailMgr->>EventBus: Emit "email.urgent"
            EventBus->>Assistant: Handle "email.urgent"
            Assistant->>Telegram: Send alert
            Telegram-->>User: "🚨 Urgent email from client!"
        end
        
        EmailMgr->>Gemini: Generate draft reply
        Gemini-->>EmailMgr: draft_text
        EmailMgr->>Database: INSERT content_draft
        EmailMgr->>EventBus: Emit "draft.created"
    end
    
    User->>Telegram: /approve draft_456
    Telegram->>Assistant: Approval granted
    Assistant->>Gmail: POST /send {message}
    Gmail-->>User: Email sent
```

#### 1.4.3 Network Building Flow

```mermaid
sequenceDiagram
    participant Scheduler as Celery Scheduler
    participant NetBuilder as Network Builder
    participant OpenClaw as OpenClaw API
    participant DecisionEngine as Decision Engine
    participant Gemini as Gemini AI
    participant Database as PostgreSQL
    participant EventBus as EventBus
    participant Assistant as Personal Assistant
    participant Telegram as Telegram Bot
    participant User as User

    Note over Scheduler: Daily at 10 AM
    Scheduler->>NetBuilder: Search for contacts
    NetBuilder->>OpenClaw: Scrape LinkedIn (target_role="founder")
    OpenClaw-->>NetBuilder: 10 profiles
    
    loop For each profile
        NetBuilder->>DecisionEngine: Calculate value_score
        DecisionEngine-->>NetBuilder: score = 8.0
        NetBuilder->>Database: INSERT contact
        
        alt score >= 7.0
            NetBuilder->>Gemini: Generate personalized message
            Gemini-->>NetBuilder: outreach_message
            NetBuilder->>Database: INSERT content_draft
            NetBuilder->>EventBus: Emit "contact.discovered"
            EventBus->>Assistant: Handle "contact.discovered"
            Assistant->>Telegram: Send approval request
            Telegram-->>User: "👤 Found valuable contact: John Doe (Founder @ Startup)"
        end
    end
    
    User->>Telegram: /approve contact_789
    Telegram->>Assistant: Approval granted
    Assistant->>OpenClaw: Send LinkedIn message
    OpenClaw-->>Database: Log interaction
```



---

## 2. Component Design

### 2.1 Job Hunter Agent (Tactical Layer)

**Purpose:** หางาน freelance/full-time อัตโนมัติจาก 5-7 platforms และประเมินความเหมาะสม

**Class Design:**

```python
from app.agents.base import BaseAgent
from app.core.event_bus import EventBus
from app.models.job_posting import JobPosting
from app.core.scoring import ScoringEngine
import hashlib
from typing import List, Dict

class JobHunterAgent(BaseAgent):
    """
    Agent ที่หางานอัตโนมัติและประเมินความเหมาะสม
    
    Responsibilities:
    - รับ raw job data จาก scrapers
    - คำนวณ fit_score (0-10) ตาม skill_profile
    - Deduplication ด้วย source_hash
    - Emit "job.found" event สำหรับงานที่ score >= 7
    """
    
    def __init__(self, event_bus: EventBus, scoring_engine: ScoringEngine):
        super().__init__(name="job_hunter", event_bus=event_bus)
        self.scoring_engine = scoring_engine
        self.min_fit_score = 7.0  # configurable
        
    async def execute(self, jobs: List[Dict]) -> List[JobPosting]:
        """
        Process raw job data from scrapers
        
        Args:
            jobs: List of raw job dicts from scrapers
            
        Returns:
            List of JobPosting objects that were saved
        """
        saved_jobs = []
        
        for job_data in jobs:
            # 1. Calculate source_hash for deduplication
            source_hash = self._calculate_hash(
                job_data['source'], 
                job_data['source_id']
            )
            
            # 2. Check if already exists
            existing = await JobPosting.get_by_hash(source_hash)
            if existing:
                continue  # Skip duplicate
                
            # 3. Calculate fit_score
            fit_score = await self.scoring_engine.calculate_fit_score(
                job_data,
                user_skills=self.get_user_skills(),
                user_identity=self.get_user_identity()
            )
            
            # 4. Create JobPosting object
            job = JobPosting(
                source=job_data['source'],
                source_id=job_data['source_id'],
                source_url=job_data['url'],
                source_hash=source_hash,
                title=job_data['title'],
                description=job_data['description'],
                company=job_data.get('company'),
                location=job_data.get('location'),
                job_type=job_data.get('job_type'),
                salary_min=job_data.get('salary_min'),
                salary_max=job_data.get('salary_max'),
                skills=job_data.get('skills', []),
                fit_score=fit_score,
                action_priority=self._determine_priority(fit_score),
                status='new'
            )
            
            # 5. Save to database
            await job.save()
            saved_jobs.append(job)
            
            # 6. Emit event if high score
            if fit_score >= self.min_fit_score:
                await self.event_bus.emit('job.found', {
                    'job_id': str(job.id),
                    'title': job.title,
                    'fit_score': fit_score,
                    'source': job.source,
                    'url': job.source_url
                })
                
        return saved_jobs
    
    def _calculate_hash(self, source: str, source_id: str) -> str:
        """Calculate SHA256 hash for deduplication"""
        content = f"{source}:{source_id}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _determine_priority(self, fit_score: float) -> str:
        """Determine action priority based on fit_score"""
        if fit_score >= 8.0:
            return 'do_now'
        elif fit_score >= 6.0:
            return 'consider'
        else:
            return 'skip'
```

**Configuration:**

```python
# config.py
class JobHunterConfig:
    MIN_FIT_SCORE = 7.0  # Minimum score to notify user
    PLATFORMS = ['upwork', 'linkedin', 'fastwork', 'fiverr', 'devpost']
    SCRAPE_INTERVAL_HOURS = 6  # How often to scrape
    MAX_JOBS_PER_RUN = 100  # Limit per scraper run
    SALARY_MIN_USD = 50000  # Minimum salary for full-time jobs
```

**Scoring Algorithm:**

```python
class ScoringEngine:
    """
    Calculate fit_score for jobs based on user profile
    
    Formula:
    fit_score = (skill_match * 0.4) + (salary_match * 0.3) + 
                (location_match * 0.2) + (urgency * 0.1)
    
    Where:
    - skill_match: % of required skills user has (0-10)
    - salary_match: How close to desired salary (0-10)
    - location_match: Remote=10, Preferred location=8, Other=5
    - urgency: Based on deadline (urgent=10, normal=5)
    """
    
    async def calculate_fit_score(
        self, 
        job: Dict, 
        user_skills: List[str],
        user_identity: Dict
    ) -> float:
        # 1. Skill matching
        required_skills = set(job.get('skills', []))
        user_skill_set = set(user_skills)
        skill_overlap = len(required_skills & user_skill_set)
        skill_match = (skill_overlap / len(required_skills) * 10) if required_skills else 5.0
        
        # 2. Salary matching
        desired_salary = user_identity.get('desired_salary', 50000)
        job_salary = job.get('salary_max', job.get('salary_min', 0))
        salary_ratio = job_salary / desired_salary if desired_salary > 0 else 0
        salary_match = min(salary_ratio * 10, 10.0)
        
        # 3. Location matching
        location_match = 10.0 if job.get('location') == 'Remote' else 5.0
        
        # 4. Urgency
        deadline_days = self._days_until_deadline(job.get('deadline'))
        urgency = 10.0 if deadline_days <= 3 else 5.0
        
        # Weighted sum
        fit_score = (
            skill_match * 0.4 +
            salary_match * 0.3 +
            location_match * 0.2 +
            urgency * 0.1
        )
        
        return round(fit_score, 2)
```

**Database Model:**

```python
# app/models/job_posting.py
from sqlalchemy import Column, String, Text, DECIMAL, TIMESTAMP, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

class JobPosting(Base):
    __tablename__ = 'job_postings'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(100), nullable=False)  # 'upwork', 'linkedin'
    source_id = Column(String(255))
    source_url = Column(Text, nullable=False)
    source_hash = Column(String(64), unique=True, index=True)  # SHA256
    
    title = Column(String(500), nullable=False)
    description = Column(Text)
    company = Column(String(255))
    location = Column(String(255))
    job_type = Column(String(50))  # 'freelance', 'full-time'
    
    salary_min = Column(DECIMAL(12, 2))
    salary_max = Column(DECIMAL(12, 2))
    salary_currency = Column(String(3), default='USD')
    
    skills = Column(JSONB)  # ['Python', 'FastAPI']
    requirements = Column(Text)
    posted_at = Column(TIMESTAMP)
    deadline = Column(TIMESTAMP)
    
    fit_score = Column(DECIMAL(3, 2))  # 0.00-10.00
    action_priority = Column(String(20))  # 'do_now', 'consider', 'skip'
    status = Column(String(50), default='new')  # 'new', 'scored', 'applied'
    
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_job_source_hash', 'source_hash'),
        Index('idx_job_fit_score', 'fit_score', postgresql_ops={'fit_score': 'DESC'}),
        Index('idx_job_status', 'status'),
        Index('idx_job_posted', 'posted_at', postgresql_ops={'posted_at': 'DESC'}),
    )
```

**Event Schema:**

```python
# Event: job.found
{
    "event_type": "job.found",
    "timestamp": "2024-01-15T10:30:00Z",
    "data": {
        "job_id": "uuid-here",
        "title": "Senior Python Developer",
        "fit_score": 8.5,
        "source": "linkedin",
        "url": "https://linkedin.com/jobs/123",
        "salary_max": 120000,
        "skills": ["Python", "FastAPI", "PostgreSQL"]
    }
}
```



### 2.2 Network Builder Agent (Executive Layer)

**Purpose:** หาและสร้างความสัมพันธ์กับ contacts ที่มีคุณค่า

**Class Design:**

```python
from app.agents.base import BaseAgent
from app.models.contact import Contact
from app.models.network_interaction import NetworkInteraction
from typing import List, Dict

class NetworkBuilderAgent(BaseAgent):
    """
    Agent ที่หาและสร้าง network อัตโนมัติ
    
    Responsibilities:
    - ค้นหา potential contacts จาก LinkedIn
    - ประเมิน value_score (0-10)
    - สร้าง personalized outreach messages
    - Track interactions และ relationship_strength
    - ระบุ bridge_nodes และ network_clusters
    """
    
    def __init__(self, event_bus: EventBus, openclaw_client, gemini_client):
        super().__init__(name="network_builder", event_bus=event_bus)
        self.openclaw = openclaw_client
        self.gemini = gemini_client
        self.min_value_score = 7.0
        
    async def search_contacts(self, target_profile: Dict) -> List[Contact]:
        """
        Search for contacts matching target profile
        
        Args:
            target_profile: {
                'roles': ['founder', 'cto', 'investor'],
                'industries': ['saas', 'fintech'],
                'locations': ['San Francisco', 'Remote']
            }
        """
        # 1. Build LinkedIn search query
        query = self._build_search_query(target_profile)
        
        # 2. Scrape LinkedIn via OpenClaw
        profiles = await self.openclaw.scrape_linkedin_search(query, max_results=20)
        
        # 3. Process each profile
        contacts = []
        for profile_data in profiles:
            # Calculate value_score
            value_score = await self._calculate_value_score(profile_data)
            
            if value_score >= self.min_value_score:
                # Create contact
                contact = Contact(
                    name=profile_data['name'],
                    email=profile_data.get('email'),
                    linkedin_url=profile_data['url'],
                    title=profile_data['title'],
                    company=profile_data['company'],
                    location=profile_data.get('location'),
                    value_score=value_score,
                    relationship_strength=0.0,  # Initial
                    tags=self._extract_tags(profile_data),
                    status='discovered'
                )
                
                await contact.save()
                contacts.append(contact)
                
                # Emit event
                await self.event_bus.emit('contact.discovered', {
                    'contact_id': str(contact.id),
                    'name': contact.name,
                    'value_score': value_score
                })
                
        return contacts
    
    async def generate_outreach(self, contact: Contact) -> str:
        """Generate personalized outreach message"""
        prompt = f"""
        Generate a personalized LinkedIn connection request for:
        
        Name: {contact.name}
        Title: {contact.title}
        Company: {contact.company}
        
        My background: {self.get_user_identity()}
        
        Requirements:
        - Keep it under 300 characters
        - Be genuine and specific
        - Mention a common interest or connection
        - Don't be salesy
        """
        
        message = await self.gemini.generate(prompt)
        return message
    
    async def _calculate_value_score(self, profile: Dict) -> float:
        """
        Calculate value_score (0-10) based on:
        - Role relevance (0-10)
        - Company stage (0-10)
        - Mutual connections (0-10)
        - Activity level (0-10)
        """
        role_score = self._score_role(profile['title'])
        company_score = self._score_company(profile['company'])
        mutual_score = len(profile.get('mutual_connections', [])) / 10 * 10
        activity_score = self._score_activity(profile.get('recent_posts', []))
        
        value_score = (
            role_score * 0.4 +
            company_score * 0.3 +
            mutual_score * 0.2 +
            activity_score * 0.1
        )
        
        return round(value_score, 2)
    
    async def analyze_network_graph(self) -> Dict:
        """
        Analyze network graph to find:
        - Bridge nodes (connect 2+ clusters)
        - Network clusters (communities)
        - Weak ties (low relationship_strength)
        """
        contacts = await Contact.get_all()
        edges = await NetworkInteraction.get_all()
        
        # Build graph
        graph = self._build_graph(contacts, edges)
        
        # Find communities (clusters)
        clusters = self._detect_communities(graph)
        
        # Find bridge nodes
        bridges = self._find_bridge_nodes(graph, clusters)
        
        # Find weak ties
        weak_ties = [c for c in contacts if c.relationship_strength < 0.3]
        
        return {
            'clusters': clusters,
            'bridge_nodes': bridges,
            'weak_ties': weak_ties,
            'total_contacts': len(contacts)
        }
```

**Database Models:**

```python
# app/models/contact.py (existing, extended)
class Contact(Base):
    __tablename__ = 'contacts'
    
    # ... existing fields ...
    
    # New fields
    value_score = Column(DECIMAL(3, 2))  # 0.00-10.00
    relationship_strength = Column(DECIMAL(3, 2))  # 0.00-1.00
    last_contacted_at = Column(TIMESTAMP)
    next_followup_date = Column(TIMESTAMP)
    network_cluster_id = Column(Integer)  # Which cluster they belong to
    is_bridge_node = Column(Boolean, default=False)

# app/models/network_interaction.py (new)
class NetworkInteraction(Base):
    __tablename__ = 'network_interactions'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey('contacts.id'))
    
    interaction_type = Column(String(50))  # 'email', 'linkedin_message', 'meeting'
    direction = Column(String(20))  # 'outbound', 'inbound'
    channel = Column(String(50))  # 'email', 'linkedin', 'twitter'
    
    subject = Column(String(500))
    content = Column(Text)
    sentiment = Column(String(20))  # 'positive', 'neutral', 'negative'
    outcome = Column(String(100))  # 'replied', 'no_response', 'meeting_scheduled'
    
    interaction_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, default=func.now())
    
    __table_args__ = (
        Index('idx_interaction_contact', 'contact_id'),
        Index('idx_interaction_type', 'interaction_type'),
        Index('idx_interaction_at', 'interaction_at', postgresql_ops={'interaction_at': 'DESC'}),
        Index('idx_interaction_contact_at', 'contact_id', 'interaction_at'),
    )
```

**Network Graph Algorithm:**

```python
import networkx as nx
from typing import List, Set

class NetworkGraphAnalyzer:
    """Analyze network graph for insights"""
    
    def _build_graph(self, contacts: List[Contact], edges: List[NetworkInteraction]) -> nx.Graph:
        """Build NetworkX graph from contacts and interactions"""
        G = nx.Graph()
        
        # Add nodes
        for contact in contacts:
            G.add_node(contact.id, **contact.to_dict())
        
        # Add edges (interactions)
        for interaction in edges:
            if interaction.direction == 'outbound':
                G.add_edge(
                    'user',  # User node
                    interaction.contact_id,
                    weight=interaction.sentiment_score
                )
        
        return G
    
    def _detect_communities(self, G: nx.Graph) -> List[Set]:
        """Detect network clusters using Louvain algorithm"""
        from community import community_louvain
        
        partition = community_louvain.best_partition(G)
        
        # Group nodes by cluster
        clusters = {}
        for node, cluster_id in partition.items():
            if cluster_id not in clusters:
                clusters[cluster_id] = set()
            clusters[cluster_id].add(node)
        
        return list(clusters.values())
    
    def _find_bridge_nodes(self, G: nx.Graph, clusters: List[Set]) -> List[str]:
        """Find nodes that connect 2+ clusters"""
        bridges = []
        
        for node in G.nodes():
            # Count how many clusters this node connects to
            connected_clusters = set()
            for neighbor in G.neighbors(node):
                for i, cluster in enumerate(clusters):
                    if neighbor in cluster:
                        connected_clusters.add(i)
            
            if len(connected_clusters) >= 2:
                bridges.append(node)
        
        return bridges
```



### 2.3 Email Manager Agent (Tactical Layer)

**Purpose:** จัดการ email อัตโนมัติ - อ่าน จัดหมวดหมู่ สร้าง draft replies

**Class Design:**

```python
from app.agents.base import BaseAgent
from app.models.email_thread import EmailThread
from app.models.email_message import EmailMessage
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import re

class EmailManagerAgent(BaseAgent):
    """
    Agent ที่จัดการ email อัตโนมัติ
    
    Responsibilities:
    - Fetch emails จาก Gmail API ทุก 5 นาที
    - จัดหมวดหมู่ emails (urgent, important, normal, spam)
    - Extract action items (dates, tasks, amounts)
    - สร้าง draft replies สำหรับ common types
    - Track email threads และ follow-ups
    """
    
    def __init__(self, event_bus: EventBus, gmail_creds: Credentials, gemini_client):
        super().__init__(name="email_manager", event_bus=event_bus)
        self.gmail = build('gmail', 'v1', credentials=gmail_creds)
        self.gemini = gemini_client
        
    async def fetch_new_emails(self, max_results: int = 100) -> List[EmailMessage]:
        """Fetch new unread emails from Gmail"""
        # 1. Get unread messages
        results = self.gmail.users().messages().list(
            userId='me',
            q='is:unread',
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        
        # 2. Process each message
        email_messages = []
        for msg in messages:
            # Get full message
            full_msg = self.gmail.users().messages().get(
                userId='me',
                id=msg['id'],
                format='full'
            ).execute()
            
            # Parse message
            email_msg = await self._parse_email(full_msg)
            email_messages.append(email_msg)
            
        return email_messages
    
    async def categorize_email(self, email: EmailMessage) -> Dict:
        """
        Categorize email using AI
        
        Returns:
            {
                'category': 'urgent' | 'important' | 'normal' | 'spam' | 'newsletter',
                'priority': 1-10,
                'confidence': 0.0-1.0
            }
        """
        prompt = f"""
        Categorize this email:
        
        From: {email.from_email}
        Subject: {email.subject}
        Body: {email.body_text[:500]}
        
        Categories:
        - urgent: Requires immediate action (client issue, deadline, payment)
        - important: Requires action within 24h (meeting request, proposal)
        - normal: Can wait (general inquiry, update)
        - spam: Unsolicited marketing
        - newsletter: Subscribed content
        
        Return JSON: {{"category": "...", "priority": 1-10, "reason": "..."}}
        """
        
        response = await self.gemini.generate(prompt, response_format='json')
        return response
    
    async def extract_action_items(self, email: EmailMessage) -> List[Dict]:
        """
        Extract action items using NER
        
        Returns:
            [
                {'type': 'meeting', 'date': '2024-01-20', 'time': '14:00'},
                {'type': 'deadline', 'date': '2024-01-25', 'task': 'Submit proposal'},
                {'type': 'payment', 'amount': 5000, 'currency': 'USD', 'due': '2024-01-30'}
            ]
        """
        # Use regex + AI for extraction
        text = email.body_text
        
        # Extract dates
        dates = self._extract_dates(text)
        
        # Extract amounts
        amounts = self._extract_amounts(text)
        
        # Use AI to structure action items
        prompt = f"""
        Extract action items from this email:
        
        {text}
        
        Dates found: {dates}
        Amounts found: {amounts}
        
        Return JSON array of action items with type, description, due_date.
        """
        
        action_items = await self.gemini.generate(prompt, response_format='json')
        return action_items
    
    async def generate_draft_reply(self, email: EmailMessage, category: str) -> str:
        """Generate draft reply based on email category"""
        
        if category == 'urgent':
            template = "acknowledgment"  # Quick acknowledgment
        elif category == 'important':
            template = "detailed"  # Detailed response
        else:
            template = "brief"  # Brief response
        
        prompt = f"""
        Generate a {template} reply to this email:
        
        From: {email.from_email}
        Subject: {email.subject}
        Body: {email.body_text}
        
        My context: {self.get_user_identity()}
        
        Requirements:
        - Professional tone
        - Address all questions
        - Suggest next steps
        - Keep it concise
        """
        
        draft = await self.gemini.generate(prompt)
        return draft
    
    def _extract_dates(self, text: str) -> List[str]:
        """Extract dates using regex"""
        patterns = [
            r'\d{4}-\d{2}-\d{2}',  # 2024-01-20
            r'\d{1,2}/\d{1,2}/\d{4}',  # 1/20/2024
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}'  # Jan 20, 2024
        ]
        
        dates = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(matches)
        
        return dates
    
    def _extract_amounts(self, text: str) -> List[Dict]:
        """Extract monetary amounts"""
        pattern = r'(\$|USD|THB|€|£)\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)'
        matches = re.findall(pattern, text)
        
        amounts = []
        for currency, amount in matches:
            amounts.append({
                'currency': currency,
                'amount': float(amount.replace(',', ''))
            })
        
        return amounts
```

**Database Models:**

```python
# app/models/email_thread.py
class EmailThread(Base):
    __tablename__ = 'email_threads'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(String(255), unique=True)  # Gmail thread ID
    
    subject = Column(String(500))
    participants = Column(JSONB)  # [{'email': 'x@y.com', 'name': 'X'}]
    
    category = Column(String(50))  # 'urgent', 'important', 'normal', 'spam'
    priority = Column(Integer, default=5)  # 1-10
    
    last_message_at = Column(TIMESTAMP)
    unread_count = Column(Integer, default=0)
    has_attachments = Column(Boolean, default=False)
    
    action_items = Column(JSONB)  # [{'task': 'Reply', 'due': '2024-01-01'}]
    status = Column(String(50), default='unread')  # 'unread', 'read', 'replied'
    
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now())
    
    __table_args__ = (
        Index('idx_email_category', 'category'),
        Index('idx_email_priority', 'priority', postgresql_ops={'priority': 'DESC'}),
        Index('idx_email_status', 'status'),
        Index('idx_email_last_message', 'last_message_at', postgresql_ops={'last_message_at': 'DESC'}),
    )

# app/models/email_message.py
class EmailMessage(Base):
    __tablename__ = 'email_messages'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('email_threads.id'))
    message_id = Column(String(255), unique=True)  # Gmail message ID
    
    from_email = Column(String(255))
    from_name = Column(String(255))
    to_emails = Column(JSONB)
    cc_emails = Column(JSONB)
    
    subject = Column(String(500))
    body_text = Column(Text)
    body_html = Column(Text)
    
    received_at = Column(TIMESTAMP)
    is_from_me = Column(Boolean, default=False)
    
    sentiment = Column(String(20))  # 'positive', 'neutral', 'negative'
    extracted_data = Column(JSONB)  # {'dates': [], 'amounts': [], 'links': []}
    
    created_at = Column(TIMESTAMP, default=func.now())
    
    __table_args__ = (
        Index('idx_email_msg_thread', 'thread_id'),
        Index('idx_email_msg_received', 'received_at', postgresql_ops={'received_at': 'DESC'}),
    )
```



### 2.4 Personal Assistant Agent (Executive Layer)

**Purpose:** ทำหน้าที่เป็นเลขาส่วนตัว - daily briefing, task management, notifications

**Class Design:**

```python
from app.agents.base import BaseAgent
from app.models.assistant_task import AssistantTask
from datetime import datetime, timedelta
from typing import List, Dict

class PersonalAssistantAgent(BaseAgent):
    """
    Agent ที่ทำหน้าที่เป็นเลขาส่วนตัว
    
    Responsibilities:
    - สร้าง daily briefing ทุกเช้า 8:00 AM
    - จัดการ task list อัตโนมัติ
    - ส่ง notifications สำหรับ deadlines
    - ติดตาม approvals ที่รออยู่
    - Monitor costs และ budget
    - Handle Telegram commands
    """
    
    def __init__(self, event_bus: EventBus, telegram_bot):
        super().__init__(name="personal_assistant", event_bus=event_bus)
        self.telegram = telegram_bot
        self.notification_rate_limit = 10  # per hour
        self.notification_count = 0
        self.last_reset = datetime.now()
        
    async def generate_daily_briefing(self) -> str:
        """
        Generate daily briefing at 8:00 AM
        
        Includes:
        - Top 10 new jobs (sorted by fit_score)
        - Top 5 new contacts (sorted by value_score)
        - Urgent emails (priority >= 9)
        - Tasks due today
        - Pending approvals
        - Yesterday's metrics
        - Budget status
        """
        # 1. Get new jobs
        jobs = await JobPosting.get_recent(limit=10, min_score=7.0)
        
        # 2. Get new contacts
        contacts = await Contact.get_recent(limit=5, min_score=7.0)
        
        # 3. Get urgent emails
        emails = await EmailThread.get_urgent(priority_min=9)
        
        # 4. Get tasks due today
        tasks = await AssistantTask.get_due_today()
        
        # 5. Get pending approvals
        approvals = await ApprovalRequest.get_pending()
        
        # 6. Get yesterday's metrics
        metrics = await self._get_yesterday_metrics()
        
        # 7. Get budget status
        budget = await self._get_budget_status()
        
        # 8. Format briefing
        briefing = f"""
🌅 **Daily Briefing - {datetime.now().strftime('%A, %B %d, %Y')}**

📊 **Yesterday's Summary:**
- Jobs found: {metrics['jobs_found']}
- Contacts added: {metrics['contacts_added']}
- Emails processed: {metrics['emails_processed']}
- Tasks completed: {metrics['tasks_completed']}

🎯 **New Opportunities ({len(jobs)}):**
{self._format_jobs(jobs)}

👥 **New Contacts ({len(contacts)}):**
{self._format_contacts(contacts)}

📧 **Urgent Emails ({len(emails)}):**
{self._format_emails(emails)}

✅ **Tasks Due Today ({len(tasks)}):**
{self._format_tasks(tasks)}

⏳ **Pending Approvals ({len(approvals)}):**
{self._format_approvals(approvals)}

💰 **Budget Status:**
- Spent this month: ${budget['spent']:.2f} / ${budget['limit']:.2f}
- Remaining: ${budget['remaining']:.2f}
- Days left: {budget['days_left']}

Have a productive day! 🚀
        """
        
        return briefing
    
    async def send_notification(self, message: str, priority: int = 5) -> bool:
        """
        Send notification via Telegram with rate limiting
        
        Rate Limiting Rules:
        - Urgent (priority >= 9): Always send immediately
        - High (priority 7-8): Queue if limit reached
        - Normal (priority 1-6): Batch into hourly digest
        - Max 10 messages/hour for non-urgent
        """
        # Reset counter if hour passed
        if (datetime.now() - self.last_reset).seconds >= 3600:
            self.notification_count = 0
            self.last_reset = datetime.now()
        
        # Urgent messages bypass rate limit
        if priority >= 9:
            await self.telegram.send_message(message)
            return True
        
        # Check rate limit
        if self.notification_count >= self.notification_rate_limit:
            # Queue for later
            await self._queue_notification(message, priority)
            return False
        
        # Send message
        await self.telegram.send_message(message)
        self.notification_count += 1
        return True
    
    async def create_task_from_email(self, email: EmailMessage, action_items: List[Dict]):
        """Create tasks from email action items"""
        for item in action_items:
            task = AssistantTask(
                title=item['task'],
                description=f"From email: {email.subject}",
                task_type='email',
                priority=item.get('priority', 5),
                due_date=item.get('due_date'),
                related_entity_type='email_message',
                related_entity_id=email.id,
                assigned_to='user',
                status='pending'
            )
            
            await task.save()
            
            # Emit event
            await self.event_bus.emit('task.created', {
                'task_id': str(task.id),
                'title': task.title,
                'due_date': task.due_date.isoformat() if task.due_date else None
            })
    
    async def check_deadlines(self):
        """Check for upcoming deadlines and send reminders"""
        # Get tasks due in next 3 days
        upcoming = await AssistantTask.get_upcoming(days=3)
        
        for task in upcoming:
            days_left = (task.due_date - datetime.now()).days
            
            if days_left <= 1:
                priority = 9  # Urgent
                emoji = "🚨"
            elif days_left <= 3:
                priority = 7  # High
                emoji = "⚠️"
            else:
                priority = 5  # Normal
                emoji = "📅"
            
            message = f"{emoji} **Deadline Reminder**\n\n"
            message += f"Task: {task.title}\n"
            message += f"Due: {task.due_date.strftime('%B %d, %Y')}\n"
            message += f"Days left: {days_left}\n"
            
            await self.send_notification(message, priority=priority)
    
    async def monitor_costs(self):
        """Monitor API costs and alert if approaching limit"""
        # Get current month costs
        openclaw_cost = await OpenClawUsage.get_month_total()
        gemini_cost = await self._get_gemini_cost()
        total_cost = openclaw_cost + gemini_cost
        
        budget_limit = 50.0  # $50/month
        threshold = budget_limit * 0.8  # 80%
        
        if total_cost >= budget_limit:
            # Hard stop
            await self.send_notification(
                f"🛑 **BUDGET EXCEEDED**\n\n"
                f"Total cost: ${total_cost:.2f}\n"
                f"Budget: ${budget_limit:.2f}\n\n"
                f"All AI agents have been paused.",
                priority=10
            )
            await self._pause_all_agents()
            
        elif total_cost >= threshold:
            # Warning
            await self.send_notification(
                f"⚠️ **Budget Warning**\n\n"
                f"Total cost: ${total_cost:.2f}\n"
                f"Budget: ${budget_limit:.2f}\n"
                f"Remaining: ${budget_limit - total_cost:.2f}\n\n"
                f"Consider reducing scraping frequency.",
                priority=8
            )
    
    async def handle_telegram_command(self, command: str, args: List[str]) -> str:
        """Handle Telegram bot commands"""
        if command == '/status':
            return await self._get_system_status()
        
        elif command == '/jobs':
            jobs = await JobPosting.get_recent(limit=10)
            return self._format_jobs(jobs)
        
        elif command == '/contacts':
            contacts = await Contact.get_recent(limit=10)
            return self._format_contacts(contacts)
        
        elif command == '/tasks':
            tasks = await AssistantTask.get_pending()
            return self._format_tasks(tasks)
        
        elif command == '/costs':
            return await self._get_cost_breakdown()
        
        elif command == '/approve':
            if not args:
                return "Usage: /approve <approval_id>"
            approval_id = args[0]
            return await self._approve_request(approval_id)
        
        elif command == '/reject':
            if not args:
                return "Usage: /reject <approval_id>"
            approval_id = args[0]
            return await self._reject_request(approval_id)
        
        else:
            return "Unknown command. Try /help"
```

**Database Model:**

```python
# app/models/assistant_task.py
class AssistantTask(Base):
    __tablename__ = 'assistant_tasks'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    title = Column(String(500), nullable=False)
    description = Column(Text)
    task_type = Column(String(50))  # 'email', 'application', 'follow_up', 'meeting'
    priority = Column(Integer, default=5)  # 1-10
    status = Column(String(50), default='pending')  # 'pending', 'in_progress', 'completed'
    
    due_date = Column(TIMESTAMP)
    related_entity_type = Column(String(50))  # 'job_posting', 'contact', 'email_thread'
    related_entity_id = Column(UUID(as_uuid=True))
    
    assigned_to = Column(String(100), default='user')  # 'user', 'agent_name'
    completed_at = Column(TIMESTAMP)
    
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now())
    
    __table_args__ = (
        Index('idx_task_status', 'status'),
        Index('idx_task_priority', 'priority', postgresql_ops={'priority': 'DESC'}),
        Index('idx_task_due_date', 'due_date'),
        Index('idx_task_related', 'related_entity_type', 'related_entity_id'),
        Index('idx_task_status_priority', 'status', 'priority'),
    )
```



### 2.5 OpenClaw Integration Module

**Purpose:** เชื่อมต่อกับ OpenClaw API สำหรับ web scraping ขั้นสูง

**Class Design:**

```python
import httpx
import hashlib
from typing import Dict, Optional
from datetime import datetime, timedelta

class OpenClawClient:
    """
    Client สำหรับ OpenClaw API
    
    Features:
    - Browser automation สำหรับ anti-bot sites
    - Caching layer (Redis, 4h TTL)
    - Rate limiting (50 req/day LinkedIn, 20 req/day Network)
    - Cost tracking
    - Circuit breaker
    - 4-tier fallback
    """
    
    def __init__(self, api_key: str, redis_client, database):
        self.api_key = api_key
        self.base_url = "https://api.openclaw.com/v1"
        self.redis = redis_client
        self.db = database
        
        # Rate limits
        self.rate_limits = {
            'linkedin_jobs': {'limit': 50, 'period': 'day'},
            'linkedin_network': {'limit': 20, 'period': 'day'},
            'upwork': {'limit': 30, 'period': 'day'}
        }
        
        # Circuit breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=60
        )
        
        # Cost tracking
        self.monthly_budget = 50.0  # $50/month
        
    async def scrape(
        self, 
        url: str, 
        selectors: Dict,
        platform: str,
        cache_key: Optional[str] = None
    ) -> Dict:
        """
        Scrape URL with caching and fallback
        
        4-Tier Fallback:
        1. Redis cache (if available)
        2. OpenClaw API
        3. Database cache (stale data)
        4. Alert user
        """
        # Tier 1: Check Redis cache
        if cache_key:
            cached = await self.redis.get(cache_key)
            if cached:
                return {'data': cached, 'source': 'cache', 'age': 'fresh'}
        
        # Check rate limit
        if not await self._check_rate_limit(platform):
            # Tier 3: Use stale cache
            stale = await self._get_stale_cache(cache_key)
            if stale:
                return {'data': stale, 'source': 'cache', 'age': 'stale'}
            
            # Tier 4: Alert user
            raise RateLimitExceeded(f"Rate limit exceeded for {platform}")
        
        # Check budget
        if not await self._check_budget():
            raise BudgetExceeded("Monthly budget exceeded")
        
        # Tier 2: Call OpenClaw API
        try:
            result = await self.circuit_breaker.call(
                self._make_request,
                url=url,
                selectors=selectors,
                platform=platform
            )
            
            # Cache result
            if cache_key:
                await self.redis.setex(
                    cache_key,
                    14400,  # 4 hours
                    result['html']
                )
            
            # Track usage
            await self._track_usage(platform, result)
            
            return {'data': result, 'source': 'openclaw', 'age': 'fresh'}
            
        except CircuitBreakerOpen:
            # Tier 3: Use stale cache
            stale = await self._get_stale_cache(cache_key)
            if stale:
                return {'data': stale, 'source': 'cache', 'age': 'stale'}
            
            # Tier 4: Alert user
            raise ServiceUnavailable("OpenClaw is down and no cache available")
    
    async def _make_request(self, url: str, selectors: Dict, platform: str) -> Dict:
        """Make actual API request to OpenClaw"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/scrape",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "url": url,
                    "selectors": selectors,
                    "wait_for": "networkidle",
                    "timeout": 60000
                },
                timeout=90.0
            )
            
            if response.status_code == 429:
                raise RateLimitExceeded("OpenClaw rate limit")
            
            response.raise_for_status()
            return response.json()
    
    async def _check_rate_limit(self, platform: str) -> bool:
        """Check if within rate limit"""
        limit_config = self.rate_limits.get(platform)
        if not limit_config:
            return True
        
        # Get current usage
        key = f"openclaw:ratelimit:{platform}:{datetime.now().strftime('%Y-%m-%d')}"
        current = await self.redis.get(key) or 0
        
        if int(current) >= limit_config['limit']:
            return False
        
        # Increment counter
        await self.redis.incr(key)
        await self.redis.expire(key, 86400)  # 24 hours
        
        return True
    
    async def _check_budget(self) -> bool:
        """Check if within monthly budget"""
        # Get current month spending
        spent = await OpenClawUsage.get_month_total()
        
        if spent >= self.monthly_budget:
            return False
        
        return True
    
    async def _track_usage(self, platform: str, result: Dict):
        """Track API usage and cost"""
        usage = OpenClawUsage(
            request_type='scrape',
            target_url=result.get('url'),
            target_platform=platform,
            tokens_used=result.get('tokens', 0),
            cost_usd=result.get('cost', 0.05),  # Default $0.05
            duration_ms=result.get('duration_ms', 0),
            status='success',
            response_size_bytes=len(result.get('html', ''))
        )
        
        await usage.save()
        
        # Check if approaching budget
        total_spent = await OpenClawUsage.get_month_total()
        if total_spent >= self.monthly_budget * 0.8:  # 80% threshold
            await self._alert_budget_warning(total_spent)

class CircuitBreaker:
    """Circuit breaker pattern for external services"""
    
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'closed'  # 'closed', 'open', 'half-open'
    
    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker"""
        if self.state == 'open':
            # Check if recovery timeout passed
            if datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                self.state = 'half-open'
            else:
                raise CircuitBreakerOpen("Circuit breaker is open")
        
        try:
            result = await func(*args, **kwargs)
            
            # Success - reset if half-open
            if self.state == 'half-open':
                self.state = 'closed'
                self.failure_count = 0
            
            return result
            
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.failure_count >= self.failure_threshold:
                self.state = 'open'
            
            raise e
```

**Database Model:**

```python
# app/models/openclaw_usage.py
class OpenClawUsage(Base):
    __tablename__ = 'openclaw_usage'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    request_type = Column(String(50))  # 'scrape', 'screenshot', 'pdf'
    target_url = Column(Text)
    target_platform = Column(String(100))  # 'linkedin', 'upwork', 'fiverr'
    
    tokens_used = Column(Integer)
    cost_usd = Column(DECIMAL(10, 4))
    duration_ms = Column(Integer)
    
    status = Column(String(50))  # 'success', 'error', 'timeout'
    error_message = Column(Text)
    response_size_bytes = Column(Integer)
    
    created_at = Column(TIMESTAMP, default=func.now())
    
    __table_args__ = (
        Index('idx_openclaw_platform', 'target_platform'),
        Index('idx_openclaw_status', 'status'),
        Index('idx_openclaw_created', 'created_at', postgresql_ops={'created_at': 'DESC'}),
    )
    
    @classmethod
    async def get_month_total(cls) -> float:
        """Get total cost for current month"""
        from sqlalchemy import func, extract
        
        result = await cls.query.filter(
            extract('year', cls.created_at) == datetime.now().year,
            extract('month', cls.created_at) == datetime.now().month
        ).with_entities(func.sum(cls.cost_usd)).scalar()
        
        return float(result or 0)
```

### 2.6 Enhanced Scrapers (5-7 Platforms)

**Scraper Architecture:**

```python
from abc import ABC, abstractmethod
from typing import List, Dict
import httpx
from bs4 import BeautifulSoup

class BaseScraper(ABC):
    """Base class for all scrapers"""
    
    def __init__(self, openclaw_client: Optional[OpenClawClient] = None):
        self.openclaw = openclaw_client
        self.platform_name = ""
        
    @abstractmethod
    async def scrape(self, query: Dict) -> List[Dict]:
        """Scrape platform and return raw data"""
        pass
    
    async def _fetch_html(self, url: str, use_openclaw: bool = False) -> str:
        """Fetch HTML with fallback"""
        if use_openclaw and self.openclaw:
            result = await self.openclaw.scrape(
                url=url,
                selectors={},
                platform=self.platform_name,
                cache_key=f"{self.platform_name}:{url}"
            )
            return result['data']['html']
        else:
            # Direct HTTP request
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                return response.text

class LinkedInJobScraper(BaseScraper):
    """Scraper for LinkedIn jobs (requires OpenClaw)"""
    
    def __init__(self, openclaw_client: OpenClawClient):
        super().__init__(openclaw_client)
        self.platform_name = "linkedin"
        
    async def scrape(self, query: Dict) -> List[Dict]:
        """
        Scrape LinkedIn jobs
        
        Args:
            query: {
                'keywords': 'python developer',
                'location': 'Remote',
                'job_type': 'full-time',
                'max_pages': 5
            }
        """
        jobs = []
        
        for page in range(query.get('max_pages', 5)):
            url = self._build_url(query, page)
            
            # Must use OpenClaw (anti-bot protection)
            html = await self._fetch_html(url, use_openclaw=True)
            
            # Parse jobs
            soup = BeautifulSoup(html, 'html.parser')
            job_cards = soup.select('.job-card-container')
            
            for card in job_cards:
                job = {
                    'source': 'linkedin',
                    'source_id': card.get('data-job-id'),
                    'url': card.select_one('a')['href'],
                    'title': card.select_one('.job-card-list__title').text.strip(),
                    'company': card.select_one('.job-card-container__company-name').text.strip(),
                    'location': card.select_one('.job-card-container__metadata-item').text.strip(),
                    'posted_at': self._parse_date(card.select_one('.job-card-container__listed-time').text),
                    'job_type': 'full-time',
                    'skills': []  # Extract from description later
                }
                
                jobs.append(job)
        
        return jobs

class FastWorkScraper(BaseScraper):
    """Scraper for FastWork (direct HTTP, no OpenClaw needed)"""
    
    def __init__(self):
        super().__init__(openclaw_client=None)
        self.platform_name = "fastwork"
        
    async def scrape(self, query: Dict) -> List[Dict]:
        """Scrape FastWork jobs"""
        jobs = []
        
        url = f"https://fastwork.co/search?q={query['keywords']}"
        html = await self._fetch_html(url, use_openclaw=False)
        
        soup = BeautifulSoup(html, 'html.parser')
        job_cards = soup.select('.job-item')
        
        for card in job_cards:
            job = {
                'source': 'fastwork',
                'source_id': card.get('data-id'),
                'url': f"https://fastwork.co{card.select_one('a')['href']}",
                'title': card.select_one('.job-title').text.strip(),
                'company': card.select_one('.company-name').text.strip(),
                'salary_min': self._parse_salary(card.select_one('.salary').text),
                'job_type': 'freelance',
                'skills': [s.text for s in card.select('.skill-tag')]
            }
            
            jobs.append(job)
        
        return jobs

# Similar scrapers for: Upwork, Fiverr, Devpost, RSS feeds
```



---

## 3. Database Design

### 3.1 Schema Overview

ระบบเพิ่ม 8 tables ใหม่เข้ากับ BRAVOS ที่มี 16 tables อยู่แล้ว:

**New Tables (Phase 1):**
1. `job_postings` - งานที่พบจาก scrapers
2. `email_threads` - email conversations
3. `email_messages` - individual emails
4. `assistant_tasks` - tasks และ reminders
5. `network_interactions` - interactions กับ contacts
6. `openclaw_usage` - OpenClaw API usage tracking
7. `scraper_runs` - scraper execution history
8. `api_rate_limits` - rate limiting per service

### 3.2 Entity Relationship Diagram

```mermaid
erDiagram
    job_postings ||--o{ submissions : "applied_to"
    job_postings {
        uuid id PK
        string source
        string source_hash UK
        string title
        decimal fit_score
        string status
    }
    
    email_threads ||--|{ email_messages : "contains"
    email_threads {
        uuid id PK
        string thread_id UK
        string category
        int priority
        jsonb action_items
    }
    
    email_messages {
        uuid id PK
        uuid thread_id FK
        string message_id UK
        string from_email
        text body_text
        timestamp received_at
    }
    
    contacts ||--|{ network_interactions : "has"
    contacts {
        uuid id PK
        string name
        decimal value_score
        decimal relationship_strength
        timestamp next_followup_date
    }
    
    network_interactions {
        uuid id PK
        uuid contact_id FK
        string interaction_type
        string sentiment
        timestamp interaction_at
    }
    
    assistant_tasks {
        uuid id PK
        string title
        int priority
        timestamp due_date
        string related_entity_type
        uuid related_entity_id
    }
    
    openclaw_usage {
        uuid id PK
        string target_platform
        decimal cost_usd
        int duration_ms
        timestamp created_at
    }
    
    scraper_runs {
        uuid id PK
        string scraper_name
        int items_found
        string status
        timestamp started_at
    }
```

### 3.3 Index Strategy

**High-Priority Indexes:**

```sql
-- job_postings
CREATE INDEX idx_job_source_hash ON job_postings(source_hash);  -- Deduplication
CREATE INDEX idx_job_fit_score ON job_postings(fit_score DESC);  -- Sorting
CREATE INDEX idx_job_status ON job_postings(status);  -- Filtering
CREATE INDEX idx_job_posted ON job_postings(posted_at DESC);  -- Recent jobs

-- email_threads
CREATE INDEX idx_email_category ON email_threads(category);
CREATE INDEX idx_email_priority ON email_threads(priority DESC);
CREATE INDEX idx_email_status ON email_threads(status);
CREATE INDEX idx_email_last_message ON email_threads(last_message_at DESC);

-- assistant_tasks
CREATE INDEX idx_task_status ON assistant_tasks(status);
CREATE INDEX idx_task_priority ON assistant_tasks(priority DESC);
CREATE INDEX idx_task_due_date ON assistant_tasks(due_date);
CREATE INDEX idx_task_status_priority ON assistant_tasks(status, priority DESC);  -- Composite

-- network_interactions
CREATE INDEX idx_interaction_contact ON network_interactions(contact_id);
CREATE INDEX idx_interaction_at ON network_interactions(interaction_at DESC);
CREATE INDEX idx_interaction_contact_at ON network_interactions(contact_id, interaction_at DESC);  -- Composite

-- openclaw_usage
CREATE INDEX idx_openclaw_platform ON openclaw_usage(target_platform);
CREATE INDEX idx_openclaw_created ON openclaw_usage(created_at DESC);
```

**Query Performance Targets:**
- Simple SELECT: <50ms (P95)
- JOIN queries: <200ms (P95)
- Aggregations: <500ms (P95)

### 3.4 Migration Strategy

**Alembic Migration Files:**

```python
# alembic/versions/004_personal_assistant_tables.py
"""Add personal assistant tables

Revision ID: 004
Revises: 003
Create Date: 2024-01-15 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    # 1. job_postings
    op.create_table(
        'job_postings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source', sa.String(100), nullable=False),
        sa.Column('source_id', sa.String(255)),
        sa.Column('source_url', sa.Text, nullable=False),
        sa.Column('source_hash', sa.String(64), unique=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('company', sa.String(255)),
        sa.Column('location', sa.String(255)),
        sa.Column('job_type', sa.String(50)),
        sa.Column('salary_min', sa.DECIMAL(12, 2)),
        sa.Column('salary_max', sa.DECIMAL(12, 2)),
        sa.Column('salary_currency', sa.String(3), default='USD'),
        sa.Column('skills', postgresql.JSONB),
        sa.Column('requirements', sa.Text),
        sa.Column('posted_at', sa.TIMESTAMP),
        sa.Column('deadline', sa.TIMESTAMP),
        sa.Column('fit_score', sa.DECIMAL(3, 2)),
        sa.Column('action_priority', sa.String(20)),
        sa.Column('status', sa.String(50), default='new'),
        sa.Column('created_at', sa.TIMESTAMP, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP, server_default=sa.func.now())
    )
    
    # Create indexes
    op.create_index('idx_job_source_hash', 'job_postings', ['source_hash'])
    op.create_index('idx_job_fit_score', 'job_postings', [sa.text('fit_score DESC')])
    op.create_index('idx_job_status', 'job_postings', ['status'])
    op.create_index('idx_job_posted', 'job_postings', [sa.text('posted_at DESC')])
    
    # 2. email_threads
    op.create_table(
        'email_threads',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('thread_id', sa.String(255), unique=True),
        sa.Column('subject', sa.String(500)),
        sa.Column('participants', postgresql.JSONB),
        sa.Column('category', sa.String(50)),
        sa.Column('priority', sa.Integer, default=5),
        sa.Column('last_message_at', sa.TIMESTAMP),
        sa.Column('unread_count', sa.Integer, default=0),
        sa.Column('has_attachments', sa.Boolean, default=False),
        sa.Column('action_items', postgresql.JSONB),
        sa.Column('status', sa.String(50), default='unread'),
        sa.Column('created_at', sa.TIMESTAMP, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP, server_default=sa.func.now())
    )
    
    # ... (similar for other 6 tables)

def downgrade():
    op.drop_table('job_postings')
    op.drop_table('email_threads')
    # ... (drop other tables)
```

### 3.5 Data Retention Policy

| Table | Retention | Archive Strategy |
|-------|-----------|------------------|
| job_postings | 6 months | Archive to cold storage after 6 months |
| email_messages | 1 year | Archive after 1 year, keep threads |
| network_interactions | Permanent | Keep all (relationship history) |
| openclaw_usage | 3 months | Aggregate monthly, delete details |
| scraper_runs | Last 1000 runs | Keep last 1000 per scraper |
| assistant_tasks | Permanent | Keep completed tasks for learning |

---

## 4. API Design

### 4.1 RESTful Endpoints

**Base URL:** `/api/v1`

**Authentication:** JWT Bearer token

#### 4.1.1 Jobs API

```
GET    /api/v1/jobs                    # List jobs
GET    /api/v1/jobs/{id}               # Get job details
POST   /api/v1/jobs/{id}/apply         # Apply to job
GET    /api/v1/jobs/stats              # Get job statistics
```

**Example Request:**

```http
GET /api/v1/jobs?status=new&min_score=7.0&limit=20&offset=0
Authorization: Bearer <token>
```

**Example Response:**

```json
{
  "data": [
    {
      "id": "uuid-here",
      "source": "linkedin",
      "title": "Senior Python Developer",
      "company": "Tech Corp",
      "location": "Remote",
      "salary_max": 120000,
      "fit_score": 8.5,
      "skills": ["Python", "FastAPI", "PostgreSQL"],
      "posted_at": "2024-01-15T10:00:00Z",
      "status": "new"
    }
  ],
  "pagination": {
    "total": 150,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

#### 4.1.2 Contacts API

```
GET    /api/v1/contacts                # List contacts
GET    /api/v1/contacts/{id}           # Get contact details
POST   /api/v1/contacts/{id}/outreach  # Send outreach
GET    /api/v1/contacts/network        # Get network graph
```

#### 4.1.3 Emails API

```
GET    /api/v1/emails                  # List email threads
GET    /api/v1/emails/{id}             # Get thread details
POST   /api/v1/emails/{id}/reply       # Reply to email
PUT    /api/v1/emails/{id}/category    # Update category
```

#### 4.1.4 Tasks API

```
GET    /api/v1/tasks                   # List tasks
POST   /api/v1/tasks                   # Create task
GET    /api/v1/tasks/{id}              # Get task details
PUT    /api/v1/tasks/{id}              # Update task
DELETE /api/v1/tasks/{id}              # Delete task
POST   /api/v1/tasks/{id}/complete     # Mark complete
```

#### 4.1.5 Approvals API

```
GET    /api/v1/approvals               # List pending approvals
POST   /api/v1/approvals/{id}/approve  # Approve request
POST   /api/v1/approvals/{id}/reject   # Reject request
```

#### 4.1.6 Metrics API

```
GET    /api/v1/metrics/dashboard       # Dashboard metrics
GET    /api/v1/metrics/costs           # Cost breakdown
GET    /api/v1/metrics/agents          # Agent performance
```

### 4.2 Request/Response Schemas

**Pydantic Schemas:**

```python
# app/schemas/job.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

class JobBase(BaseModel):
    source: str
    title: str
    company: Optional[str]
    location: Optional[str]
    job_type: Optional[str]
    salary_min: Optional[Decimal]
    salary_max: Optional[Decimal]
    skills: List[str] = []

class JobCreate(JobBase):
    source_id: str
    source_url: str
    description: Optional[str]

class JobResponse(JobBase):
    id: str
    fit_score: Decimal
    action_priority: str
    status: str
    posted_at: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True

class JobListResponse(BaseModel):
    data: List[JobResponse]
    pagination: dict

# Similar schemas for contacts, emails, tasks
```

### 4.3 Error Handling

**Standard Error Response:**

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": [
      {
        "field": "min_score",
        "message": "Must be between 0 and 10"
      }
    ]
  }
}
```

**HTTP Status Codes:**
- 200: Success
- 201: Created
- 400: Bad Request (validation error)
- 401: Unauthorized (missing/invalid token)
- 403: Forbidden (insufficient permissions)
- 404: Not Found
- 429: Too Many Requests (rate limit)
- 500: Internal Server Error

### 4.4 Rate Limiting

**Rate Limits:**
- Authenticated users: 100 requests/minute
- Unauthenticated: 10 requests/minute
- Bulk operations: 10 requests/minute

**Implementation:**

```python
from fastapi import Request, HTTPException
from redis import Redis
import time

class RateLimiter:
    def __init__(self, redis: Redis):
        self.redis = redis
        
    async def check_rate_limit(self, request: Request, limit: int = 100):
        """Check if request is within rate limit"""
        # Get user ID from token
        user_id = request.state.user_id
        
        # Rate limit key
        key = f"ratelimit:{user_id}:{int(time.time() / 60)}"
        
        # Get current count
        current = self.redis.get(key) or 0
        
        if int(current) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again in 1 minute."
            )
        
        # Increment counter
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)  # 1 minute TTL
        pipe.execute()
```



---

## 5. Integration Design

### 5.1 Gmail API Integration

**OAuth 2.0 Flow:**

```mermaid
sequenceDiagram
    participant User
    participant App
    participant Google
    participant Gmail

    User->>App: Click "Connect Gmail"
    App->>Google: Redirect to OAuth consent
    Google-->>User: Show permissions screen
    User->>Google: Grant permissions
    Google->>App: Return authorization code
    App->>Google: Exchange code for tokens
    Google-->>App: Access token + Refresh token
    App->>Gmail: Fetch emails (with access token)
    Gmail-->>App: Email data
```

**Implementation:**

```python
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

class GmailIntegration:
    """Gmail API integration"""
    
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.modify'
    ]
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        
    def get_authorization_url(self, redirect_uri: str) -> str:
        """Get OAuth authorization URL"""
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            },
            scopes=self.SCOPES,
            redirect_uri=redirect_uri
        )
        
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        
        return auth_url
    
    async def exchange_code(self, code: str, redirect_uri: str) -> Credentials:
        """Exchange authorization code for tokens"""
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            },
            scopes=self.SCOPES,
            redirect_uri=redirect_uri
        )
        
        flow.fetch_token(code=code)
        return flow.credentials
    
    async def refresh_token(self, refresh_token: str) -> Credentials:
        """Refresh access token"""
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret
        )
        
        creds.refresh(Request())
        return creds
```

### 5.2 Telegram Bot Integration

**Webhook Setup:**

```python
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

class TelegramBotIntegration:
    """Telegram Bot integration"""
    
    def __init__(self, bot_token: str, webhook_url: str):
        self.bot_token = bot_token
        self.webhook_url = webhook_url
        self.app = Application.builder().token(bot_token).build()
        
    async def setup_webhook(self):
        """Setup webhook for receiving updates"""
        await self.app.bot.set_webhook(
            url=f"{self.webhook_url}/telegram/webhook",
            allowed_updates=["message", "callback_query"]
        )
    
    async def send_approval_request(
        self, 
        chat_id: int, 
        approval_id: str,
        title: str,
        description: str,
        preview: str
    ):
        """Send approval request with inline keyboard"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{approval_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject:{approval_id}")
            ],
            [
                InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{approval_id}")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = f"""
🔔 **Approval Request**

**{title}**

{description}

**Preview:**
```
{preview}
```

Please review and approve/reject.
        """
        
        await self.app.bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def handle_callback(self, update: Update):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        await query.answer()
        
        # Parse callback data
        action, approval_id = query.data.split(':')
        
        if action == 'approve':
            await self._approve_request(approval_id)
            await query.edit_message_text("✅ Approved!")
            
        elif action == 'reject':
            await self._reject_request(approval_id)
            await query.edit_message_text("❌ Rejected!")
            
        elif action == 'edit':
            await query.edit_message_text("✏️ Edit mode (coming soon)")
```

**Command Handlers:**

```python
async def handle_status_command(update: Update, context):
    """Handle /status command"""
    # Get system status
    status = await get_system_status()
    
    message = f"""
📊 **System Status**

**Agents:**
- Job Hunter: {status['job_hunter']}
- Network Builder: {status['network_builder']}
- Email Manager: {status['email_manager']}
- Personal Assistant: {status['personal_assistant']}

**Today's Activity:**
- Jobs found: {status['jobs_found']}
- Contacts added: {status['contacts_added']}
- Emails processed: {status['emails_processed']}

**Budget:**
- Spent: ${status['spent']:.2f} / ${status['budget']:.2f}
- Remaining: ${status['remaining']:.2f}
    """
    
    await update.message.reply_text(message, parse_mode='Markdown')

# Register handlers
app.add_handler(CommandHandler("status", handle_status_command))
app.add_handler(CommandHandler("jobs", handle_jobs_command))
app.add_handler(CommandHandler("contacts", handle_contacts_command))
app.add_handler(CommandHandler("tasks", handle_tasks_command))
app.add_handler(CommandHandler("costs", handle_costs_command))
app.add_handler(CallbackQueryHandler(handle_callback))
```

### 5.3 Redis Caching Layer

**Cache Strategy:**

```python
import redis.asyncio as redis
import json
from typing import Optional, Any
from datetime import timedelta

class RedisCacheLayer:
    """Redis caching layer for scraping results"""
    
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.default_ttl = 14400  # 4 hours
        
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        value = await self.redis.get(key)
        if value:
            return json.loads(value)
        return None
    
    async def set(self, key: str, value: Any, ttl: int = None):
        """Set value in cache"""
        ttl = ttl or self.default_ttl
        await self.redis.setex(
            key,
            ttl,
            json.dumps(value)
        )
    
    async def delete(self, key: str):
        """Delete key from cache"""
        await self.redis.delete(key)
    
    async def get_or_fetch(
        self, 
        key: str, 
        fetch_func,
        ttl: int = None
    ) -> Any:
        """Get from cache or fetch if not exists"""
        # Try cache first
        cached = await self.get(key)
        if cached:
            return cached
        
        # Fetch from source
        value = await fetch_func()
        
        # Cache result
        await self.set(key, value, ttl)
        
        return value
    
    async def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching pattern"""
        keys = []
        async for key in self.redis.scan_iter(match=pattern):
            keys.append(key)
        
        if keys:
            await self.redis.delete(*keys)
```

**Cache Keys:**

```
linkedin:jobs:{query_hash}:{page}       # LinkedIn job search results
linkedin:profile:{profile_id}           # LinkedIn profile data
upwork:jobs:{category}:{page}           # Upwork job listings
fastwork:jobs:{keywords}                # FastWork search results
gmail:thread:{thread_id}                # Gmail thread data
openclaw:ratelimit:{platform}:{date}    # Rate limit counters
```

### 5.4 EventBus Extensions

**New Event Types:**

```python
# app/core/event_bus.py (extended)

class EventType(str, Enum):
    # Existing events
    OPPORTUNITY_FOUND = "opportunity.found"
    SUBMISSION_CREATED = "submission.created"
    
    # New events
    JOB_FOUND = "job.found"
    CONTACT_DISCOVERED = "contact.discovered"
    EMAIL_URGENT = "email.urgent"
    EMAIL_RECEIVED = "email.received"
    TASK_CREATED = "task.created"
    TASK_DUE = "task.due"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_REJECTED = "approval.rejected"
    SCRAPER_FAILED = "scraper.failed"
    COST_LIMIT_REACHED = "cost.limit_reached"
    BUDGET_WARNING = "budget.warning"

class Event(BaseModel):
    """Event schema"""
    event_type: EventType
    timestamp: datetime
    data: Dict
    priority: int = 5  # 1-10
    retry_count: int = 0
    max_retries: int = 3

class EventBus:
    """Extended EventBus with new events"""
    
    async def emit(self, event_type: str, data: Dict, priority: int = 5):
        """Emit event to all subscribers"""
        event = Event(
            event_type=event_type,
            timestamp=datetime.now(),
            data=data,
            priority=priority
        )
        
        # Get subscribers for this event type
        subscribers = self.subscribers.get(event_type, [])
        
        # Deliver to each subscriber
        for subscriber in subscribers:
            try:
                await subscriber.handle_event(event)
            except Exception as e:
                # Retry logic
                if event.retry_count < event.max_retries:
                    event.retry_count += 1
                    await self._retry_event(event, subscriber)
                else:
                    # Log failure
                    logger.error(f"Event delivery failed: {e}")
```



---

## 6. Security Design

### 6.1 API Key Encryption

**AES-256 Encryption:**

```python
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
import base64
import os

class APIKeyEncryption:
    """Encrypt/decrypt API keys using AES-256"""
    
    def __init__(self, master_key: str):
        # Derive encryption key from master key
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'bravos_salt',  # Should be random in production
            iterations=100000
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
        self.cipher = Fernet(key)
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt API key"""
        encrypted = self.cipher.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt API key"""
        encrypted = base64.urlsafe_b64decode(ciphertext.encode())
        decrypted = self.cipher.decrypt(encrypted)
        return decrypted.decode()

# Usage
encryptor = APIKeyEncryption(os.getenv('MASTER_KEY'))

# Store encrypted key in database
encrypted_key = encryptor.encrypt(openclaw_api_key)
await db.save_setting('openclaw_api_key', encrypted_key)

# Retrieve and decrypt
encrypted_key = await db.get_setting('openclaw_api_key')
api_key = encryptor.decrypt(encrypted_key)
```

### 6.2 PII Handling

**Data Classification:**

| Data Type | Sensitivity | Encryption | Logging | Retention |
|-----------|-------------|------------|---------|-----------|
| API Keys | High | AES-256 | Never | Permanent |
| Email Content | Medium | At rest | Sanitized | 1 year |
| Contact Names | Medium | At rest | Allowed | Permanent |
| Phone Numbers | Medium | AES-256 | Never | Permanent |
| Job Descriptions | Low | None | Allowed | 6 months |

**Anonymization for AI:**

```python
import re
import hashlib

class PIIAnonymizer:
    """Anonymize PII before sending to AI APIs"""
    
    def anonymize_email(self, text: str) -> tuple[str, dict]:
        """Replace emails with placeholders"""
        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        
        mapping = {}
        for i, email in enumerate(emails):
            placeholder = f"EMAIL_{i}"
            mapping[placeholder] = email
            text = text.replace(email, placeholder)
        
        return text, mapping
    
    def anonymize_phone(self, text: str) -> tuple[str, dict]:
        """Replace phone numbers with placeholders"""
        phones = re.findall(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', text)
        
        mapping = {}
        for i, phone in enumerate(phones):
            placeholder = f"PHONE_{i}"
            mapping[placeholder] = phone
            text = text.replace(phone, placeholder)
        
        return text, mapping
    
    def anonymize(self, text: str) -> tuple[str, dict]:
        """Anonymize all PII"""
        text, email_map = self.anonymize_email(text)
        text, phone_map = self.anonymize_phone(text)
        
        mapping = {**email_map, **phone_map}
        return text, mapping
    
    def deanonymize(self, text: str, mapping: dict) -> str:
        """Restore original PII"""
        for placeholder, original in mapping.items():
            text = text.replace(placeholder, original)
        return text

# Usage
anonymizer = PIIAnonymizer()

# Before sending to AI
anonymized_text, mapping = anonymizer.anonymize(email_body)
ai_response = await gemini.generate(anonymized_text)

# After receiving from AI
original_text = anonymizer.deanonymize(ai_response, mapping)
```

### 6.3 Rate Limiting

**Multi-Level Rate Limiting:**

```python
from fastapi import Request, HTTPException
from redis import Redis
import time

class MultiLevelRateLimiter:
    """Rate limiting at multiple levels"""
    
    def __init__(self, redis: Redis):
        self.redis = redis
        
        # Rate limit tiers
        self.limits = {
            'per_second': 10,
            'per_minute': 100,
            'per_hour': 1000,
            'per_day': 10000
        }
    
    async def check_rate_limit(self, user_id: str):
        """Check all rate limit tiers"""
        now = int(time.time())
        
        # Check each tier
        for period, limit in self.limits.items():
            if period == 'per_second':
                window = now
            elif period == 'per_minute':
                window = now // 60
            elif period == 'per_hour':
                window = now // 3600
            elif period == 'per_day':
                window = now // 86400
            
            key = f"ratelimit:{user_id}:{period}:{window}"
            current = int(self.redis.get(key) or 0)
            
            if current >= limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded: {limit} requests {period}"
                )
            
            # Increment counter
            pipe = self.redis.pipeline()
            pipe.incr(key)
            
            # Set TTL based on period
            if period == 'per_second':
                pipe.expire(key, 1)
            elif period == 'per_minute':
                pipe.expire(key, 60)
            elif period == 'per_hour':
                pipe.expire(key, 3600)
            elif period == 'per_day':
                pipe.expire(key, 86400)
            
            pipe.execute()
```

### 6.4 Circuit Breaker Pattern

**Implementation:**

```python
from enum import Enum
from datetime import datetime, timedelta
from typing import Callable, Any

class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreaker:
    """Circuit breaker for external services"""
    
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: int = 60,
        success_threshold: int = 2
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker"""
        
        # Check state
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout passed
            if datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                raise CircuitBreakerOpen(
                    f"Circuit breaker is open. Try again in {self.recovery_timeout}s"
                )
        
        try:
            # Execute function
            result = await func(*args, **kwargs)
            
            # Success
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                
                # Enough successes to close circuit
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
            
            return result
            
        except Exception as e:
            # Failure
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            # Open circuit if threshold reached
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
            
            raise e

# Usage
openclaw_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

try:
    result = await openclaw_breaker.call(
        openclaw_client.scrape,
        url="https://linkedin.com/jobs",
        selectors={}
    )
except CircuitBreakerOpen:
    # Fallback to cache
    result = await get_cached_data()
```

### 6.5 Audit Logging

**Comprehensive Audit Trail:**

```python
from app.models.audit import AuditLog
from enum import Enum

class AuditAction(Enum):
    JOB_APPLIED = "job.applied"
    EMAIL_SENT = "email.sent"
    CONTACT_ADDED = "contact.added"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_REJECTED = "approval.rejected"
    API_KEY_ACCESSED = "api_key.accessed"
    PII_ACCESSED = "pii.accessed"
    COST_LIMIT_REACHED = "cost.limit_reached"

class AuditLogger:
    """Audit logging for sensitive operations"""
    
    async def log(
        self,
        action: AuditAction,
        user_id: str,
        entity_type: str,
        entity_id: str,
        details: dict,
        ip_address: str = None
    ):
        """Log audit event"""
        audit = AuditLog(
            action=action.value,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=ip_address,
            timestamp=datetime.now()
        )
        
        await audit.save()
        
        # Also log to external service (Phase 2)
        # await self.send_to_siem(audit)

# Usage
audit_logger = AuditLogger()

# Log job application
await audit_logger.log(
    action=AuditAction.JOB_APPLIED,
    user_id=user.id,
    entity_type='job_posting',
    entity_id=job.id,
    details={
        'job_title': job.title,
        'company': job.company,
        'fit_score': job.fit_score
    },
    ip_address=request.client.host
)
```

---

## 7. UI/UX Design

### 7.1 Design System (BRAVOS)

**Color Palette:**

```css
/* Primary - Indigo */
--color-primary-50: #eef2ff;
--color-primary-500: #6366f1;
--color-primary-900: #312e81;

/* Neutral - Slate */
--color-neutral-50: #f8fafc;
--color-neutral-500: #64748b;
--color-neutral-900: #0f172a;

/* Semantic Colors */
--color-success: #10b981;  /* Green */
--color-warning: #f59e0b;  /* Amber */
--color-error: #ef4444;    /* Red */
--color-info: #3b82f6;     /* Blue */
```

**Typography:**

```css
/* Font Families */
--font-sans: 'DM Sans', 'Noto Sans Thai', sans-serif;
--font-mono: 'DM Mono', monospace;

/* Font Sizes */
--text-xs: 0.75rem;    /* 12px */
--text-sm: 0.875rem;   /* 14px */
--text-base: 1rem;     /* 16px */
--text-lg: 1.125rem;   /* 18px */
--text-xl: 1.25rem;    /* 20px */
--text-2xl: 1.5rem;    /* 24px */
--text-3xl: 1.875rem;  /* 30px */
```

### 7.2 Screen Designs

#### 7.2.1 Jobs Screen

```
┌─────────────────────────────────────────────────────────┐
│  BRAVOS                                    [User Menu]   │
├─────────────────────────────────────────────────────────┤
│  Jobs  Contacts  Emails  Tasks  Approvals               │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  🎯 Jobs (150)                                          │
│                                                          │
│  [Filters]  Status: All ▾  Score: 7+ ▾  Source: All ▾  │
│  [Search: "python developer"                        🔍] │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ 🟢 Senior Python Developer                    8.5  │ │
│  │ Tech Corp • Remote • $100k-120k                    │ │
│  │ Python, FastAPI, PostgreSQL, Docker                │ │
│  │ Posted 2 hours ago                                 │ │
│  │ [View Details]  [Apply]                            │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ 🟡 Full Stack Engineer                        7.8  │ │
│  │ Startup Inc • San Francisco • $90k-110k            │ │
│  │ React, Node.js, MongoDB                            │ │
│  │ Posted 5 hours ago                                 │ │
│  │ [View Details]  [Apply]                            │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  [Load More]                                            │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

#### 7.2.2 Contacts Screen

```
┌─────────────────────────────────────────────────────────┐
│  BRAVOS                                    [User Menu]   │
├─────────────────────────────────────────────────────────┤
│  Jobs  Contacts  Emails  Tasks  Approvals               │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  👥 Contacts (85)                                       │
│                                                          │
│  [Filters]  Score: 7+ ▾  Tags: All ▾  Status: All ▾    │
│  [Search: "founder"                                 🔍] │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ 👤 John Doe                                   9.2  │ │
│  │ Founder & CEO @ Startup Inc                        │ │
│  │ San Francisco • 15 mutual connections              │ │
│  │ Tags: founder, saas, investor                      │ │
│  │ Last contact: 3 days ago                           │ │
│  │ [View Profile]  [Send Message]                     │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ 👤 Jane Smith                                 8.5  │ │
│  │ CTO @ Tech Corp                                    │ │
│  │ Remote • 8 mutual connections                      │ │
│  │ Tags: cto, engineering, hiring                     │ │
│  │ Last contact: 1 week ago                           │ │
│  │ [View Profile]  [Send Message]                     │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  [Network Graph]  [Load More]                          │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

#### 7.2.3 Approvals Screen

```
┌─────────────────────────────────────────────────────────┐
│  BRAVOS                                    [User Menu]   │
├─────────────────────────────────────────────────────────┤
│  Jobs  Contacts  Emails  Tasks  Approvals               │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ⏳ Pending Approvals (5)                               │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ 🚨 URGENT • Job Application                        │ │
│  │ Senior Python Developer @ Tech Corp                │ │
│  │                                                     │ │
│  │ Preview:                                            │ │
│  │ ┌──────────────────────────────────────────────┐  │ │
│  │ │ Dear Hiring Manager,                         │  │ │
│  │ │                                              │  │ │
│  │ │ I am excited to apply for the Senior        │  │ │
│  │ │ Python Developer position...                │  │ │
│  │ └──────────────────────────────────────────────┘  │ │
│  │                                                     │ │
│  │ Fit Score: 8.5 • Deadline: 2 days                  │ │
│  │ Requested: 2 hours ago                             │ │
│  │                                                     │ │
│  │ [✅ Approve]  [❌ Reject]  [✏️ Edit]               │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ 📧 Email Reply                                     │ │
│  │ Re: Project Proposal                               │ │
│  │                                                     │ │
│  │ Preview:                                            │ │
│  │ ┌──────────────────────────────────────────────┐  │ │
│  │ │ Hi Sarah,                                    │  │ │
│  │ │                                              │  │ │
│  │ │ Thank you for your email. I would be        │  │ │
│  │ │ happy to discuss...                         │  │ │
│  │ └──────────────────────────────────────────────┘  │ │
│  │                                                     │ │
│  │ Priority: High • Requested: 1 hour ago             │ │
│  │                                                     │ │
│  │ [✅ Approve]  [❌ Reject]  [✏️ Edit]               │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 7.3 Component Library

**Approval Card Component:**

```tsx
// components/ApprovalCard.tsx
import React from 'react';

interface ApprovalCardProps {
  id: string;
  type: 'job' | 'email' | 'outreach';
  title: string;
  preview: string;
  priority: number;
  metadata: Record<string, any>;
  requestedAt: Date;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onEdit: (id: string) => void;
}

export const ApprovalCard: React.FC<ApprovalCardProps> = ({
  id,
  type,
  title,
  preview,
  priority,
  metadata,
  requestedAt,
  onApprove,
  onReject,
  onEdit
}) => {
  const priorityColor = priority >= 9 ? 'red' : priority >= 7 ? 'amber' : 'slate';
  const typeIcon = type === 'job' ? '🎯' : type === 'email' ? '📧' : '👤';
  
  return (
    <div className="approval-card border rounded-lg p-4 bg-white shadow-sm">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-2xl">{typeIcon}</span>
        {priority >= 9 && <span className="text-red-600 font-semibold">URGENT</span>}
        <span className="text-slate-600">•</span>
        <span className="font-medium">{title}</span>
      </div>
      
      <div className="preview bg-slate-50 p-3 rounded mb-3 text-sm">
        <pre className="whitespace-pre-wrap font-sans">{preview}</pre>
      </div>
      
      <div className="metadata text-sm text-slate-600 mb-3">
        {Object.entries(metadata).map(([key, value]) => (
          <span key={key} className="mr-4">
            {key}: {value}
          </span>
        ))}
        <span>Requested: {formatTimeAgo(requestedAt)}</span>
      </div>
      
      <div className="actions flex gap-2">
        <button
          onClick={() => onApprove(id)}
          className="btn btn-success flex-1"
        >
          ✅ Approve
        </button>
        <button
          onClick={() => onReject(id)}
          className="btn btn-error flex-1"
        >
          ❌ Reject
        </button>
        <button
          onClick={() => onEdit(id)}
          className="btn btn-secondary"
        >
          ✏️ Edit
        </button>
      </div>
    </div>
  );
};
```

**Status Badge Component:**

```tsx
// components/StatusBadge.tsx
interface StatusBadgeProps {
  status: 'new' | 'pending' | 'approved' | 'rejected' | 'completed';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const colors = {
    new: 'bg-blue-100 text-blue-800',
    pending: 'bg-amber-100 text-amber-800',
    approved: 'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
    completed: 'bg-slate-100 text-slate-800'
  };
  
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${colors[status]}`}>
      {status.toUpperCase()}
    </span>
  );
};
```

**Budget Pill Component:**

```tsx
// components/BudgetPill.tsx
interface BudgetPillProps {
  spent: number;
  limit: number;
}

export const BudgetPill: React.FC<BudgetPillProps> = ({ spent, limit }) => {
  const percentage = (spent / limit) * 100;
  const color = percentage >= 100 ? 'red' : percentage >= 80 ? 'amber' : 'green';
  
  return (
    <div className={`budget-pill bg-${color}-100 text-${color}-800 px-3 py-1 rounded-full text-sm font-medium`}>
      💰 ${spent.toFixed(2)} / ${limit.toFixed(2)} ({percentage.toFixed(0)}%)
    </div>
  );
};
```

### 7.4 Telegram UI Flows

**Daily Briefing:**

```
🌅 Daily Briefing - Monday, January 15, 2024

📊 Yesterday's Summary:
- Jobs found: 12
- Contacts added: 3
- Emails processed: 45
- Tasks completed: 8

🎯 New Opportunities (5):
1. Senior Python Developer @ Tech Corp (8.5⭐)
   $100k-120k • Remote
   /view_job_123

2. Full Stack Engineer @ Startup Inc (7.8⭐)
   $90k-110k • San Francisco
   /view_job_124

[View All Jobs]

👥 New Contacts (2):
1. John Doe - Founder @ Startup Inc (9.2⭐)
   /view_contact_456

[View All Contacts]

📧 Urgent Emails (1):
1. Client inquiry - Project timeline
   /view_email_789

✅ Tasks Due Today (3):
1. Submit proposal to Client A
2. Follow up with John Doe
3. Review contract

⏳ Pending Approvals (2):
1. Job application - Senior Python Developer
   /approve_req_111

💰 Budget Status:
Spent: $35.50 / $50.00 (71%)
Remaining: $14.50

Have a productive day! 🚀
```

**Approval Request:**

```
🔔 Approval Request

🎯 Job Application
Senior Python Developer @ Tech Corp

Preview:
───────────────────────
Dear Hiring Manager,

I am excited to apply for the Senior Python Developer 
position at Tech Corp. With 5+ years of experience in 
Python development and a strong background in FastAPI 
and PostgreSQL, I believe I would be a great fit...
───────────────────────

Fit Score: 8.5 ⭐
Deadline: 2 days
Requested: 2 hours ago

[✅ Approve] [❌ Reject] [✏️ Edit]
```



---

## 8. Testing Strategy

### 8.1 Unit Tests

**Coverage Target:** >80%

**Test Structure:**

```python
# tests/test_job_hunter.py
import pytest
from app.agents.job_hunter import JobHunterAgent
from app.models.job_posting import JobPosting

class TestJobHunterAgent:
    """Unit tests for Job Hunter Agent"""
    
    @pytest.fixture
    def job_hunter(self, mock_event_bus, mock_scoring_engine):
        return JobHunterAgent(
            event_bus=mock_event_bus,
            scoring_engine=mock_scoring_engine
        )
    
    @pytest.mark.asyncio
    async def test_calculate_hash(self, job_hunter):
        """Test source hash calculation"""
        hash1 = job_hunter._calculate_hash('linkedin', '12345')
        hash2 = job_hunter._calculate_hash('linkedin', '12345')
        hash3 = job_hunter._calculate_hash('linkedin', '67890')
        
        assert hash1 == hash2  # Same input = same hash
        assert hash1 != hash3  # Different input = different hash
        assert len(hash1) == 64  # SHA256 = 64 chars
    
    @pytest.mark.asyncio
    async def test_deduplication(self, job_hunter, db_session):
        """Test job deduplication"""
        # Create job
        job_data = {
            'source': 'linkedin',
            'source_id': '12345',
            'title': 'Python Developer',
            'url': 'https://linkedin.com/jobs/12345'
        }
        
        # First save
        jobs1 = await job_hunter.execute([job_data])
        assert len(jobs1) == 1
        
        # Second save (duplicate)
        jobs2 = await job_hunter.execute([job_data])
        assert len(jobs2) == 0  # Should skip duplicate
        
        # Verify only 1 job in database
        total = await JobPosting.count()
        assert total == 1
    
    @pytest.mark.asyncio
    async def test_fit_score_calculation(self, job_hunter):
        """Test fit score calculation"""
        job_data = {
            'title': 'Senior Python Developer',
            'skills': ['Python', 'FastAPI', 'PostgreSQL'],
            'salary_max': 120000,
            'location': 'Remote'
        }
        
        user_skills = ['Python', 'FastAPI', 'Docker']
        user_identity = {'desired_salary': 100000}
        
        score = await job_hunter.scoring_engine.calculate_fit_score(
            job_data,
            user_skills,
            user_identity
        )
        
        assert 0 <= score <= 10
        assert score >= 7.0  # Should be high score (good match)
    
    @pytest.mark.asyncio
    async def test_event_emission(self, job_hunter, mock_event_bus):
        """Test event emission for high-score jobs"""
        job_data = {
            'source': 'linkedin',
            'source_id': '12345',
            'title': 'Python Developer',
            'url': 'https://linkedin.com/jobs/12345',
            'fit_score': 8.5  # High score
        }
        
        await job_hunter.execute([job_data])
        
        # Verify event was emitted
        assert mock_event_bus.emit.called
        assert mock_event_bus.emit.call_args[0][0] == 'job.found'
```

**Test Coverage by Component:**

| Component | Unit Tests | Integration Tests | Property Tests |
|-----------|-----------|-------------------|----------------|
| Job Hunter | 15 tests | 5 tests | 3 properties |
| Network Builder | 12 tests | 4 tests | 2 properties |
| Email Manager | 18 tests | 6 tests | 4 properties |
| Personal Assistant | 20 tests | 8 tests | 2 properties |
| OpenClaw Integration | 10 tests | 5 tests | 1 property |
| Scrapers | 25 tests (5 per platform) | 10 tests | 5 properties |

### 8.2 Integration Tests

**End-to-End Workflows:**

```python
# tests/integration/test_job_discovery_flow.py
import pytest
from app.agents.job_hunter import JobHunterAgent
from app.scrapers.linkedin import LinkedInJobScraper
from app.core.event_bus import EventBus

@pytest.mark.integration
class TestJobDiscoveryFlow:
    """Integration tests for job discovery workflow"""
    
    @pytest.mark.asyncio
    async def test_full_job_discovery_flow(
        self,
        linkedin_scraper,
        job_hunter,
        event_bus,
        db_session
    ):
        """Test complete flow: scrape → score → save → emit"""
        
        # 1. Scrape jobs
        jobs = await linkedin_scraper.scrape({
            'keywords': 'python developer',
            'location': 'Remote',
            'max_pages': 1
        })
        
        assert len(jobs) > 0
        
        # 2. Process jobs
        saved_jobs = await job_hunter.execute(jobs)
        
        assert len(saved_jobs) > 0
        
        # 3. Verify database
        db_jobs = await JobPosting.get_all()
        assert len(db_jobs) == len(saved_jobs)
        
        # 4. Verify events emitted
        events = event_bus.get_emitted_events('job.found')
        high_score_jobs = [j for j in saved_jobs if j.fit_score >= 7.0]
        assert len(events) == len(high_score_jobs)
    
    @pytest.mark.asyncio
    async def test_approval_flow(
        self,
        job_hunter,
        personal_assistant,
        telegram_bot,
        db_session
    ):
        """Test approval flow for job application"""
        
        # 1. Create high-score job
        job = await JobPosting.create({
            'source': 'linkedin',
            'title': 'Python Developer',
            'fit_score': 8.5,
            'status': 'new'
        })
        
        # 2. Emit job.found event
        await event_bus.emit('job.found', {'job_id': str(job.id)})
        
        # 3. Verify approval request created
        approval = await ApprovalRequest.get_by_entity(job.id)
        assert approval is not None
        assert approval.status == 'pending'
        
        # 4. Verify Telegram notification sent
        assert telegram_bot.send_message.called
        
        # 5. Approve request
        await personal_assistant.handle_approval(approval.id, 'approve')
        
        # 6. Verify submission created
        submission = await Submission.get_by_job(job.id)
        assert submission is not None
        assert submission.status == 'submitted'
```

### 8.3 Property-Based Tests

**Using Hypothesis:**

```python
# tests/property/test_job_hunter_properties.py
from hypothesis import given, strategies as st
import pytest

class TestJobHunterProperties:
    """Property-based tests for Job Hunter"""
    
    @given(
        source=st.sampled_from(['linkedin', 'upwork', 'fastwork']),
        source_id=st.text(min_size=1, max_size=100)
    )
    def test_hash_deterministic(self, job_hunter, source, source_id):
        """Property: Hash calculation is deterministic"""
        hash1 = job_hunter._calculate_hash(source, source_id)
        hash2 = job_hunter._calculate_hash(source, source_id)
        
        assert hash1 == hash2
    
    @given(
        jobs=st.lists(
            st.fixed_dictionaries({
                'source': st.sampled_from(['linkedin', 'upwork']),
                'source_id': st.text(min_size=1, max_size=50),
                'title': st.text(min_size=1, max_size=200),
                'url': st.text(min_size=10, max_size=200)
            }),
            min_size=1,
            max_size=10
        )
    )
    @pytest.mark.asyncio
    async def test_deduplication_idempotent(self, job_hunter, jobs):
        """Property: Deduplication is idempotent"""
        # Process jobs twice
        result1 = await job_hunter.execute(jobs)
        result2 = await job_hunter.execute(jobs)
        
        # Second run should find no new jobs
        assert len(result2) == 0
    
    @given(
        fit_score=st.floats(min_value=0.0, max_value=10.0)
    )
    def test_priority_determination(self, job_hunter, fit_score):
        """Property: Priority determination is consistent"""
        priority = job_hunter._determine_priority(fit_score)
        
        if fit_score >= 8.0:
            assert priority == 'do_now'
        elif fit_score >= 6.0:
            assert priority == 'consider'
        else:
            assert priority == 'skip'

# tests/property/test_email_manager_properties.py
class TestEmailManagerProperties:
    """Property-based tests for Email Manager"""
    
    @given(
        email_text=st.text(min_size=10, max_size=1000)
    )
    @pytest.mark.asyncio
    async def test_categorization_always_returns_valid_category(
        self,
        email_manager,
        email_text
    ):
        """Property: Categorization always returns valid category"""
        email = EmailMessage(body_text=email_text)
        result = await email_manager.categorize_email(email)
        
        valid_categories = ['urgent', 'important', 'normal', 'spam', 'newsletter']
        assert result['category'] in valid_categories
        assert 1 <= result['priority'] <= 10
        assert 0.0 <= result['confidence'] <= 1.0
    
    @given(
        text=st.text(min_size=0, max_size=5000)
    )
    def test_date_extraction_no_false_positives(self, email_manager, text):
        """Property: Date extraction doesn't create false dates"""
        dates = email_manager._extract_dates(text)
        
        # All extracted dates should be valid date strings
        for date in dates:
            assert isinstance(date, str)
            assert len(date) > 0
```

### 8.4 Load Tests

**Using Locust:**

```python
# tests/load/locustfile.py
from locust import HttpUser, task, between

class BRAVOSUser(HttpUser):
    """Load test for BRAVOS API"""
    
    wait_time = between(1, 3)
    
    def on_start(self):
        """Login and get token"""
        response = self.client.post("/api/v1/auth/login", json={
            "username": "test@example.com",
            "password": "password"
        })
        self.token = response.json()['token']
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    @task(3)
    def list_jobs(self):
        """List jobs (most common operation)"""
        self.client.get(
            "/api/v1/jobs?limit=20",
            headers=self.headers
        )
    
    @task(2)
    def list_contacts(self):
        """List contacts"""
        self.client.get(
            "/api/v1/contacts?limit=20",
            headers=self.headers
        )
    
    @task(1)
    def get_dashboard_metrics(self):
        """Get dashboard metrics"""
        self.client.get(
            "/api/v1/metrics/dashboard",
            headers=self.headers
        )
    
    @task(1)
    def approve_request(self):
        """Approve a request"""
        # Get pending approvals
        response = self.client.get(
            "/api/v1/approvals?status=pending&limit=1",
            headers=self.headers
        )
        
        approvals = response.json()['data']
        if approvals:
            approval_id = approvals[0]['id']
            self.client.post(
                f"/api/v1/approvals/{approval_id}/approve",
                headers=self.headers
            )

# Run: locust -f tests/load/locustfile.py --host=http://localhost:8000
```

**Load Test Targets:**

| Metric | Target | Measurement |
|--------|--------|-------------|
| Concurrent Users | 100 | Simultaneous active users |
| Requests/Second | 1000 | Total throughput |
| Response Time (P95) | <200ms | GET endpoints |
| Response Time (P95) | <500ms | POST endpoints |
| Error Rate | <1% | Failed requests |
| Database Connections | <50 | Active connections |

### 8.5 Test Automation

**GitHub Actions CI/CD:**

```yaml
# .github/workflows/test.yml
name: Test Suite

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r backend/requirements.txt
        pip install pytest pytest-asyncio pytest-cov hypothesis
    
    - name: Run migrations
      run: |
        cd backend
        alembic upgrade head
      env:
        DATABASE_URL: postgresql://postgres:postgres@localhost/test_db
    
    - name: Run unit tests
      run: |
        cd backend
        pytest tests/unit -v --cov=app --cov-report=xml
      env:
        DATABASE_URL: postgresql://postgres:postgres@localhost/test_db
        REDIS_URL: redis://localhost:6379
    
    - name: Run integration tests
      run: |
        cd backend
        pytest tests/integration -v
      env:
        DATABASE_URL: postgresql://postgres:postgres@localhost/test_db
        REDIS_URL: redis://localhost:6379
    
    - name: Run property tests
      run: |
        cd backend
        pytest tests/property -v --hypothesis-show-statistics
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./backend/coverage.xml
        fail_ci_if_error: true
```

---

## 9. Deployment Strategy

### 9.1 Infrastructure

**Technology Stack:**

| Component | Technology | Hosting | Cost |
|-----------|-----------|---------|------|
| Backend API | FastAPI + Python 3.11 | Railway | $0-15/month |
| Database | PostgreSQL 15 | Supabase | $0-25/month |
| Cache | Redis 7 | Upstash | $0-10/month |
| Frontend | React + TypeScript | Vercel | $0 |
| Background Jobs | Celery + Redis | Railway | Included |

**Total Infrastructure Cost:** $0-50/month

### 9.2 Environment Configuration

```bash
# .env.production
# Database
DATABASE_URL=postgresql://user:pass@host:5432/bravos_prod
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis
REDIS_URL=redis://user:pass@host:6379/0
REDIS_MAX_CONNECTIONS=50

# OpenClaw
OPENCLAW_API_KEY=encrypted_key_here
OPENCLAW_ENDPOINT=https://api.openclaw.com/v1
OPENCLAW_MONTHLY_BUDGET=50.0

# Gmail
GMAIL_CLIENT_ID=your_client_id
GMAIL_CLIENT_SECRET=encrypted_secret_here

# Telegram
TELEGRAM_BOT_TOKEN=encrypted_token_here
TELEGRAM_WEBHOOK_URL=https://your-domain.com/telegram/webhook

# Gemini
GEMINI_API_KEY=encrypted_key_here
GEMINI_MODEL=gemini-1.5-flash

# Security
MASTER_KEY=your_master_encryption_key
JWT_SECRET=your_jwt_secret
JWT_EXPIRATION=86400

# Monitoring
SENTRY_DSN=https://your-sentry-dsn
LOG_LEVEL=INFO
```

### 9.3 Deployment Process

```bash
# 1. Build Docker image
docker build -t bravos-backend:latest -f backend/Dockerfile .

# 2. Run database migrations
docker run --rm \
  -e DATABASE_URL=$DATABASE_URL \
  bravos-backend:latest \
  alembic upgrade head

# 3. Deploy to Railway
railway up

# 4. Verify deployment
curl https://your-domain.com/health
```

### 9.4 Monitoring & Alerting

**Health Check Endpoint:**

```python
# app/api/system.py
from fastapi import APIRouter
from app.database import database
from app.core.redis_client import redis_client

router = APIRouter()

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    checks = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "checks": {}
    }
    
    # Check database
    try:
        await database.execute("SELECT 1")
        checks["checks"]["database"] = "healthy"
    except Exception as e:
        checks["checks"]["database"] = f"unhealthy: {str(e)}"
        checks["status"] = "unhealthy"
    
    # Check Redis
    try:
        await redis_client.ping()
        checks["checks"]["redis"] = "healthy"
    except Exception as e:
        checks["checks"]["redis"] = f"unhealthy: {str(e)}"
        checks["status"] = "unhealthy"
    
    # Check OpenClaw
    try:
        # Simple ping to OpenClaw
        checks["checks"]["openclaw"] = "healthy"
    except Exception as e:
        checks["checks"]["openclaw"] = f"unhealthy: {str(e)}"
    
    return checks
```

---

## 10. Summary

### 10.1 Key Design Decisions

1. **OpenClaw สำหรับ Anti-Bot Sites** - LinkedIn, Upwork, Fiverr ต้องใช้ browser automation
2. **Redis Cache (4h TTL)** - ลด costs จาก $42-105/month → $30-50/month
3. **EventBus สำหรับ Communication** - loosely coupled, async, retry-able
4. **4-Tier Fallback Strategy** - OpenClaw → Direct Scraper → Cache → Alert User
5. **Approval Flow ผ่าน Telegram** - inline keyboards สำหรับ quick decisions
6. **AES-256 Encryption** - สำหรับ API keys และ PII
7. **Circuit Breaker Pattern** - ป้องกัน cascade failures
8. **Property-Based Testing** - ใช้ Hypothesis สำหรับ comprehensive testing

### 10.2 Success Metrics

**Phase 1 (MVP - Month 1-2):**
- ✅ 50+ jobs found per week
- ✅ 10+ quality contacts per month
- ✅ 95% system uptime
- ✅ <$80/month total cost
- ✅ 10+ hours saved per week

### 10.3 Next Steps

1. **Week 1-2:** Database schema + OpenClaw integration
2. **Week 3-4:** Job Hunter + Enhanced Scrapers
3. **Week 5:** Network Builder + Email Manager (start)
4. **Week 6:** Email Manager (complete) + Personal Assistant
5. **Week 7:** Approval Flow + Infrastructure
6. **Week 8:** Testing + Bug fixes + Documentation

### 10.4 Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| LinkedIn blocks scraping | 4-tier fallback + rate limiting |
| Cost explosion | Hard limits + circuit breaker + alerts |
| Developer burnout | Realistic timeline + MVP focus |
| Scope creep | Strict MoSCoW + phase gates |

---

**Document Version:** 1.0  
**Last Updated:** 2024-01-15  
**Status:** Ready for Implementation

