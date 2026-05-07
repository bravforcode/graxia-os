# 📓 Obsidian Integration Guide

## ภาพรวม

ระบบ Personal OS สามารถซิงค์ข้อมูลไปยัง Obsidian vault ของคุณได้อัตโนมัติ ทำให้คุณสามารถติดตามงาน opportunities, submissions, contacts และอื่นๆ ใน Obsidian ได้

## 🎯 Features

- ✅ Auto-sync opportunities เมื่อพบใหม่
- ✅ Auto-sync submissions เมื่อส่งแล้ว
- ✅ Auto-sync contacts เมื่อสร้างใหม่
- ✅ สร้าง daily notes อัตโนมัติ
- ✅ สร้าง weekly reviews
- ✅ Frontmatter metadata สำหรับ filtering และ queries
- ✅ Backlinks ระหว่าง notes
- ✅ รองรับทั้ง file system และ REST API

## 🚀 Setup

### วิธีที่ 1: File System (แนะนำ)

1. เพิ่ม path ของ Obsidian vault ใน `.env`:

```bash
OBSIDIAN_VAULT_PATH=C:/Users/YourName/C:/Users/menum/OneDrive/Documents/Gracia
```

2. Restart backend:

```bash
docker-compose restart backend
```

3. ทดสอบ:

```bash
curl http://localhost:8000/api/v1/obsidian/health
```

### วิธีที่ 2: REST API (ต้องติดตั้ง plugin)

1. ติดตั้ง [Local REST API plugin](https://github.com/coddingtonbear/obsidian-local-rest-api) ใน Obsidian

2. เปิด plugin และ copy API key

3. เพิ่มใน `.env`:

```bash
OBSIDIAN_API_URL=http://localhost:27123
OBSIDIAN_API_KEY=your_api_key_here
```

4. Restart backend

## 📁 Vault Structure

ระบบจะสร้าง folders ดังนี้:

```
ObsidianVault/
├── Daily Notes/
│   ├── 2024-01-15.md
│   ├── 2024-01-16.md
│   └── ...
├── Opportunities/
│   ├── OPP-uuid-1.md
│   ├── OPP-uuid-2.md
│   └── ...
├── Submissions/
│   ├── SUB-uuid-1.md
│   ├── SUB-uuid-2.md
│   └── ...
├── Contacts/
│   ├── Contact-John-Doe.md
│   ├── Contact-Jane-Smith.md
│   └── ...
└── Reviews/
    ├── Week-2024-W01.md
    ├── Week-2024-W02.md
    └── ...
```

## 📝 Note Templates

### Opportunity Note

```markdown
---
type: opportunity
status: new
score: 85
tags:
  - opportunity
  - devpost
created: 2024-01-15T10:30:00
---

# Hackathon Project

## 📋 Details

- **Source**: devpost
- **URL**: https://example.com
- **Deadline**: 2024-02-01
- **Budget**: $5,000

## 🎯 Score: 85/100

## 📝 Description

Build an AI-powered tool...

## 🤔 Analysis

This opportunity aligns well with...

## 📎 Links

- [[Opportunities MOC]]
```

### Daily Note

```markdown
---
date: 2024-01-15
tags:
  - daily-note
created: 2024-01-15T06:00:00
---

# Monday, January 15, 2024

## 🎯 Today's Focus

## 📝 Notes

## ✅ Tasks

## 🤝 Meetings

## 💡 Ideas

## 📊 Metrics
```

## 🔄 Auto-Sync Events

ระบบจะซิงค์อัตโนมัติเมื่อ:

- `opportunity.found` → สร้าง opportunity note
- `submission.sent` → สร้าง submission note
- `contact.created` → สร้าง contact note

## 🛠️ API Endpoints

### Health Check

```bash
GET /api/v1/obsidian/health
```

Response:
```json
{
  "configured": true,
  "vault_path": "C:/Users/YourName/C:/Users/menum/OneDrive/Documents/Gracia",
  "api_url": null
}
```

### Manual Sync

```bash
POST /api/v1/obsidian/sync
Content-Type: application/json

{
  "entity_type": "opportunity",
  "entity_id": "uuid-here"
}
```

### Create Daily Note

```bash
POST /api/v1/obsidian/daily-note
```

### Create Weekly Review

```bash
POST /api/v1/obsidian/weekly-review
```

## 🔍 Obsidian Queries

### Dataview: Recent Opportunities

```dataview
TABLE score, status, deadline
FROM "Opportunities"
WHERE type = "opportunity"
SORT created DESC
LIMIT 10
```

### Dataview: Win Rate

```dataview
TABLE
  length(rows.file) as "Total",
  length(filter(rows.file, (x) => contains(x.status, "won"))) as "Won",
  round(length(filter(rows.file, (x) => contains(x.status, "won"))) / length(rows.file) * 100, 1) + "%" as "Win Rate"
FROM "Submissions"
WHERE type = "submission"
GROUP BY true
```

### Dataview: High-Score Opportunities

```dataview
LIST
FROM "Opportunities"
WHERE type = "opportunity" AND score >= 80
SORT score DESC
```

## 🎨 Recommended Plugins

1. **Dataview** - Query และ visualize ข้อมูล
2. **Calendar** - View daily notes
3. **Templater** - Custom templates
4. **Kanban** - Track opportunities
5. **Local REST API** - API access (optional)

## 🔧 Troubleshooting

### ไม่สามารถเขียนไฟล์ได้

1. ตรวจสอบ `OBSIDIAN_VAULT_PATH` ถูกต้อง
2. ตรวจสอบ permissions ของ folder
3. ตรวจสอบ vault ไม่ได้ถูก lock โดย Obsidian

### Notes ไม่ปรากฏใน Obsidian

1. Refresh vault: `Ctrl+R` (Windows) หรือ `Cmd+R` (Mac)
2. ตรวจสอบ folder path ใน settings
3. ปิด-เปิด Obsidian ใหม่

### API connection failed

1. ตรวจสอบ Local REST API plugin เปิดอยู่
2. ตรวจสอบ port 27123 ไม่ถูกใช้งาน
3. ตรวจสอบ API key ถูกต้อง

## 📚 Best Practices

1. **ใช้ tags** - เพิ่ม tags เพื่อ organize notes
2. **สร้าง MOC** - สร้าง Map of Content notes
3. **Link notes** - ใช้ `[[wikilinks]]` เชื่อม notes
4. **Daily reviews** - Review daily notes ทุกเย็น
5. **Weekly reviews** - Review metrics ทุกสัปดาห์

## 🎯 Next Steps

1. ตั้งค่า Obsidian vault path
2. ทดสอบ sync opportunity
3. สร้าง daily note template
4. ติดตั้ง Dataview plugin
5. สร้าง custom queries

## 📖 Resources

- [Obsidian Documentation](https://help.obsidian.md/)
- [Dataview Plugin](https://blacksmithgu.github.io/obsidian-dataview/)
- [Local REST API Plugin](https://github.com/coddingtonbear/obsidian-local-rest-api)
