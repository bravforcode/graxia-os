# Graxia VPS Autopilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ทำให้ Graxia บน VPS 168.222.27.36 รันงานอัตโนมัติได้จริงทุกตัว deploy ซ้ำได้จาก git commit และเตือนเองเมื่อพัง

**Architecture:** repo เป็นแหล่งความจริงเดียวของทุกไฟล์ที่ VPS ใช้ (compose override, deploy script, ops script) image สร้างจาก `git archive` ของ commit เดียว ติด tag เป็น SHA ไม่มีการ copy ไฟล์ทับ image เก่าอีก งาน beat ที่ขาด config จะ skip พร้อมเหตุผลแทนการ raise และ host timer ตรวจอัตรางานล้มแล้วส่ง Telegram

**Tech Stack:** FastAPI, Celery 5 + beat, Redis, Postgres 17 (pgvector), Docker Compose, systemd timers, Caddy, age

**Spec:** ผลสำรวจ VPS แบบอ่านอย่างเดียววันที่ 2026-11-02 (หัวข้อ "หลักฐาน" ด้านล่าง) ร่วมกับแผนเดิม `C:\Users\menum\.claude\plans\wild-nibbling-haven.md`

## TL;DR (อ่านแค่นี้ก็พอ)

1. **ระบบอัตโนมัติพังอยู่ทั้งหมด** ตั้งแต่ 2026-10-29 11:35 UTC งาน beat 15 ใน 17 ชนิดล้มทุกรอบ (392 ครั้งใน 24 ชม.) ด้วย `ValueError: organization_id must come from a trusted tenant context` ไม่มี job ใหม่เข้ามาตั้งแต่ 2026-10-29 07:34
2. **ต้นเหตุ:** `config.py` ใน image `20261029-aligned` ประกาศ `LEGACY_ORGANIZATION_ID` สองครั้ง บรรทัด 391 (`str = ""`) ทับบรรทัด 158 (`UUID`) ค่าจึงเป็น `str` และ `_require_organization_id` ปฏิเสธ ใน repo ไม่มีบรรทัดซ้ำนี้ image ที่รันอยู่จึงไม่ตรงกับ repo
3. **ต้นเหตุของต้นเหตุ:** deploy ทำโดย copy ไฟล์ทีละตัวเข้าโฟลเดอร์ `build-*` แล้ว build ทับ image เก่า ไม่มี commit ผูกไว้ แก้ที่กระบวนการ deploy ไม่ใช่แค่ที่บรรทัดนั้น
4. ลำดับงาน: Task 1 ถึง 3 ทำให้ระบบกลับมาทำงานและ deploy ซ้ำได้ Task 4 ถึง 7 ทำให้ไม่พังเงียบอีก Task 8 เป็นงานบน VPS ที่ต้องได้ "yes"

## หลักฐาน (สำรวจ 2026-11-02 11:34 UTC)

| เรื่อง | ค่าจริง | สถานะ |
|---|---|---|
| Disk `/` | 41G/48G (87%) | เตือน |
| Image reclaimable | 15.67GB, build cache 4.85GB | ลบได้หลังอนุมัติ |
| graxia image เก่า | 3 tag x 1.56GB (`celery-openai`, `celery-linkedin-dedupe`, `celery-career-org`) | ไม่ได้ใช้ |
| Container graxia | 6 ตัว up, restart 0, OOM 0 | ดี |
| Healthcheck | celery และ frontend ไม่มี | ขาด |
| Log rotation | graxia ทุกตัวไม่มี `max-size` (windmill และ stocknomist มี) | ขาด |
| Celery ping | `pong`, 1 node | ดี |
| `/health/live`, `/health/ready` | 404 (image เก่ากว่า repo) | ขาด |
| Beat → Celery | 15/17 ชนิดงาน raise, `check_dlq_depth` บอก depth 0 ทั้งที่งานล้ม | **P0** |
| `job_postings` | 20 แถว, ล่าสุด 2026-10-29 07:34, มี score ครบ 20 | หยุดเติม |
| Backup host | `graxia-backup.timer` สำเร็จทุกวันตั้งแต่ 30 ต.ค. dump `graxia-production` ด้วย, age encrypt, เก็บ 7 วัน + 4 สัปดาห์ | ดี |
| Offsite | Windows task `GraxiaPcBackupPull` ดึงถึง `20261101T202244Z`, result 0 | ดี |
| Restore drill | ไม่เคยทำ | ขาด |
| Backup ฝั่ง celery | `tasks.backup.run_daily_backup`, `run_redis_backup` raise | ซ้ำกับ host |
| Env ว่าง | Google OAuth 3 ตัว, `RESEND_API_KEY`, Stripe ทั้งหมด, Supabase, `BACKUP_*` | งานที่พึ่งพาจะล้มต่อ |
| Kernel | รัน 6.8.0-142, ติดตั้งแล้ว 6.8.0-147, `/var/run/reboot-required` มี | รอ reboot |
| SSH | root key-only, password off, fail2ban jail `sshd` | ดี |
| ufw | 22/80/443 เปิด, 8000 deny ยกเว้น bridge windmill | ดี |
| PC agent | `GraxiaPcAgent` หยุดตั้งแต่ 2026-10-30 (0xC000013A) | ตรวจ |
| ไฟล์บน VPS | `/opt/graxia-os` ไม่ใช่ git repo, override `.bak-*` 13 ไฟล์, `.env.production.*` 6 ไฟล์ | drift |

