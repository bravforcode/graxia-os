# 🔧 CRITICAL FIXES IMPLEMENTATION GUIDE

## แก้ไขปัญหาเร่งด่วนทั้งหมดในไฟล์เดียว

---

## FIX #1: Backend Import Error (CRIT-01)

### ไฟล์: `backend/app/main.py`

**ปัญหา:** `ModuleNotFoundError: No module named 'core'`

**วิธีแก้ที่ 1: เพิ่ม PYTHONPATH (แนะนำ)**

สร้างไฟล์ `backend/.env.local`:
```bash
PYTHONPATH=${PYTHONPATH}:${PWD}/..
```

แก้ `backend/Dockerfile`:
```dockerfile
# เพิ่มบรรทัดนี้
ENV PYTHONPATH=/app:${PYTHONPATH}
```

แก้ `docker-compose.yml`:
```yaml
backend:
  environment:
    PYTHONPATH: /app:/app/..
```

**วิธีแก้ที่ 2: Conditional Import (ปลอดภัยกว่า)**

แก้ `backend/app/main.py` lines 59-67:
```python
# Graxia OS Integration (Optional)
GRAXIA_ENABLED = os.getenv("GRAXIA_ENABLED", "false").lower() == "true"

if GRAXIA_ENABLED:
    try:
        import sys
        from pathlib import Path
        # Add parent directory to path
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        
        from core.ingestion.pipeline import AutoIngestionPipeline
        from core.chunking.semantic_chunker import SemanticChunker
        from core.retrieval.graph_rag import EntityExtractor
        from core.providers.openai_provider import OpenAIEmbeddingProvider, OpenAIProvider
        from core.execution.message_bus import message_bus, AgentMessage
        from core.routing.task_delegator import ChiefOrchestrator
        from core.execution.real_swarm import RealSwarmOrchestrator
        
        logger.info("Graxia OS components loaded successfully")
    except ImportError as e:
        logger.warning(f"Graxia OS components not available: {e}")
        logger.warning("Running in Brav OS standalone mode")
        GRAXIA_ENABLED = False
else:
    logger.info("Graxia OS disabled, running in Brav OS standalone mode")

# Shared Swarm Engine (only if Graxia enabled)
if GRAXIA_ENABLED:
    swarm = RealSwarmOrchestrator()
    chief = ChiefOrchestrator()
else:
    swarm = None
    chief = None
```

แก้ `initialize_graxia_components()` function:
```python
async def initialize_graxia_components():
    """Initializes Graxia OS background services and components."""
    if not GRAXIA_ENABLED:
        logger.info("Graxia OS disabled, skipping initialization")
        return None
        
    logger.info("Initializing Graxia OS Intelligence components...")
    
    try:
        # ... existing code ...
    except Exception as e:
        logger.error(f"Failed to initialize Graxia OS components: {e}")
        return None
```

แก้ Graxia endpoints:
```python
@app.post("/v1/graxia/execute", dependencies=[Depends(api_key_security)])
async def execute_graxia_task(request: SwarmTaskRequest, background_tasks: BackgroundTasks):
    """Activates the Graxia Swarm for a specific project goal."""
    if not GRAXIA_ENABLED or chief is None:
        raise HTTPException(
            status_code=503,
            detail="Graxia OS is not enabled or not available"
        )
    
    background_tasks.add_task(safe_execute_project, request.project_description)
    return {
        "status": "success", 
        "message": "Graxia Swarm activated. Watch progress via /v1/graxia/stream WebSocket."
    }
```

---

## FIX #2: Missing Environment Variables (CRIT-06)

### ไฟล์: `backend/app/config.py`

เพิ่ม fields ใน `Settings` class (หลัง line 100):
```python
class Settings(BaseSettings):
    # ... existing fields ...
    
    # ── Graxia OS Configuration ────────────────────────────────────────────
    GRAXIA_ENABLED: bool = False
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-small"
    DEFAULT_LLM_MODEL: str = "gpt-4o-mini"
    OPENAI_API_KEY: str = ""
    
    # ... rest of existing fields ...
```

เพิ่มใน `.env.example`:
```bash
# ── Graxia OS (Optional) ──────────────────────────────────────────────────
GRAXIA_ENABLED=false
DEFAULT_EMBEDDING_MODEL=text-embedding-3-small
DEFAULT_LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=
```

---

## FIX #3: Celery Tasks Import Errors (CRIT-07)

### ไฟล์: `backend/app/tasks/celery_app.py`

แก้ include list:
```python
celery_app = Celery(
    "personal_os",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.daily_scan",
        "app.tasks.morning_briefing",
        "app.tasks.follow_up_check",
        "app.tasks.job_discovery",
        "app.tasks.email_processing",
        "app.tasks.weekly_review",
        "app.tasks.maintenance_tasks",
        "app.tasks.backup_tasks",
        "app.tasks.vault_sync",
        "app.tasks.outreach_tasks",
        "app.tasks.leadgen_tasks",
        "app.tasks.crm_sync_tasks",
        # "app.tasks.agent_tasks",  # ❌ ลบออกถ้าไม่มีไฟล์
    ],
)
```

