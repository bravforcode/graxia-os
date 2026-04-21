# Obsidian API แบบใช้ได้ทุกโปรเจกต์ (Windows + Docker)

## 1) เปิด Obsidian Local REST API (ใน Obsidian)
- Obsidian → Settings → Community plugins → Browse → ติดตั้ง/Enable “Local REST API”
- ในหน้าตั้งค่าปลั๊กอิน:
  - Start/Enable server
  - ดู Port (ตัวอย่าง 27124)
  - Copy API Key

## 2) ตั้งค่าให้ container เข้า host ได้
ใน Docker container ให้ใช้ `host.docker.internal` แทน `127.0.0.1`
- `OBSIDIAN_API_URL=https://host.docker.internal:27124`
- `OBSIDIAN_API_KEY=<your key>`
- ถ้าเป็น https แบบ self-signed: `OBSIDIAN_API_VERIFY_SSL=false`

## 3) ทำให้ใช้ “ทุกโปรเจกต์” โดยไม่ต้องก็อป .env
รันสคริปต์นี้ครั้งเดียว:
- `powershell -ExecutionPolicy Bypass -File .\\scripts\\setup_global_obsidian_env.ps1`

สคริปต์จะสร้างไฟล์:
- `%USERPROFILE%\\.config\\obsidian.env`

จากนั้นทุกโปรเจกต์ใช้คำสั่งเดียว:
- `docker compose --env-file "%USERPROFILE%\\.config\\obsidian.env" --env-file .env up -d`

## 4) เช็คว่าเชื่อมได้จริง
- ถ้า API รันบนเครื่อง: `https://127.0.0.1:27124/vault/` ต้องตอบได้ (ต้องมี Authorization)
- จากระบบ: `http://localhost:8000/api/v1/system/health` ดูสถานะ Obsidian