## Global Constraints

- ไม่แตะ Sanso (`sanso-prod-*`) ในคำสั่ง prune, restart, firewall ใดๆ
- ห้ามพิมพ์ค่า secret ทุกคำสั่งพิมพ์ได้เฉพาะชื่อ key
- งานบน VPS ที่เปลี่ยนสถานะ (deploy, restart, prune, reboot, แก้ systemd) ต้องได้ "yes" จากผู้ใช้ทุกครั้ง ติดป้าย **[APPROVAL]**
- ห้าม push จนกว่าผู้ใช้อนุมัติ commit อยู่บน branch `chore/prod-readiness`
- ไม่ restart docker daemon (กระทบ windmill/stocknomist/sanso) log rotation ทำผ่าน `logging:` ต่อ service แทน
- backend test: `cd backend && python -m pytest <path> -q` failed ที่ยอมรับได้มีแค่ 3 ตัวที่รู้แล้ว (`test_alertmanager_webhook_accepts_bearer_token_and_formats_alert`, `test_auto_org_creation_for_new_user`, `test_bearer_token_fallback_when_no_secret`)
- SSH ใช้ alias `opportunity-vps` กับ `-o BatchMode=yes`

---

### Task 1: กันไม่ให้ Settings ประกาศ field ซ้ำ (P0 regression guard)

**Files:**
- Test: `backend/tests/test_settings_schema.py` (ใหม่)

**Interfaces:**
- Consumes: `app.config.settings`, class `Settings` ใน `backend/app/config.py`
- Produces: test ที่ล้มเมื่อมี field ซ้ำ หรือ `LEGACY_ORGANIZATION_ID` ไม่ใช่ `UUID`

- [ ] **Step 1: เขียน test**

```python
import ast
from pathlib import Path
from uuid import UUID

from app.config import settings

CONFIG_PATH = Path(__file__).resolve().parents[1] / "app" / "config.py"


def _settings_field_names() -> list[str]:
    tree = ast.parse(CONFIG_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            return [
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            ]
    raise AssertionError("class Settings not found in app/config.py")


def test_settings_fields_are_declared_once():
    names = _settings_field_names()
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert duplicates == [], f"duplicate Settings fields override each other: {duplicates}"


def test_legacy_organization_id_is_uuid():
    assert isinstance(settings.LEGACY_ORGANIZATION_ID, UUID)
```

- [ ] **Step 2: รัน test บน repo**

Run: `cd backend && python -m pytest tests/test_settings_schema.py -q`
Expected: PASS ทั้งสอง (repo ไม่มีบรรทัดซ้ำ) ถ้า `test_settings_fields_are_declared_once` ล้ม ให้ลบบรรทัดที่ซ้ำโดยเก็บตัวที่ type ถูก แล้วรันซ้ำ

- [ ] **Step 3: พิสูจน์ว่า test จับบั๊กจริง**

