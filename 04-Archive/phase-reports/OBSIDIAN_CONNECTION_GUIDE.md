# 🔗 OBSIDIAN CONNECTION GUIDE

**วันที่:** 2026-04-26  
**สถานะ:** ⚠️ API Plugin ยังไม่เปิด แต่ Filesystem Access พร้อมใช้งาน

---

## 📊 สถานะปัจจุบัน

### ✅ สิ่งที่พร้อมใช้งาน

1. **Filesystem Access** ✅
   - Path: `C:\Users\menum\OneDrive\Documents\Gracia\Second Brain`
   - Root Folder: `Second Brain`
   - Status: ✅ Accessible

2. **Symlink to Skills** ✅
   - Path: `.claude/skills-universal`
   - Target: `C:\Users\menum\Documents\ObsidianVault\Second Brain\brain\skills-universal`
   - Status: ✅ Working

3. **Configuration in .env** ✅
   ```bash
   OBSIDIAN_VAULT_PATH=C:\Users\menum\OneDrive\Documents\Gracia
   OBSIDIAN_ROOT_FOLDER=Second Brain
   OBSIDIAN_AUTO_BOOTSTRAP=true
   OBSIDIAN_AUTO_SYNC_ENABLED=true
   OBSIDIAN_API_URL=http://localhost:27123
   OBSIDIAN_API_KEY=72261506ea20cd103c79008a109cc546ffacc56d6a154e613d3677bd99fa8f188
   ```

### ⚠️ สิ่งที่ยังไม่พร้อม

1. **Obsidian Local REST API Plugin** ❌
   - Port: 27123
   - Status: ❌ Not running
   - Error: `Failed to connect to localhost port 27123`

---

## 🔧 วิธีเปิดใช้งาน Obsidian Local REST API

### Step 1: ติดตั้ง Plugin

1. เปิด Obsidian
2. ไปที่ Settings → Community Plugins
3. ปิด Safe Mode (ถ้ายังเปิดอยู่)
4. คลิก Browse
5. ค้นหา "Local REST API"
6. คลิก Install
7. คลิก Enable

### Step 2: Configure Plugin

1. ไปที่ Settings → Local REST API
2. Enable API
3. Set API Key: `72261506ea20cd103c79008a109cc546ffacc56d6a154e613d3677bd99fa8f188`
4. Set Port: `27123` (default)
5. Enable CORS (ถ้าต้องการ)

### Step 3: ทดสอบการเชื่อมต่อ

```bash
# Test connection
curl -H "Authorization: Bearer 72261506ea20cd103c79008a109cc546ffacc56d6a154e613d3677bd99fa8f188" http://localhost:27123/vault/

# Expected response: List of files in vault
```

---

## 🎯 สิ่งที่ทำได้ตอนนี้ (โดยไม่ต้องมี API Plugin)

### 1. อ่านไฟล์จาก Vault ✅

Backend สามารถอ่านไฟล์จาก vault ได้โดยตรงผ่าน filesystem:

```python
# backend/app/integrations/obsidian.py
from pathlib import Path

vault_path = Path("C:/Users/menum/OneDrive/Documents/Gracia/Second Brain")
note_path = vault_path / "brain" / "latest.md"

with open(note_path, "r", encoding="utf-8") as f:
    content = f.read()
```

### 2. เขียนไฟล์ไปยัง Vault ✅

```python
# Create new note
note_path = vault_path / "brain" / "Projects" / "Graxia-OS" / "notes.md"
note_path.parent.mkdir(parents=True, exist_ok=True)

with open(note_path, "w", encoding="utf-8") as f:
    f.write("# Graxia OS Notes\n\n...")
```

### 3. Sync Opportunities/Submissions/Contacts ✅

Backend มี Obsidian sync agent ที่ทำงานได้แล้ว:

```python
# backend/app/agents/obsidian_sync.py
from app.agents.obsidian_sync import obsidian_sync_agent

# Sync opportunity
await obsidian_sync_agent.sync_opportunity(opportunity_id)

# Sync submission
await obsidian_sync_agent.sync_submission(submission_id)

# Sync contact
await obsidian_sync_agent.sync_contact(contact_id)
```

### 4. Bootstrap Second Brain ✅

```python
# Create vault structure
await obsidian_sync_agent.bootstrap_second_brain()
```

---

## 📝 สิ่งที่ต้องมี API Plugin

### ❌ Real-time Updates

ถ้าต้องการให้ Obsidian update ทันทีเมื่อมีการเปลี่ยนแปลง ต้องใช้ API Plugin

### ❌ Bidirectional Sync

ถ้าต้องการให้ Obsidian ส่งข้อมูลกลับมาที่ backend ต้องใช้ API Plugin

### ❌ Remote Access

ถ้าต้องการเข้าถึง vault จากเครื่องอื่น ต้องใช้ API Plugin

---

## 🚀 Quick Start (ไม่ต้องมี API Plugin)

### 1. Test Obsidian Integration

