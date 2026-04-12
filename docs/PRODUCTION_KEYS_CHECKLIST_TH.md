# Production Keys Checklist

ไฟล์ที่ต้องเติม: `.env.production`

ห้าม commit `.env.production`, `.env.backup-*`, หรือไฟล์ใน `secrets/`

## เติมให้แล้วโดยอัตโนมัติ

ค่ากลุ่มนี้สร้างให้แล้ว ไม่ต้องไปหาจาก provider:

- `SECRET_KEY`
- `ENCRYPTION_KEY`
- `JWT_SIGNING_KEYS`
- `JWT_ACTIVE_KID`
- `JWT_ISSUER`
- `JWT_AUDIENCE`
- `CSRF_SECRET`
- `REDIS_PASSWORD`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `N8N_PASSWORD`
- `ALERTMANAGER_WEBHOOK_TOKEN`
- `GRAFANA_ADMIN_PASSWORD`
- `POSTGRES_DB=postgres`
- `POSTGRES_USER=postgres`
- `OBSIDIAN_VAULT_PATH=/data/obsidian`
- `OBSIDIAN_AUTO_BOOTSTRAP=false`
- `OBSIDIAN_AUTO_SYNC_ENABLED=false`

## ต้องใส่เองก่อน production จริง

### 1. Domain และ TLS

ต้องเติม:

```env
APP_HOST=
FRONTEND_URL=
APP_BASE_URL=
ALLOWED_CORS_ORIGINS=
CADDY_EMAIL=
COOKIE_DOMAIN=
```

วิธีกรอก:

```env
APP_HOST=app.yourdomain.com
FRONTEND_URL=https://app.yourdomain.com
APP_BASE_URL=https://app.yourdomain.com
ALLOWED_CORS_ORIGINS=https://app.yourdomain.com
CADDY_EMAIL=you@example.com
COOKIE_DOMAIN=app.yourdomain.com
```

วิธีเอาค่า:

1. ซื้อหรือเลือก domain ที่จะใช้
2. ตั้ง DNS `A record` ให้ subdomain ชี้ไป IP ของ server
3. ใช้ subdomain นั้นเป็น `APP_HOST`
4. ใช้ email จริงเป็น `CADDY_EMAIL` สำหรับ Let's Encrypt

### 2. Supabase

ต้องเติม:

```env
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
DATABASE_URL=
DATABASE_MIGRATION_URL=
POSTGRES_EXPORTER_DATA_SOURCE_NAME=
POSTGRES_PASSWORD=
```

วิธีเอา database connection:

1. เข้า `https://supabase.com/dashboard`
2. เลือก project
3. กด `Connect`
4. Copy connection string แบบ `Session pooler`
5. แทน database password ใน connection string
6. ใส่เป็น `DATABASE_URL`

รูปแบบ:

```env
DATABASE_URL=postgresql://postgres.PROJECT_REF:DB_PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require
```

สำหรับ migration:

```env
DATABASE_MIGRATION_URL=postgresql://postgres:DB_PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres?sslmode=require
```

ถ้าเครื่อง production ต่อ IPv6 ไม่ได้ ให้ใช้ session pooler port `5432` เหมือน `DATABASE_URL`

สำหรับ exporter:

```env
POSTGRES_EXPORTER_DATA_SOURCE_NAME=postgresql://postgres:DB_PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres?sslmode=require
```

ถ้า direct connection ใช้ไม่ได้ ให้ใช้ session pooler แทน

วิธีเอา API keys:

1. Supabase Dashboard
2. Project Settings
3. API Keys
4. Copy:
   - Project URL -> `SUPABASE_URL`
   - anon/publishable key -> `SUPABASE_ANON_KEY`
   - service_role/secret key -> `SUPABASE_SERVICE_ROLE_KEY`

ข้อสำคัญ: `SUPABASE_SERVICE_ROLE_KEY` ใช้ฝั่ง backend เท่านั้น ห้ามใส่ frontend

### 3. Telegram