Run: `ssh -o BatchMode=yes opportunity-vps 'docker exec graxia_prod_celery cat /app/app/config.py' > /tmp/image_config.py && cd backend && python - <<'PY'
import ast
names=[s.target.id for n in ast.parse(open('/tmp/image_config.py',encoding='utf-8').read()).body if isinstance(n,ast.ClassDef) and n.name=='Settings' for s in n.body if isinstance(s,ast.AnnAssign) and isinstance(s.target,ast.Name)]
print(sorted({x for x in names if names.count(x)>1}))
PY`
Expected: รายการมี `LEGACY_ORGANIZATION_ID` (logic เดียวกับ test ล้มกับไฟล์ใน image)

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_settings_schema.py
git commit -m "test(config): fail on duplicate Settings fields and non-UUID legacy org"
```

---

### Task 2: นำไฟล์ deploy ของ VPS เข้า repo และเพิ่ม healthcheck กับ log limit

**Files:**
- Create: `deploy/vps/docker-compose.base.yml` (copy จาก `/opt/graxia-os/docker-compose.yml` ไฟล์นี้ต่างจาก `docker-compose.yml` ที่ root ของ repo ซึ่งใช้ PORT 8080 จึงแยกเก็บ)
- Create: `deploy/vps/docker-compose.production.override.yml` (copy จาก VPS แล้วแก้)
- Create: `deploy/vps/graxia-backup` (copy จาก `/usr/local/sbin/graxia-backup`)
- Create: `deploy/vps/graxia-vitals` (copy จาก `/usr/local/bin/graxia-vitals`)
- Create: `.gitattributes`
- Delete: `ops/backup-graxia.sh` (ซ้ำกับ `graxia-backup` ที่ dump `graxia-production` อยู่แล้ว)
- Test: `backend/tests/test_vps_compose.py` (ใหม่, ใช้ PyYAML ไม่ต้องมี docker บนเครื่อง dev)

**Interfaces:**
- Produces: override ที่ใช้ `${GRAXIA_BACKEND_TAG:?}` และ `${PRODUCTION_TAG:?}` แทน tag ที่ hardcode, ทุก service มี `healthcheck` และ `logging` ให้ Task 3 ใช้

- [ ] **Step 1: ดึงไฟล์จาก VPS**

```bash
mkdir -p deploy/vps
scp -o BatchMode=yes opportunity-vps:/opt/graxia-os/docker-compose.yml deploy/vps/docker-compose.base.yml
scp -o BatchMode=yes opportunity-vps:/opt/graxia-os/docker-compose.production.override.yml deploy/vps/
scp -o BatchMode=yes opportunity-vps:/usr/local/sbin/graxia-backup deploy/vps/
scp -o BatchMode=yes opportunity-vps:/usr/local/bin/graxia-vitals deploy/vps/
```

- [ ] **Step 2: ตรวจว่าไม่มีค่า secret ติดมา**

Run: `grep -nE '(PASSWORD|SECRET|TOKEN|KEY)[A-Z_]*[:=] *[^$ {]' deploy/vps/*`
Expected: ไม่มีผลลัพธ์ (ทุกค่าเป็น `${VAR}`) ถ้ามี ให้แทนด้วย `${VAR}` ก่อนไปต่อ

- [ ] **Step 3: เขียน failing test**

`backend/tests/test_vps_compose.py`:

```python
from pathlib import Path

import pytest
import yaml

VPS_DIR = Path(__file__).resolve().parents[2] / "deploy" / "vps"
SERVICES = ("postgres", "redis", "backend", "frontend", "celery", "beat")


def _merged_services() -> dict:
    base = yaml.safe_load((VPS_DIR / "docker-compose.base.yml").read_text(encoding="utf-8"))
    override = yaml.safe_load((VPS_DIR / "docker-compose.production.override.yml").read_text(encoding="utf-8"))
    services = {name: dict(spec or {}) for name, spec in base.get("services", {}).items()}
    for name, spec in override.get("services", {}).items():
        services.setdefault(name, {}).update(spec or {})
    return services


@pytest.mark.parametrize("service", SERVICES)
def test_service_has_healthcheck(service):
    assert _merged_services()[service].get("healthcheck", {}).get("test"), f"{service} has no healthcheck"


@pytest.mark.parametrize("service", SERVICES)
def test_service_has_log_limit(service):
    options = _merged_services()[service].get("logging", {}).get("options", {})
    assert options.get("max-size"), f"{service} logs grow without limit"


def test_backend_image_tag_comes_from_env():
    for service in ("backend", "celery", "beat"):
        image = _merged_services()[service]["image"]
        assert image.startswith("graxia-backend:${GRAXIA_BACKEND_TAG"), f"{service} pins {image}"
```

Run: `cd backend && python -m pytest tests/test_vps_compose.py -q`
Expected: FAIL ที่ healthcheck ของ celery และ frontend, log limit ทุก service, และ image tag ที่ hardcode

- [ ] **Step 4: แก้ override**

ใน `deploy/vps/docker-compose.production.override.yml`:

1. แทน `image: graxia-backend:20261029-aligned` ทั้ง 3 จุด (backend, celery, beat) ด้วย `image: graxia-backend:${GRAXIA_BACKEND_TAG:?GRAXIA_BACKEND_TAG is required}`
2. backend healthcheck เปลี่ยน test เป็น `["CMD", "curl", "-f", "http://localhost:8000/health/live"]`
3. เพิ่มใน celery:

```yaml
    healthcheck:
      test: ["CMD-SHELL", "celery -A app.tasks.celery_app inspect ping -d celery@$$HOSTNAME --timeout 5"]
      interval: 60s
      timeout: 15s
      retries: 3
      start_period: 30s
```

4. เพิ่มใน frontend (image เป็น nginx alpine ฟัง 8080 ตาม port map `19080->8080`):

```yaml
    healthcheck:
      test: ["CMD-SHELL", "wget -qO /dev/null http://127.0.0.1:8080/ || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
```

5. เพิ่ม anchor ด้านบนไฟล์และอ้างในทุก service (postgres, redis, backend, frontend, celery, beat, n8n):

```yaml
x-logging: &default-logging
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
    compress: "true"
```

แต่ละ service: `    logging: *default-logging`

- [ ] **Step 5: รัน test ให้ผ่าน แล้วตรวจกับ docker จริงบน VPS (อ่านอย่างเดียว)**

Run: `cd backend && python -m pytest tests/test_vps_compose.py -q`
Expected: PASS ทั้งหมด

Run: `scp deploy/vps/docker-compose.production.override.yml opportunity-vps:/tmp/override.check.yml && ssh -o BatchMode=yes opportunity-vps 'cd /opt/graxia-os && GRAXIA_BACKEND_TAG=20261029-aligned docker compose -f docker-compose.yml -f /tmp/override.check.yml config --quiet && echo valid; rm -f /tmp/override.check.yml'`
Expected: `valid` (ไม่เปลี่ยน container ใดๆ)

- [ ] **Step 6: กัน CRLF ใน shell script**

`.gitattributes`:

```
*.sh text eol=lf
deploy/vps/graxia-backup text eol=lf
deploy/vps/graxia-vitals text eol=lf
```

Run: `git rm ops/backup-graxia.sh && git add --renormalize .`

- [ ] **Step 7: Commit**

```bash
git add .gitattributes deploy/vps/ backend/tests/test_vps_compose.py
git commit -m "chore(deploy): track VPS compose and ops scripts, add healthchecks and log limits"
```

---

### Task 3: Deploy จาก git SHA พร้อม auto-rollback

**Files:**
- Create: `deploy/vps/deploy.sh`
- Modify: `scripts/deploy.sh` (ให้เรียก `deploy/vps/deploy.sh` หรือลบถ้าไม่มีคนใช้ ตรวจด้วย `grep -rn "scripts/deploy.sh" .github docs`)

**Interfaces:**
- Consumes: override จาก Task 2 (`GRAXIA_BACKEND_TAG`)
- Produces: คำสั่งเดียว `deploy/vps/deploy.sh <git-ref>` ที่ Task 8 และ CI ใช้, เขียน `/opt/graxia-os/DEPLOYED_SHA`

- [ ] **Step 1: เขียน script**

`deploy/vps/deploy.sh` (รันบนเครื่อง dev):

```bash
#!/usr/bin/env bash
# Build graxia-backend from one git commit on the VPS and roll back if health fails.
set -euo pipefail
ref="${1:-HEAD}"
host="${GRAXIA_VPS:-opportunity-vps}"
sha=$(git rev-parse --short=12 "$ref")
[ -z "$(git status --porcelain -- backend deploy/vps)" ] || { echo "backend/ or deploy/vps has uncommitted changes" >&2; exit 1; }

echo "deploy $sha to $host"
git archive --format=tar "$sha" backend deploy/vps | ssh -o BatchMode=yes "$host" "
  set -euo pipefail
  src=/opt/graxia-os/releases/$sha
  rm -rf \"\$src\" && mkdir -p \"\$src\" && tar -x -C \"\$src\"
  docker build -q -t graxia-backend:$sha --label org.opencontainers.image.revision=$sha \"\$src/backend\"
  cd /opt/graxia-os
  cp docker-compose.yml docker-compose.yml.prev
  cp docker-compose.production.override.yml docker-compose.production.override.yml.prev
  cp \"\$src/deploy/vps/docker-compose.base.yml\" docker-compose.yml
  cp \"\$src/deploy/vps/docker-compose.production.override.yml\" docker-compose.production.override.yml
  prev=\$(cat DEPLOYED_SHA 2>/dev/null || docker inspect -f '{{.Config.Image}}' graxia_prod_backend | cut -d: -f2)
  export GRAXIA_BACKEND_TAG=$sha
  docker compose -p graxia-production -f docker-compose.yml -f docker-compose.production.override.yml config --quiet
  docker compose -p graxia-production -f docker-compose.yml -f docker-compose.production.override.yml up -d --no-deps backend celery beat
  for i in \$(seq 1 30); do
    b=\$(docker inspect -f '{{.State.Health.Status}}' graxia_prod_backend)
    c=\$(docker inspect -f '{{.State.Health.Status}}' graxia_prod_celery)
    [ \"\$b\" = healthy ] && [ \"\$c\" = healthy ] && { echo $sha > DEPLOYED_SHA; echo ok; exit 0; }
    sleep 10
  done
  echo 'health failed, rolling back to' \"\$prev\" >&2
  cp docker-compose.yml.prev docker-compose.yml
  cp docker-compose.production.override.yml.prev docker-compose.production.override.yml
  GRAXIA_BACKEND_TAG=\"\$prev\" docker compose -p graxia-production -f docker-compose.yml -f docker-compose.production.override.yml up -d --no-deps backend celery beat
  exit 1
"
```

หมายเหตุ: rollback ครั้งแรกใช้ `prev` = `20261029-aligned` (อ่านจาก container เพราะยังไม่มี `DEPLOYED_SHA`) ซึ่งยังมีบั๊ก P0 อยู่ rollback จึงแค่คืนสถานะเดิม ไม่ได้แย่ลง

- [ ] **Step 2: ตรวจ syntax**

Run: `bash -n deploy/vps/deploy.sh && shellcheck deploy/vps/deploy.sh`
Expected: exit 0 (ถ้าไม่มี shellcheck ให้ข้าม พร้อมบันทึก)

- [ ] **Step 3: [APPROVAL] deploy ครั้งแรก**

ถามผู้ใช้ก่อน: "deploy commit `<sha>` ไป VPS (recreate backend, celery, beat ประมาณ 1 นาที) ไหม"
Run: `bash deploy/vps/deploy.sh HEAD`
Expected: `ok` และ exit 0

- [ ] **Step 4: ยืนยันว่า automation กลับมา**

Run: `ssh -o BatchMode=yes opportunity-vps 'sleep 900; docker logs --since 15m graxia_prod_celery 2>&1 | grep -c "trusted tenant context"; docker logs --since 15m graxia_prod_celery 2>&1 | grep -oE "Task [a-z_.]+ (succeeded|raised)" | sort | uniq -c'`
Expected: บรรทัดแรก `0` และ `tasks.daily_scan.run succeeded` อย่างน้อยหนึ่งครั้ง

- [ ] **Step 5: Commit**

```bash
git add deploy/vps/deploy.sh scripts/deploy.sh
git commit -m "feat(deploy): build backend image from git SHA with health-gated rollback"
```

---

### Task 4: งาน beat ที่ขาด config ต้อง skip ไม่ใช่ raise

**Files:**
- Create: `backend/app/tasks/requirements.py`
- Modify: `backend/app/tasks/base.py:66-92` (`_execute_managed_run`)
- Test: `backend/tests/test_task_requirements.py`

**Interfaces:**
- Produces: `TASK_REQUIREMENTS: dict[str, tuple[str, ...]]`, `missing_settings(task_name: str) -> list[str]`, และผลคืนของงานที่ถูก skip `{"status": "skipped", "reason": "missing_config", "missing": [...]}`

- [ ] **Step 1: หา task_name จริง**

Run: `cd backend && grep -rn "task_name=" app/tasks | grep -v "def "`
บันทึกชื่อ task ของ email_processing, outreach.email, vault_sync, crm.sync, morning_briefing, follow_up_check และใช้ชื่อนั้นตรงตัวใน Step 3

- [ ] **Step 2: เขียน failing test**

```python
import asyncio

from app.config import settings
from app.tasks import base
from app.tasks.requirements import TASK_REQUIREMENTS, missing_settings


def test_missing_settings_lists_empty_keys(monkeypatch):
    monkeypatch.setitem(TASK_REQUIREMENTS, "tasks.demo.run", ("RESEND_API_KEY",))
    monkeypatch.setattr(settings, "RESEND_API_KEY", "", raising=False)
    assert missing_settings("tasks.demo.run") == ["RESEND_API_KEY"]


def test_unknown_task_has_no_requirements():
    assert missing_settings("tasks.not_registered.run") == []


def test_managed_run_skips_without_creating_run(monkeypatch):
    monkeypatch.setitem(TASK_REQUIREMENTS, "tasks.demo.run", ("RESEND_API_KEY",))
    monkeypatch.setattr(settings, "RESEND_API_KEY", "", raising=False)
    created = []

    async def fake_create_run(**kwargs):
        created.append(kwargs)

    monkeypatch.setattr(base, "create_run", fake_create_run)

    async def never_called():
        raise AssertionError("coroutine must not run when config is missing")

    result = asyncio.run(base._execute_managed_run("tasks.demo.run", "default", never_called, "scheduler"))
    assert result == {"status": "skipped", "reason": "missing_config", "missing": ["RESEND_API_KEY"]}
    assert created == []
```

Run: `cd backend && python -m pytest tests/test_task_requirements.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'app.tasks.requirements'`

- [ ] **Step 3: เขียน registry**

`backend/app/tasks/requirements.py` (แทนชื่อ task ด้วยค่าที่ได้จาก Step 1):

```python
"""Settings each scheduled task needs before it can do useful work."""
from __future__ import annotations

from app.config import settings

TASK_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "tasks.email_processing.run": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"),
    "tasks.outreach.email": ("RESEND_API_KEY",),
    "tasks.follow_up_check.run": ("RESEND_API_KEY",),
    "tasks.vault_sync.run": ("OBSIDIAN_API_URL", "OBSIDIAN_API_KEY"),
}


def missing_settings(task_name: str) -> list[str]:
    return [key for key in TASK_REQUIREMENTS.get(task_name, ()) if not str(getattr(settings, key, "") or "").strip()]
```

- [ ] **Step 4: ใช้ใน `_execute_managed_run`**

เพิ่ม import `from app.tasks.requirements import missing_settings` และบรรทัดแรกของ `_execute_managed_run`:

```python
    missing = missing_settings(task_name)
    if missing:
        logger.warning("Task %s skipped: missing config %s", task_name, ", ".join(missing))
        return {"status": "skipped", "reason": "missing_config", "missing": missing}
```

- [ ] **Step 5: รัน test**

Run: `cd backend && python -m pytest tests/test_task_requirements.py tests/test_settings_schema.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/tasks/requirements.py backend/app/tasks/base.py backend/tests/test_task_requirements.py
git commit -m "fix(tasks): skip scheduled tasks with missing config instead of raising"
```

---

### Task 5: เอา backup ฝั่ง celery ออกจาก beat

host timer `graxia-backup` ทำ pg_dump + age + offsite อยู่แล้วและสำเร็จทุกวัน งานใน celery ซ้ำและล้ม

**Files:**
- Modify: `backend/app/tasks/celery_app.py` หรือไฟล์ที่นิยาม `BEAT_SCHEDULE` (หาด้วย `grep -rn "daily-backup\|redis-backup" backend/app`)
- Test: `backend/tests/test_beat_schedule.py`

- [ ] **Step 1: failing test**

```python
from app.tasks.celery_app import BEAT_SCHEDULE


def test_backups_run_on_host_not_in_beat():
    tasks = {entry["task"] for entry in BEAT_SCHEDULE.values()}
    assert "tasks.backup.run_daily_backup" not in tasks
    assert "tasks.backup.run_redis_backup" not in tasks
```

Run: `cd backend && python -m pytest tests/test_beat_schedule.py -q`
Expected: FAIL

- [ ] **Step 2: ลบ entry `daily-backup` และ `redis-backup` จาก `BEAT_SCHEDULE`** (ไม่ลบโค้ด task เพื่อให้เรียกมือได้)

- [ ] **Step 3: รัน test**

Run: `cd backend && python -m pytest tests/test_beat_schedule.py -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/tasks backend/tests/test_beat_schedule.py
git commit -m "chore(beat): drop in-app backups; host graxia-backup timer owns backups"
```

---

### Task 6: เตือนเมื่องานอัตโนมัติล้ม (host-side)

ตอนนี้งานล้ม 392 ครั้งต่อวันโดยไม่มีใครรู้ และ `check_dlq_depth` รายงาน 0 ตัวเช็คต้องอยู่นอก celery เพื่อให้ยังเตือนได้ตอน celery ตาย

**Files:**
- Create: `deploy/vps/graxia-autopilot-check` (bash)
- Create: `deploy/vps/systemd/graxia-autopilot-check.service`, `deploy/vps/systemd/graxia-autopilot-check.timer`
- Test: `deploy/vps/test-autopilot-check.sh`

**Interfaces:**
- Consumes: ตาราง `automation_runs` (มี `status`, `created_at`, `task_type`), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` ใน `/opt/graxia-os/.env.production`
- Produces: exit 0 เมื่อปกติ, exit 2 และส่ง Telegram เมื่อผิดปกติ

- [ ] **Step 1: ยืนยันชื่อคอลัมน์**

Run: `ssh -o BatchMode=yes opportunity-vps 'docker exec graxia_prod_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"select status, count(*) from automation_runs group by 1\""'`
Expected: เห็นค่า status เช่น `failed`, `completed` ถ้าชื่อคอลัมน์ต่าง ให้แก้ SQL ใน Step 2

- [ ] **Step 2: เขียน script**

```bash
#!/usr/bin/env bash
# Alert on Telegram when graxia automation fails or stalls. Reads secrets from the env file only.
set -euo pipefail
ENV_FILE="${GRAXIA_ENV_FILE:-/opt/graxia-os/.env.production}"
WINDOW="${GRAXIA_CHECK_WINDOW:-1 hour}"
MAX_FAILED_RATIO="${GRAXIA_MAX_FAILED_PCT:-20}"
PSQL="${GRAXIA_PSQL:-docker exec graxia_prod_postgres sh -c}"
DISK_MAX_PCT="${GRAXIA_DISK_MAX_PCT:-85}"

q() { $PSQL "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"$1\""; }

read -r total failed < <(q "select count(*), count(*) filter (where status='failed') from automation_runs where created_at > now() - interval '$WINDOW'" | tr '|' ' ')
problems=()
[ "$total" -eq 0 ] && problems+=("no automation runs in last $WINDOW")
[ "$total" -gt 0 ] && [ $((failed * 100 / total)) -gt "$MAX_FAILED_RATIO" ] && problems+=("$failed/$total runs failed in last $WINDOW")
for c in graxia_prod_backend graxia_prod_celery graxia_prod_beat graxia_prod_postgres graxia_prod_redis graxia_prod_frontend; do
  h=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$c" 2>/dev/null || echo missing)
  case "$h" in healthy|running) ;; *) problems+=("$c is $h") ;; esac
done
disk=$(df -P / | awk 'NR==2 {print $5}' | tr -d %)
[ "$disk" -ge "$DISK_MAX_PCT" ] && problems+=("disk / at ${disk}%")

[ ${#problems[@]} -eq 0 ] && { echo ok; exit 0; }
msg="Graxia autopilot alert: $(IFS='; '; echo "${problems[*]}")"
echo "$msg"
token=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | cut -d= -f2-)
chat=$(grep -E '^TELEGRAM_CHAT_ID=' "$ENV_FILE" | cut -d= -f2-)
curl -fsS -m 15 "https://api.telegram.org/bot${token}/sendMessage" --data-urlencode "chat_id=${chat}" --data-urlencode "text=${msg}" >/dev/null
exit 2
```

- [ ] **Step 3: test ด้วย psql และ docker ปลอม**

`deploy/vps/test-autopilot-check.sh`:

```bash
#!/usr/bin/env bash
set -u
dir=$(mktemp -d); trap 'rm -rf "$dir"' EXIT
mkdir -p "$dir/bin"
cat > "$dir/bin/docker" <<'EOF'
#!/usr/bin/env bash
[ "$1" = inspect ] && { echo healthy; exit 0; }
EOF
cat > "$dir/bin/curl" <<'EOF'
#!/usr/bin/env bash
echo sent >> "$CURL_LOG"
EOF
cat > "$dir/bin/psql-fake" <<'EOF'
#!/usr/bin/env bash
echo "$FAKE_ROW"
EOF
chmod +x "$dir/bin/"*
printf 'TELEGRAM_BOT_TOKEN=t\nTELEGRAM_CHAT_ID=1\n' > "$dir/env"
run() {
  FAKE_ROW="$1" CURL_LOG="$dir/curl.log" PATH="$dir/bin:$PATH" GRAXIA_ENV_FILE="$dir/env" \
    GRAXIA_PSQL=psql-fake GRAXIA_DISK_MAX_PCT=101 bash deploy/vps/graxia-autopilot-check >/dev/null
  echo $?
}
[ "$(run '10|0')" = 0 ] || { echo "FAIL healthy case"; exit 1; }
[ "$(run '10|9')" = 2 ] || { echo "FAIL failure-ratio case"; exit 1; }
[ "$(run '0|0')" = 2 ] || { echo "FAIL stalled case"; exit 1; }
[ "$(wc -l < "$dir/curl.log" | tr -d ' ')" = 2 ] || { echo "FAIL alert count"; exit 1; }
echo PASS
```

Run: `bash deploy/vps/test-autopilot-check.sh` (รันใน Git Bash หรือบน VPS)
Expected: `PASS`

- [ ] **Step 4: systemd units**

`graxia-autopilot-check.service`:

```ini
[Unit]
Description=Graxia autopilot health check (alerts Telegram)
After=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/graxia-autopilot-check
SuccessExitStatus=2
```

`graxia-autopilot-check.timer`:

```ini
[Unit]
Description=Graxia autopilot health check every 15 minutes

[Timer]
OnBootSec=10min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
```

- [ ] **Step 5: Commit**

```bash
git add deploy/vps/graxia-autopilot-check deploy/vps/test-autopilot-check.sh deploy/vps/systemd/
git commit -m "feat(ops): host-side autopilot failure and stall alert via Telegram"
```

- [ ] **Step 6: [APPROVAL] ติดตั้งบน VPS**

```bash
scp deploy/vps/graxia-autopilot-check opportunity-vps:/usr/local/sbin/
scp deploy/vps/systemd/graxia-autopilot-check.* opportunity-vps:/etc/systemd/system/
ssh opportunity-vps 'chmod 750 /usr/local/sbin/graxia-autopilot-check && systemctl daemon-reload && systemctl enable --now graxia-autopilot-check.timer && systemctl start graxia-autopilot-check.service; systemctl status graxia-autopilot-check.service --no-pager | tail -3'
```

Expected: ก่อน Task 3 deploy จะได้ข้อความเตือนใน Telegram (เป็นหลักฐานว่าตัวเตือนทำงาน) หลัง deploy ได้ `ok`

---

### Task 7: Restore drill ที่รันซ้ำได้

**Files:**
- Create: `deploy/vps/restore-drill.sh`
- Create: `docs/runbook/backup-restore.md`

**Interfaces:**
- Consumes: ไฟล์ `graxia-production.dump` ที่ถอด age แล้ว (private key ไม่อยู่บน VPS ผู้ใช้ถอดเองบนเครื่องที่ถือ key)
- Produces: ตาราง row count ของ production เทียบกับ drill และเวลาที่ใช้ (RTO)

- [ ] **Step 1: เขียน script**

```bash
#!/usr/bin/env bash
# Restore a graxia dump into a throwaway container and compare row counts with production.
set -euo pipefail
dump="${1:?usage: restore-drill.sh <graxia-production.dump>}"
name="graxia_restore_drill_$$"
start=$(date +%s)
docker run -d --rm --name "$name" -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=graxia pgvector/pgvector:pg17 >/dev/null
trap 'docker stop "$name" >/dev/null 2>&1 || true' EXIT
until docker exec "$name" pg_isready -U postgres -d graxia >/dev/null 2>&1; do sleep 1; done
docker exec -i "$name" pg_restore -U postgres -d graxia --no-owner --no-acl < "$dump"
sql="select relname||'|'||n_live_tup from pg_stat_user_tables order by 1"
docker exec "$name" psql -U postgres -d graxia -Atc "analyze" >/dev/null
docker exec "$name" psql -U postgres -d graxia -Atc "$sql" > /tmp/drill.counts
docker exec graxia_prod_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"$sql\"" > /tmp/prod.counts
echo "rto_seconds=$(( $(date +%s) - start ))"
diff /tmp/prod.counts /tmp/drill.counts && echo "row counts match" || echo "row counts differ (expected only for rows written after the dump)"
```

- [ ] **Step 2: เขียน runbook** `docs/runbook/backup-restore.md` ระบุ: backup อยู่ที่ `/var/backups/graxia/<stamp>/graxia-production.dump.age`, offsite ที่ `C:\graxia\offsite-backups`, คำสั่งถอด `age -d -i <key> -o graxia-production.dump graxia-production.dump.age`, คำสั่ง drill, และทำซ้ำทุกวันที่ 1 ของเดือน

- [ ] **Step 3: Commit**

```bash
git add deploy/vps/restore-drill.sh docs/runbook/backup-restore.md
git commit -m "feat(ops): repeatable restore drill and backup runbook"
```

- [ ] **Step 4: [APPROVAL + HUMAN] รัน drill** ผู้ใช้ถอด age บนเครื่องที่มี key แล้ว `scp` dump ไป VPS ที่ `/root/drill/` จากนั้นรัน `bash restore-drill.sh /root/drill/graxia-production.dump` แล้วลบไฟล์ dump ที่ถอดแล้ว

---

### Task 8: งานบน VPS (ทุกข้อ [APPROVAL])

- [ ] **8.1 ลบ image และ build cache ของ graxia ที่ไม่ใช้** (คืนพื้นที่ราว 4.7GB image + 4.85GB cache)

```bash
ssh opportunity-vps 'docker rmi graxia-backend:20261029-celery-openai graxia-backend:20261029-celery-linkedin-dedupe graxia-backend:20261028-celery-career-org && docker builder prune -f && df -h /'
```

ไม่ใช้ `docker image prune -a` เพราะจะโดน image ของ Sanso ที่หยุดอยู่ หลัง Task 3 สำเร็จ 48 ชม. ค่อยลบ `graxia-backend:20261029-aligned`

- [ ] **8.2 เก็บไฟล์ `.bak-*` และ `build-*`** ย้ายเข้า `/opt/graxia-os/archive/2026-11-02/` (ไม่ลบ) เพื่อให้เหลือเฉพาะไฟล์ที่ใช้งาน

- [ ] **8.3 Reboot เพื่อใช้ kernel 6.8.0-147** ในช่วงที่ผู้ใช้กำหนด แจ้ง Sanso/Windmill/Stocknomist ก่อน หลัง reboot ตรวจ `docker ps` ว่าทุก container กลับมา (restart policy `unless-stopped` ทั้งหมด) และ `systemctl --failed` ว่าง

- [ ] **8.4 ตรวจ `GraxiaPcAgent`** บน PC (หยุดตั้งแต่ 2026-10-30 ผลลัพธ์ 0xC000013A) รัน `Start-ScheduledTask GraxiaPcAgent` แล้วดู `LastTaskResult`

---

### Task 9: Soak 48 ชม. และปิดงาน

- [ ] **Step 1:** หลัง Task 3 deploy ครบ 48 ชม. รัน

```bash
ssh -o BatchMode=yes opportunity-vps 'docker logs --since 48h graxia_prod_celery 2>&1 | grep -oE "Task [a-z_.]+ (succeeded|raised)" | sort | uniq -c; docker exec graxia_prod_postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"select count(*), max(created_at) from job_postings\""; journalctl -u graxia-autopilot-check --since -48h --no-pager | grep -c alert; df -h /'
```

Expected: ไม่มี `raised` ยกเว้นงานภายนอกที่ล้มเพราะ site ปลายทาง (บันทึกเป็น known), `job_postings.max(created_at)` อยู่ในช่วง 48 ชม., alert 0, disk ต่ำกว่า 80%

- [ ] **Step 2:** บันทึกผลใน `.wolf/memory.md` และ `backend/.wolf/buglog.json` (bug: duplicate Settings field ทำให้ beat ล้ม 2026-10-29 ถึงวัน deploy)

---

## นอกแผนนี้ (ต้องให้ผู้ใช้ตัดสิน)

- เติม env ที่ว่าง (Google OAuth, Resend, Stripe) งานที่พึ่งพาจะ skip พร้อมเหตุผลจนกว่าจะเติม ไม่ล้มแล้ว
- push branch, ลบ `deploy-flyio.yml`, เปิด branch protection
- scraper ภายนอกที่โดน 403/404 (upwork, fiverr, fastwork) เป็นปัญหาฝั่งปลายทาง
- comfyui และ clipauto เป็นคนละโปรเจกต์
