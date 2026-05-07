# GRAXIA OS - คู่มือ Deploy 24/7 (ไม่มีดับ)

## เป้าหมาย
ตั้งค่าระบบให้ทำงานตลอด 24 ชั่วโมง แม้คุณจะปิดคอมพิวเตอร์ ระบบจะยังคงทำงานบน Cloud

## สถาปัตยกรรม 24/7

```
┌─────────────────────────────────────────────────────────────┐
│                    CLOUD SERVER (VPS/Cloud)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │   Backend   │  │   Worker    │  │      Scheduler      │   │
│  │   (FastAPI) │  │  (Celery)   │  │       (Beat)        │   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
│         │                │                   │                 │
│         └────────────────┴─────────────────┘                 │
│                          │                                   │
│              ┌───────────┴───────────┐                        │
│              │       Redis           │                        │
│              │   (Queue & Cache)     │                        │
│              └───────────────────────┘                        │
│                          │                                   │
│              ┌───────────┴───────────┐                        │
│              │      PostgreSQL       │                        │
│              │   (Supabase Cloud)    │                        │
│              └───────────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │   YOUR DOMAIN     │
                    │  (HTTPS/SSL)      │
                    └───────────────────┘
```

## ตัวเลือก Cloud Provider

### 1. VPS (แนะนำสำหรับ 24/7 เต็มรูปแบบ)
- **DigitalOcean**: $12-24/เดือน (1-2GB RAM)
- **Linode**: $12-24/เดือน
- **Hetzner**: €4.51/เดือน (ราคาดีสุด)
- **AWS Lightsail**: $10/เดือน

### 2. PaaS (ง่ายกว่า แต่แพงกว่า)
- **Render**: มี free tier (แต่ sleep หลังไม่มี traffic)
- **Railway**: ใช้งานง่าย จ่ายตาม usage
- **Fly.io**: มี free tier

### 3. Self-Hosted (ถ้ามีเครื่อง server เอง)
- ใช้ docker-compose.prod.yml เดิม
- ตั้งค่า systemd auto-start

---

## วิธี Deploy แบบ 24/7 (VPS แนะนำ)

### ขั้นตอนที่ 1: เตรียม VPS

```bash
# SSH เข้า VPS
ssh root@your-vps-ip

# อัพเดตระบบ
apt update && apt upgrade -y

# ติดตั้ง Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# ติดตั้ง Docker Compose
apt install docker-compose-plugin -y

# สร้าง user สำหรับ deploy
useradd -m -s /bin/bash graxia
usermod -aG docker graxia
```

### ขั้นตอนที่ 2: Clone Project

```bash
su - graxia
cd ~
git clone https://github.com/your-username/graxia-os.git
cd graxia-os
```

### ขั้นตอนที่ 3: ตั้งค่า Environment

```bash
# คัดลอก environment file
cp .env.production.template .env.production

# แก้ไขค่าต่างๆ:
nano .env.production

# สิ่งที่ต้องแก้:
# - APP_HOST=your-domain.com
# - FRONTEND_URL=https://your-domain.com
# - APP_BASE_URL=https://your-domain.com
# - DATABASE_URL (ใช้ Supabase ที่มีอยู่)
# - REDIS_URL (ใช้ Redis Cloud หรือ Redis บน VPS)
```

### ขั้นตอนที่ 4: Deploy 24/7

```bash
# รันสคริปต์ deploy
chmod +x deploy/24-7-always-on.sh
./deploy/24-7-always-on.sh deploy
```

สคริปต์นี้จะ:
1. สร้าง Docker containers ทั้งหมด
2. ตั้งค่า auto-restart ถ้า service ตาย
3. ตั้งค่า auto-start เมื่อ VPS reboot
4. ตั้งค่า health check ทุก 5 นาที
5. ตั้งค่า log rotation

### ขั้นตอนที่ 5: ตั้งค่า Domain & SSL

```bash
# ติดตั้ง Caddy (reverse proxy + SSL)
docker run -d --name caddy \
  -p 80:80 -p 443:443 \
  -v $(pwd)/deploy/Caddyfile:/etc/caddy/Caddyfile \
  -v caddy_data:/data -v caddy_config:/config \
  caddy:2.8-alpine
```

Caddyfile:
```
your-domain.com {
    reverse_proxy backend:8000
    
    # Frontend
    handle_path /* {
        reverse_proxy frontend:80
    }
    
    # API
    handle_path /api/* {
        reverse_proxy backend:8000
    }
    
    # Grafana
    handle_path /grafana/* {
        reverse_proxy grafana:3000
    }
}
```