### ไฟล์: `backend/app/tasks/schedule.py`

ลบหรือ comment tasks ที่ไม่มีไฟล์:
```python
BEAT_SCHEDULE = {
    # ... existing tasks ...
    
    # "weekly-cog-evolution": {  # ❌ Comment ออกถ้าไม่มีไฟล์
    #     "task": "tasks.cog_evolution.run",
    #     "schedule": crontab(day_of_week="sunday", hour=10, minute=0),
    #     "options": {"queue": DEFAULT_QUEUE},
    # },
    
    # ... rest of tasks ...
}
```

---

## FIX #4: Database Session Management (CRIT-03)

### ไฟล์: `graxia/packages/revenue_os/db.py`

แก้ให้ใช้ backend session factory:
```python
"""
graxia/packages/revenue_os/db.py
Unified database session management - uses backend session factory
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Import from backend to ensure single source of truth
try:
    from backend.app.database import get_db_session as _backend_get_db_session
    from backend.app.database import get_db as _backend_get_db
    
    # Re-export for compatibility
    get_db_session = _backend_get_db_session
    get_db = _backend_get_db
    
    logger.info("Using backend database session factory")
except ImportError:
    logger.warning("Backend database module not available, using fallback")
    
    # Fallback implementation (same as before)
    import os
    from sqlalchemy.ext.asyncio import (
        async_sessionmaker,
        create_async_engine,
    )
    
    def _get_database_url() -> str:
        url = os.getenv("DATABASE_URL")
        if not url:
            env = os.getenv("APP_ENV", "development")
            if env == "production":
                raise RuntimeError(
                    "DATABASE_URL environment variable is required in production."
                )
            return "postgresql+asyncpg://graxia:graxia@localhost:5432/graxia_dev"
        return url
    
    _DATABASE_URL: str | None = None
    
    def _get_or_init_database_url() -> str:
        global _DATABASE_URL
        if _DATABASE_URL is None:
            _DATABASE_URL = _get_database_url()
        return _DATABASE_URL
    
    _engine = None
    _AsyncSessionLocal = None
    
    def _get_engine():
        global _engine, _AsyncSessionLocal
        if _engine is None:
            database_url = _get_or_init_database_url()
            _engine = create_async_engine(
                database_url,
                pool_size=int(os.getenv("DATABASE_POOL_SIZE", "10")),
                max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "20")),
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=os.getenv("APP_ENV") == "development",
            )
            _AsyncSessionLocal = async_sessionmaker(
                _engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return _engine
    
    def _get_sessionmaker():
        _get_engine()
        return _AsyncSessionLocal
    
    @asynccontextmanager
    async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
        """Fallback session factory"""
        async with _get_sessionmaker()() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    async def get_db() -> AsyncGenerator[AsyncSession, None]:
        """Fallback FastAPI dependency"""
        async with get_db_session() as session:
            yield session
```

---

## FIX #5: Security Improvements (HIGH-04)

### ไฟล์: `backend/app/main.py`

เพิ่ม rate limiting และ validation สำหรับ Graxia endpoints:
```python
from fastapi import HTTPException, status
from app.middleware.rate_limit import rate_limit

@app.post("/v1/graxia/execute", dependencies=[Depends(api_key_security)])
@rate_limit(max_requests=10, window_seconds=3600)  # 10 requests per hour
async def execute_graxia_task(
    request: SwarmTaskRequest, 
    background_tasks: BackgroundTasks,
    api_key: str = Depends(api_key_security)
):
    """Activates the Graxia Swarm for a specific project goal."""
    if not GRAXIA_ENABLED or chief is None:
        raise HTTPException(
            status_code=503,
            detail="Graxia OS is not enabled or not available"
        )
    
    # Validate request
    if len(request.project_description) > 50000:
        raise HTTPException(
            status_code=400,
            detail="Project description too long (max 50000 characters)"
        )
    
    # Log API usage
    logger.info(
        "graxia_task_requested",
        api_key=api_key[:8] + "...",
        description_length=len(request.project_description)
    )
    
    background_tasks.add_task(safe_execute_project, request.project_description)
    return {
        "status": "success", 
        "message": "Graxia Swarm activated. Watch progress via /v1/graxia/stream WebSocket."
    }

@app.post("/v1/graxia/approve/{task_id}", dependencies=[Depends(api_key_security)])
@rate_limit(max_requests=100, window_seconds=3600)  # 100 approvals per hour
async def approve_graxia_task(
    task_id: str, 
    request: ApprovalResponse,
    api_key: str = Depends(api_key_security)
):
    """Provides manual approval for a high-risk swarm task."""
    if not GRAXIA_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Graxia OS is not enabled"
        )
    
    # Validate task_id format
    if not task_id or len(task_id) > 100:
        raise HTTPException(
            status_code=400,
            detail="Invalid task_id"
        )
    
    # Validate approval status
    if request.status not in ["approved", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail="Status must be 'approved' or 'rejected'"
        )
    
    # Log approval
    logger.info(
        "graxia_approval",
        task_id=task_id,
        status=request.status,
        api_key=api_key[:8] + "..."
    )
    
    msg = AgentMessage(
        sender="UserAPI",
        receiver="System",
        topic=f"approvals/{task_id}",
        content={"status": request.status}
    )
    await message_bus.publish(f"approvals/{task_id}", msg)
    return {
        "status": "success", 
        "message": f"Approval {request.status} sent for task {task_id}"
    }
```