ต้องเติม:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_POLLING_ENABLED=true
```

วิธีเอา token:

1. เปิด Telegram
2. คุยกับ `@BotFather`
3. ส่ง `/newbot`
4. ตั้งชื่อ bot
5. ตั้ง username ที่ลงท้ายด้วย `bot`
6. Copy token ที่ BotFather ส่งให้

วิธีเอา chat id:

1. ส่ง `/start` หา bot ของคุณ
2. เปิด URL นี้ใน browser:

```text
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates
```

3. หา `chat.id`
4. เอาเลขไปใส่ `TELEGRAM_CHAT_ID`

ถ้าเป็น group หรือ channel ค่าอาจเป็นเลขติดลบ เช่น `-1001234567890`

### 4. AI Provider

ต้องเติม:

```env
OPENCLAW_API_KEY=
GEMINI_API_KEY=
SERPAPI_KEY=
```

OpenClaw:

1. เข้า dashboard ของ OpenClaw
2. ไปที่ API Keys
3. Create key
4. ใส่ใน `OPENCLAW_API_KEY`

Gemini:

1. เข้า `https://aistudio.google.com/app/apikey`
2. Create API key
3. ใส่ใน `GEMINI_API_KEY`

SerpAPI:

1. เข้า `https://serpapi.com`
2. ไปที่ Dashboard
3. Copy API key
4. ใส่ใน `SERPAPI_KEY`

### 5. Google Workspace OAuth

ต้องเติม:

```env
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=
GOOGLE_WORKSPACE_EMAIL=
```

วิธีเอา client id/secret:

1. เข้า `https://console.cloud.google.com`
2. เลือก project
3. ไปที่ `APIs & Services`
4. Enable API ที่ใช้ เช่น Gmail API, Calendar API, Drive API
5. ไปที่ `OAuth consent screen`
6. ตั้ง app และเพิ่ม email ตัวเองเป็น test user ถ้ายังไม่ publish
7. ไปที่ `Credentials`
8. Create Credentials -> OAuth client ID
9. เลือก Web application
10. เพิ่ม redirect URI:

```text
https://developers.google.com/oauthplayground
```

11. Copy client id และ client secret

วิธีเอา refresh token:

1. เปิด `https://developers.google.com/oauthplayground`
2. กด gear icon
3. ติ๊ก `Use your own OAuth credentials`
4. ใส่ client id/secret
5. เลือก scopes ที่ต้องใช้ เช่น:

```text
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/drive.file
```

6. กด `Authorize APIs`
7. Login ด้วย account ที่ใช้ทำงาน
8. กด `Exchange authorization code for tokens`
9. Copy `refresh_token`

### 6. Backup Storage และ age encryption

ต้องเติม:

```env
BACKUP_BUCKET=
BACKUP_REGION=
BACKUP_ENDPOINT=
BACKUP_ENCRYPTION_PUBLIC_KEY=
BACKUP_ENCRYPTION_PRIVATE_KEY_FILE=/run/secrets/backup_private_key
```

ถ้าใช้ AWS S3:

```env
BACKUP_BUCKET=your-backup-bucket
BACKUP_REGION=ap-southeast-1
BACKUP_ENDPOINT=
```

ถ้าใช้ Cloudflare R2:

```env
BACKUP_BUCKET=your-r2-bucket
BACKUP_REGION=auto
BACKUP_ENDPOINT=https://ACCOUNT_ID.r2.cloudflarestorage.com
```

วิธีสร้าง age key:

```powershell
age-keygen -o secrets\backup_private_key.txt
```

เอา public key ที่ขึ้นต้นด้วย `age1...` ไปใส่:

```env
BACKUP_ENCRYPTION_PUBLIC_KEY=age1...
```

ถ้าเครื่องยังไม่มี `age-keygen` ให้ติดตั้ง age ก่อน

### 7. Obsidian API

ตอนนี้ปิดไว้แล้ว:

```env
OBSIDIAN_AUTO_SYNC_ENABLED=false
OBSIDIAN_API_URL=
OBSIDIAN_API_KEY=
```

ถ้าจะเปิด:

1. เปิด Obsidian plugin ที่ expose REST API
2. Copy API key จาก plugin
3. ตั้ง URL ที่ backend container เข้าถึงได้
4. เปลี่ยนเป็น:

```env
OBSIDIAN_AUTO_SYNC_ENABLED=true
OBSIDIAN_API_URL=http://host.docker.internal:27123
OBSIDIAN_API_KEY=...
```

## ตรวจหลังเติมครบ

```powershell
docker compose --env-file .env.production -f docker-compose.supabase.yml config --quiet
```

```powershell
docker compose --env-file .env.production -f docker-compose.supabase.yml run --rm backend python scripts/production_preflight.py
```

```powershell
docker compose --env-file .env.production -f docker-compose.supabase.yml run --rm backend python scripts/alembic_safe.py upgrade head
```

```powershell
docker compose --env-file .env.production -f docker-compose.supabase.yml up -d --build
```

## Security note

Firebase private key ที่เคยถูก paste ในแชตต้อง rotate/revoke ก่อนใช้ production ต่อ เพราะถือว่า leaked แล้ว