---

## การตรวจสอบสถานะระบบ

### คำสั่งที่ใช้บ่อย

```bash
# เข้าไปที่ project
cd ~/graxia-os

# ดูสถานะทั้งหมด
./deploy/24-7-always-on.sh status

# ดู logs แบบ real-time
./deploy/24-7-always-on.sh logs

# Restart ทั้งระบบ
./deploy/24-7-always-on.sh restart

# Update เป็น version ใหม่
./deploy/24-7-always-on.sh update

# ดู logs เฉพาะ service
./deploy/24-7-always-on.sh logs backend
./deploy/24-7-always-on.sh logs worker-default
./deploy/24-7-always-on.sh logs redis
```

### ตรวจสอบผ่าน Web Interface

- **ระบบหลัก**: https://your-domain.com
- **API Health**: https://your-domain.com/health
- **Grafana Dashboard**: https://your-domain.com/grafana
- **Flower (Celery Monitor)**: https://your-domain.com/flower

---

## การ Backup & Recovery

### Auto-Backup ทุกวัน

```bash
# เพิ่ม cron job สำหรับ backup อัตโนมัติ
crontab -e

# เพิ่มบรรทัดนี้:
0 2 * * * cd ~/graxia-os && docker-compose -f docker-compose.prod.yml exec -T backend python -m app.cli backup create --name "auto-$(date +%Y%m%d)" >> logs/backup.log 2>&1
```

### Manual Backup

```bash
# สร้าง backup ทันที
docker-compose -f docker-compose.prod.yml exec backend python -m app.cli backup create --name "manual-$(date +%Y%m%d-%H%M%S)"
```

---

## Troubleshooting

### กรณี Service ตาย

```bash
# ตรวจสอบ service ที่ตาย
docker-compose -f docker-compose.prod.yml ps

# ดู logs ของ service ที่มีปัญหา
docker-compose -f docker-compose.prod.yml logs --tail=100 backend

# Restart service ที่มีปัญหา
docker-compose -f docker-compose.prod.yml restart backend
```

### กรณี Memory เต็ม

```bash
# ดูการใช้ memory
docker stats --no-stream

# Clean up ไฟล์ที่ไม่ใช้
docker system prune -f
docker volume prune -f
```

### กรณี Disk เต็ม

```bash
# ดูการใช้ disk
df -h
docker system df

# Clean up logs เก่า
find logs -name "*.log" -mtime +7 -delete
```

---

## Cost Estimation (ประมาณการค่าใช้จ่าย)

### VPS Option (แนะนำ)
| Provider | Specs | ราคา/เดือน |
|----------|-------|-----------|
| Hetzner CPX11 | 2 vCPU, 4GB RAM | €4.51 (~180 บาท) |
| DigitalOcean Basic | 1 vCPU, 2GB RAM | $12 (~420 บาท) |
| Linode Nanode | 1 vCPU, 1GB RAM | $5 (~175 บาท) |

### Database (Supabase ที่มีอยู่)
- ใช้ Supabase Free tier ที่มีอยู่แล้ว
- หรือ Supabase Pro $25/เดือน

### Redis (ถ้าใช้ external)
- Redis Cloud: Free tier 30MB
- หรือ Upstash: Free tier

**รวมค่าใช้จ่ายต่ำสุด**: ~180-500 บาท/เดือน

---

## Checklist ก่อน Deploy

- [ ] VPS พร้อมใช้งานและมี Docker ติดตั้งแล้ว
- [ ] Domain name พร้อมใช้ (หรือใช้ DDNS)
- [ ] .env.production ตั้งค่าถูกต้อง
- [ ] Database URL ใช้งานได้ (Supabase)
- [ ] SSL certificate (Caddy จัดการให้อัตโนมัติ)
- [ ] ทดสอบระบบบน local ก่อน deploy
- [ ] Backup strategy พร้อม

---

## ติดต่อ / ขอความช่วยเหลือ

หากพบปัญหา:
1. ตรวจสอบ logs: `./deploy/24-7-always-on.sh logs`
2. ตรวจสอบ health: `curl https://your-domain.com/health`
3. Restart ระบบ: `./deploy/24-7-always-on.sh restart`

---

**พร้อมใช้งาน 24/7! 🚀**