### ไฟล์: `.env.example`

แก้ default passwords:
```bash
# ❌ เก่า
ADMIN_DEFAULT_PASSWORD=changeme
POSTGRES_PASSWORD=changeme

# ✅ ใหม่
ADMIN_DEFAULT_PASSWORD=  # Generate strong password
POSTGRES_PASSWORD=  # Generate strong password
REDIS_PASSWORD=  # Generate strong password
```

เพิ่ม script สำหรับ generate passwords:
```bash
# scripts/generate_secrets.sh
#!/bin/bash
echo "ADMIN_DEFAULT_PASSWORD=$(openssl rand -base64 32)"
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)"
echo "REDIS_PASSWORD=$(openssl rand -base64 32)"
echo "SECRET_KEY=$(openssl rand -base64 64)"
echo "ENCRYPTION_KEY=$(openssl rand -base64 32)"
```

---

## FIX #6: Add Missing Celery Task Files

### สร้างไฟล์: `backend/app/tasks/cog_evolution.py`

```python
"""
Cognitive evolution task - analyzes system performance and suggests improvements
"""
import logging
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(name="tasks.cog_evolution.run")
async def run_cog_evolution():
    """Analyze system performance and suggest cognitive improvements"""
    logger.info("Running cognitive evolution analysis")
    
    # TODO: Implement cognitive evolution logic
    # 1. Analyze recent opportunities and scoring accuracy
    # 2. Analyze submission success rates
    # 3. Suggest scoring weight adjustments
    # 4. Create approval request for weight changes
    
    logger.info("Cognitive evolution analysis completed")
    return {"status": "completed", "suggestions": []}
```

---

## QUICK START SCRIPT

สร้างไฟล์ `scripts/apply_critical_fixes.sh`:
```bash
#!/bin/bash
set -e

echo "🔧 Applying critical fixes..."

# 1. Backup current files
echo "📦 Creating backups..."
cp backend/app/main.py backend/app/main.py.backup
cp backend/app/config.py backend/app/config.py.backup
cp backend/app/tasks/celery_app.py backend/app/tasks/celery_app.py.backup

# 2. Generate secrets
echo "🔐 Generating secrets..."
bash scripts/generate_secrets.sh > .env.secrets
echo "✅ Secrets generated in .env.secrets - please add to .env"

# 3. Create missing task files
echo "📝 Creating missing task files..."
mkdir -p backend/app/tasks
touch backend/app/tasks/cog_evolution.py

# 4. Update environment
echo "🌍 Updating environment..."
if ! grep -q "GRAXIA_ENABLED" .env; then
    echo "GRAXIA_ENABLED=false" >> .env
    echo "DEFAULT_EMBEDDING_MODEL=text-embedding-3-small" >> .env
    echo "DEFAULT_LLM_MODEL=gpt-4o-mini" >> .env
fi

echo "✅ Critical fixes applied!"
echo ""
echo "⚠️  MANUAL STEPS REQUIRED:"
echo "1. Review and apply code changes from CRITICAL_FIXES_IMPLEMENTATION.md"
echo "2. Add generated secrets from .env.secrets to .env"
echo "3. Test backend startup: cd backend && python -c 'from app.main import app'"
echo "4. Run tests: make test-local"
```

---

## VERIFICATION CHECKLIST

หลังจากแก้ไขแล้ว ให้ทดสอบ:

```bash
# 1. Test backend import
cd backend
python -c "from app.main import app; print('✅ Backend imports successfully')"

# 2. Test database connection
python -c "from app.database import AsyncSessionLocal; print('✅ Database session factory works')"

# 3. Test Celery
celery -A app.tasks.celery_app inspect ping

# 4. Test API
make up
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/system/health

# 5. Run tests
make test-local
```

---

## ROLLBACK PLAN

ถ้าเกิดปัญหา:
```bash
# Restore backups
cp backend/app/main.py.backup backend/app/main.py
cp backend/app/config.py.backup backend/app/config.py
cp backend/app/tasks/celery_app.py.backup backend/app/tasks/celery_app.py

# Restart services
make down
make up
```