```bash
# Start backend
cd backend
python -c "
from app.agents.obsidian_sync import obsidian_sync_agent
import asyncio

async def test():
    result = await obsidian_sync_agent.bootstrap_second_brain()
    print('Bootstrap result:', result)

asyncio.run(test())
"
```

### 2. Sync Data to Obsidian

```bash
# Start backend API
make run-local

# Trigger sync via API
curl -X POST http://localhost:8000/obsidian/bootstrap

# Check vault
# Open: C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\brain
```

### 3. Auto-sync on Events

Backend จะ auto-sync เมื่อมี events:
- `opportunity.found` → sync to Obsidian
- `submission.sent` → sync to Obsidian
- `contact.created` → sync to Obsidian
- `task.created` → sync to Obsidian

---

## 🔍 ตรวจสอบ Vault Structure

### Expected Structure

```
C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\
└── brain/
    ├── Atlas.md
    ├── Dashboard.md
    ├── System/
    │   ├── Identity.md
    │   ├── Voice.md
    │   └── Constraints.md
    ├── Projects/
    │   ├── Index.md
    │   └── [project-name]/
    │       ├── Overview.md
    │       ├── Context.md
    │       ├── Activity Log.md
    │       └── Tasks.md
    ├── Skills/
    │   ├── Index.md
    │   └── [skill-name].md
    ├── Operations/
    │   ├── Opportunities/
    │   ├── Submissions/
    │   └── Tasks/
    ├── CRM/
    │   └── Contacts/
    ├── Knowledge/
    │   ├── Playbooks/
    │   └── Failure Analyses/
    └── Journal/
        ├── Daily/
        └── Weekly/
```

---

## 🎯 Recommended Actions

### Option 1: ใช้ Filesystem Access (แนะนำตอนนี้)

✅ **Pros:**
- ทำงานได้ทันที
- ไม่ต้องติดตั้งอะไรเพิ่ม
- เร็วกว่า API

❌ **Cons:**
- ไม่มี real-time updates
- ต้อง refresh Obsidian manually

**Setup:**
```bash
# Already configured in .env
# Just start backend and it will work
make run-local
```

### Option 2: เปิดใช้งาน API Plugin (สำหรับ advanced features)

✅ **Pros:**
- Real-time updates
- Bidirectional sync
- Remote access

❌ **Cons:**
- ต้องติดตั้ง plugin
- ต้อง configure

**Setup:**
1. ติดตั้ง Local REST API plugin ใน Obsidian
2. Configure API key และ port
3. Restart backend
4. Test connection

---

## 🧪 Testing Commands

### Test 1: Check Vault Path

```bash
# Windows PowerShell
Test-Path "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain"
# Expected: True
```

### Test 2: List Files

```bash
# Windows PowerShell
Get-ChildItem "C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\brain" -Recurse | Select-Object FullName
```

### Test 3: Test Backend Integration

```bash
cd backend
python -c "
from app.integrations.obsidian import ObsidianConnector
import asyncio

async def test():
    connector = ObsidianConnector(
        vault_path='C:/Users/menum/OneDrive/Documents/Gracia/Second Brain',
        root_folder='brain'
    )
    
    # Test write
    await connector.write_note(
        'test-note',
        '# Test Note\n\nThis is a test.',
        folder='',
        overwrite=True
    )
    print('✅ Write test passed')
    
    # Test read
    content = await connector.read_note('test-note', folder='')
    print('✅ Read test passed')
    print('Content:', content[:50])

asyncio.run(test())
"
```

---

## 📚 API Endpoints (เมื่อ backend ทำงาน)

### Bootstrap Vault

```bash
POST /obsidian/bootstrap
```

### Sync Opportunity

```bash
POST /obsidian/sync
{
  "entity_type": "opportunity",
  "entity_id": "uuid-here"
}
```

### Create Daily Note

```bash
POST /obsidian/daily-note
```

### Create Weekly Review

```bash
POST /obsidian/weekly-review
```

---

## ✅ สรุป

### สถานะปัจจุบัน
- ✅ Filesystem access พร้อมใช้งาน
- ✅ Backend integration พร้อมใช้งาน
- ✅ Auto-sync configured
- ⚠️ API Plugin ยังไม่เปิด (optional)

### แนะนำ
1. ใช้ filesystem access ก่อน (ทำงานได้แล้ว)
2. ติดตั้ง API Plugin ภายหลัง (ถ้าต้องการ real-time updates)
3. Test bootstrap และ sync ผ่าน backend API

### Next Steps
1. Start backend: `make run-local`
2. Test bootstrap: `curl -X POST http://localhost:8000/obsidian/bootstrap`
3. Check vault: เปิด Obsidian และดูโครงสร้างที่ถูกสร้าง
4. (Optional) ติดตั้ง Local REST API plugin

---

**พร้อมใช้งานแล้ว!** Backend สามารถเชื่อมต่อกับ Obsidian vault ได้ผ่าน filesystem
