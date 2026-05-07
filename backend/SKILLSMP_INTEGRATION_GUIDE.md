# SkillsMP Integration Guide

## Overview

ระบบ SkillsMP Integration ช่วยให้ AI ของคุณสามารถดึงสกิลจาก SkillsMP.com ผ่าน API โดยอัตโนมัติ เรียนรู้จากการใช้งาน และพัฒนาตนเองได้

## Features

### 1. Auto-Sync (ดึงสกิลอัตโนมัติ)
- รันทุกชั่วโมง (cron job)
- Merge strategy: เพิ่มใหม่, อัปเดตที่มีอยู่, ไม่ลบ (mark as deleted แทน)
- รองรับทุกประเภท: openclaw, claude, codex, hermes, tool, dev, context

### 2. AI Learning Engine (ระบบเรียนรู้)
- **Self-Improvement**: AI ปรับปรุงสกิลที่ใช้งานไม่ดีอัตโนมัติ
- **Skill Creation**: สร้างสกิลใหม่จาก pattern ที่สำเร็จ
- **Usage Tracking**: ติดตาม effectiveness, success rate

### 3. Recommendation Engine (ระบบแนะนำ)
- **Context-Aware**: แนะนำสกิลตาม context งาน
- **RAG Search**: ค้นหา semantic ด้วย TF-IDF + embeddings
- **Skill Chains**: แนะนำลำดับสกิลที่ใช้ร่วมกันได้ดี

### 4. API Access (A+B+C)
- **A) Direct Invoke**: `/api/v1/skillsmp/invoke` - เรียกสกิลผ่าน AI
- **B) Content Access**: `/api/v1/skillsmp/skills/{id}/content` - ดึง content ใส่ prompt
- **C) RAG Search**: `/api/v1/skillsmp/search` - ค้นหาแบบ semantic

## Configuration

```env
# .env file
SKILLSMP_API_KEY=sk_live_skillsmp_50boeaOxQlnfIT5_BkpdUGTVPBp5KAWyAHI72sn7gAA
SKILLSMP_BASE_URL=https://api.skillsmp.com/v1
SKILLSMP_AUTO_SYNC=true
SKILLSMP_SYNC_INTERVAL_MINUTES=60
```

## Database Schema

### skillsmp_skills
- `external_id`: ID จาก SkillsMP
- `source_type`: openclaw, claude, codex, hermes, tool, dev, context
- `name`, `description`, `content`: เนื้อหาสกิล
- `skill_metadata`: JSONB metadata
- `usage_count`, `success_rate`, `effectiveness_score`: สถิติการใช้งาน
- `ai_improved_version`: เนื้อหาที่ AI ปรับปรุง
- `context_tags`, `trigger_patterns`: สำหรับ recommendation
- `version`, `previous_versions`: version control

### skill_learning_log
- บันทึกการเรียนรู้ทั้งหมด (usage, improvement, creation)

### skill_invocations
- บันทึกการเรียกใช้สกิลแต่ละครั้ง

## API Endpoints

### List Skills
```http
GET /api/v1/skillsmp/skills?skill_type=claude&min_effectiveness=50
```

### Get Skill Content
```http
GET /api/v1/skillsmp/skills/{id}/content?prefer_improved=true
```

### Invoke Skill (A)
```http
POST /api/v1/skillsmp/invoke
{
  "skill_id": "uuid",
  "task": "เขียนโค้ด Python สำหรับ...",
  "context": "Project X",
  "prefer_improved": true
}
```

### Search Skills (C - RAG)
```http
POST /api/v1/skillsmp/search
{
  "query": "การจัดการ database",
  "context": "ต้องการ optimize PostgreSQL",
  "limit": 5
}
```

### Recommend Skills
```http
POST /api/v1/skillsmp/recommend
{
  "task_context": "สร้าง REST API ด้วย FastAPI",
  "preferred_types": ["python", "backend"],
  "limit": 5
}
```

### Submit Feedback
```http
POST /api/v1/skillsmp/skills/{id}/feedback
{
  "rating": 4,
  "feedback_text": "สกิลนี้ช่วยได้มาก",
  "context": "ใช้กับงานจริง"
}
```

### Trigger Sync
```http
POST /api/v1/skillsmp/sync/trigger
```

### Get Sync Status
```http
GET /api/v1/skillsmp/sync/status
```

### Analyze Skills
```http
POST /api/v1/skillsmp/analyze
{
  "skill_type": "claude",
  "min_usage": 5,
  "generate_improvements": true
}
```

## Scheduler Jobs

| Job | Schedule | Description |
|-----|----------|-------------|
| skillsmp_hourly_sync | ทุกชั่วโมง (:00) | Sync สกิลจาก SkillsMP |
| skill_daily_improvement | ทุกวัน 02:00 AM | AI ปรับปรุงสกิลที่ไม่ดี |

## Auto-Learning Flow

1. **Usage Recording**: ทุกครั้งที่ invoke สกิล → บันทึก usage + outcome
2. **Effectiveness Calculation**: คำนวณ score จาก success rate + usage + feedback
3. **Auto-Improvement Trigger**: ถ้า effectiveness ต่ำ + usage มากพอ → AI สร้าง improved version
4. **Skill Creation**: ถ้าเจอ pattern ที่สำเร็จซ้ำๆ → AI สร้างสกิลใหม่
5. **Recommendation Learning**: บันทึกว่า skill ไหนแนะนำแล้วสำเร็จ

## Files Created

```
backend/
├── alembic/versions/
│   └── 013_add_skillsmp_integration.py  # Migration
├── app/
│   ├── models/
│   │   └── skillsmp_skill.py            # Models
│   ├── schemas/
│   │   └── skillsmp.py                  # Pydantic schemas
│   ├── api/
│   │   └── skillsmp.py                  # API endpoints
│   ├── integrations/
│   │   └── skillsmp_client.py           # API client
│   ├── jobs/
│   │   ├── skillsmp_sync.py             # Sync job
│   │   └── scheduler.py                 # Scheduler
│   └── core/
│       ├── skill_learning_engine.py     # AI learning
│       └── skill_recommender.py         # Recommendation
```

## Testing

```bash
# Run migrations
alembic upgrade head

# Test API (after starting server)
curl http://localhost:8000/api/v1/skillsmp/sync/status

# Trigger manual sync
curl -X POST http://localhost:8000/api/v1/skillsmp/sync/trigger
```

## Future Enhancements

1. **Vector Embeddings**: Store content embeddings สำหรับ semantic search ที่แม่นยำกว่า
2. **Skill Composition**: รวมสกิลหลายอันเป็น workflow
3. **Multi-Agent Skill Sharing**: สกิลที่สร้างโดย agent หนึ่งใช้กับ agent อื่นได้
4. **Skill Marketplace**: แชร์สกิลที่สร้างเองกลับไปยัง SkillsMP
