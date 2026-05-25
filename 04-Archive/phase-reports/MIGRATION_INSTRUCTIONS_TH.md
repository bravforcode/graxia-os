# 🔧 คำแนะนำการรัน Migrations

**วันที่**: 26 เมษายน 2026  
**สถานะ**: ⚠️ **ต้องแก้ไข Database Configuration**

---

## ⚠️ ปัญหาที่พบ

Database configuration ใน `.env` ชี้ไปที่ PostgreSQL ใน Docker:
```
DATABASE_URL=postgresql+asyncpg://personal_os:changeme@postgres:5432/personal_os
```

แต่ตอนนี้ database จริงเป็น **SQLite** ซึ่งไม่รองรับ PostgreSQL extensions (pgcrypto, pgvector, etc.)

---

## ✅ วิธีแก้ไข

### Option 1: ใช้ Supabase (แนะนำ)

คุณมี Supabase credentials อยู่แล้วใน `.env`:
```
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

**แก้ไข `.env`**:
```bash
# เปลี่ยนจาก Docker PostgreSQL
# DATABASE_URL=postgresql+asyncpg://personal_os:changeme@postgres:5432/personal_os

# เป็น Supabase PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres.your-project-ref:YOUR_DB_PASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
DATABASE_MIGRATION_URL=postgresql://postgres.your-project-ref:YOUR_DB_PASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
```

**หา Database Password**:
1. ไปที่ https://supabase.com/dashboard/project/your-project-ref
2. Settings → Database → Connection string
3. Copy password จาก connection string

### Option 2: รัน PostgreSQL ใน Docker

**รัน Docker Compose**:
```bash
docker-compose up -d postgres redis
```

**ตรวจสอบว่า PostgreSQL รันอยู่**:
```bash
docker ps | grep postgres
```

**ทดสอบ connection**:
```bash
docker exec -it graxia-postgres psql -U personal_os -d personal_os
```

---

## 🚀 รัน Migrations (หลังแก้ไข Database)

### 1. ตรวจสอบ current migration:
```bash
cd backend
alembic current
```

### 2. รัน migrations:
```bash
alembic upgrade head
```

### 3. ตรวจสอบว่าสำเร็จ:
```bash
alembic current
# ควรแสดง: 011_add_missing_updated_at_columns (head)
```

---

## 📝 Migration Chain

```
001_enterprise_baseline
  ↓
002_schema_reconciliation
  ↓
003_...
  ↓
004_add_social_auth_columns_to_users
  ↓
005_pgvector
  ↓
4497f1eedc0b_add_multi_agent_orchestration_models
  ↓
89d09d4d6b03_add_performance_indexes
  ↓
007_revenue_os_v10_integration ⭐ NEW
  ↓
008_revenue_os_v10_part2 ⭐ NEW
  ↓
009_revenue_os_v10_part3 ⭐ NEW
  ↓
010_revenue_os_improvements ⭐ NEW
  ↓
011_add_missing_updated_at_columns ⭐ NEW (head)
```

---

## ⚠️ หมายเหตุสำคัญ

### SQLite vs PostgreSQL:
- ❌ **SQLite**: ไม่รองรับ extensions, CHECK constraints บางอย่าง, triggers ซับซ้อน
- ✅ **PostgreSQL**: รองรับครบทุกอย่าง (pgcrypto, pgvector, CHECK constraints, triggers)

### Revenue OS v10 ต้องใช้ PostgreSQL:
- ✅ CHECK constraints สำหรับ data integrity
- ✅ Composite indexes สำหรับ performance
- ✅ JSONB สำหรับ metadata
- ✅ Triggers สำหรับ updated_at
- ✅ UUID primary keys

---

## 🔍 Troubleshooting

### ปัญหา: "near EXTENSION: syntax error"
**สาเหตุ**: ใช้ SQLite แทน PostgreSQL  
**วิธีแก้**: เปลี่ยนไปใช้ Supabase หรือ Docker PostgreSQL

### ปัญหา: "KeyError: '006_revenue_os_round3_fixes'"
**สาเหตุ**: Migration chain ไม่ถูกต้อง  
**วิธีแก้**: ✅ แก้ไขแล้ว (เปลี่ยน down_revision เป็น 89d09d4d6b03)

### ปัญหา: "Connection refused"
**สาเหตุ**: PostgreSQL ไม่ได้รันอยู่  
**วิธีแก้**: รัน `docker-compose up -d postgres` หรือใช้ Supabase

---

## ✅ ขั้นตอนต่อไป (หลังรัน migrations สำเร็จ)

1. ✅ รัน migrations: `alembic upgrade head`
2. ✅ ทดสอบ: `pytest graxia/packages/revenue_os/tests/ -v`
3. ✅ Commit code
4. ✅ ไป Phase 3 - API Layer & Security Hardening

---

**สถานะ**: ⚠️ **รอแก้ไข Database Configuration**  
**แนะนำ**: ใช้ Supabase (มี credentials อยู่แล้ว)
