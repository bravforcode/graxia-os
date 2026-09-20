# obsidian-student-kit delivery bundle

This bundle contains the original AI Factory delivery assets.
Source files are preserved below with their relative paths.

## Source: `downloads/02-obsidian-student-kit/00-README.md`

```md
﻿# Obsidian Starter Kit สำหรับนักศึกษา

> **Updated**: 2026-06-05
> **Obsidian version**: v1.5+ (ใช้ได้กับ free version)
> **ความยาก**: ง่าย (เปิดใช้ได้ใน 10 นาที)

## สิ่งที่คุณจะได้

- 5 template พร้อมใช้ (Daily, Course, Exam, Research, MOC)
- Dataview queries ตัวอย่าง
- Plugin list ที่แนะนำ
- Workflow นักศึกษา (Cornell + Zettelkasten + Spaced Repetition)

---

## 1. การติดตั้ง Obsidian (1 นาที)

1. ดาวน์โหลด [obsidian.md](https://obsidian.md) (ฟรี)
2. เปิดแอป → Create new vault → ตั้งชื่อ (เช่น "StudyVault")
3. เปิด Settings → เปิด "Community plugins" → ปิด "Restricted mode"

---

## 2. Plugin ที่แนะนำ (ติดตั้งผ่าน Community Plugins)

| Plugin | ใช้ทำอะไร | จำเป็นไหม |
|--------|----------|----------|
| **Dataview** | Query notes เหมือน database | จำเป็น |
| **Calendar** | สร้าง Daily Note อัตโนมัติ | แนะนำ |
| **Spaced Repetition** | Flashcard + SRS algorithm | แนะนำ |
| **Templater** | Template ที่ dynamic | แนะนำ |
| **Excalidraw** | วาด diagram | optional |
| **Mind Map** | Mind map ใน note | optional |
| **Tag Wrangler** | จัดการ tag | optional |
| **Tasks** | Query tasks ข้าม notes | optional |

### วิธีติดตั้ง plugin

1. Settings → Community plugins → Browse
2. ค้นหาชื่อ plugin → Install → Enable
3. บาง plugin ต้องตั้งค่าเพิ่ม (ดูเอกสารของ plugin)

---

## 3. โครงสร้าง Vault ที่แนะนำ

```
StudyVault/
├── 00-Inbox/                 # Note ดิบที่ยังไม่จัดระเบียบ
├── 01-Daily/                 # Daily notes (YYYY-MM-DD.md)
├── 02-Courses/               # Note ต่อคอร์ส
│   ├── CS101/
│   ├── MATH201/
│   └── ...
├── 03-Notes/                 # Permanent notes (Zettelkasten)
├── 04-MOCs/                  # Map of Content
├── 05-Research/              # Research papers
├── 06-Exams/                 # Exam prep
├── 07-Resources/             # PDF, eBooks, references
├── Templates/                # Templates ทั้งหมดอยู่ที่นี่
└── _attachments/             # รูป/ไฟล์แนบ
```

---

## 4. เริ่มใช้งานด่วน

### 4.1 สร้าง Daily Note แรก

1. กด `Ctrl/Cmd + P` → "Daily note" → Enter
2. Note ใหม่จะถูกสร้างใน `01-Daily/2026-06-05.md`
3. ใช้ `Daily-Note-Template.md` (ใน folder นี้) เป็น template

### 4.2 ตั้ง Daily Note Template

Settings → Daily Notes → Template → เลือก `Templates/Daily-Note-Template.md`

### 4.3 สร้าง Note คอร์สแรก

1. คลิกขวาใน `02-Courses/CS101/` → New note
2. เปิด Command Palette → "Templater: Insert template"
3. เลือก `01-course-note-template.md`

### 4.4 สร้าง MOC แรก

สร้าง note ใน `04-MOCs/` ชื่อ `MOC-Data-Science.md`
ใช้ template `MOC-Template.md` ใน folder นี้

---

## 5. Dataview Queries ที่มีประโยชน์

### 5.1 List tasks ที่ยังไม่เสร็จ (จากทุก note)

```dataview
TASK
FROM ""
WHERE !completed
SORT due ASC
```

### 5.2 List notes ในคอร์ส CS101

```dataview
LIST
FROM "02-Courses/CS101"
SORT file.ctime DESC
```

### 5.3 Daily Notes 7 วันล่าสุด

```dataview
LIST
FROM "01-Daily"
SORT file.name DESC
LIMIT 7
```

### 5.4 Notes ที่ tag #exam-prep

```dataview
LIST
FROM #exam-prep
SORT file.mtime DESC
```

### 5.5 ตาราง courses + status

```dataview
TABLE
  semester as "เทอม",
  status as "สถานะ",
  grade as "เกรด"
FROM "02-Courses"
SORT semester DESC
```

### 5.6 MOC ทั้งหมด

```dataview
LIST
FROM "04-MOCs"
SORT file.name ASC
```

---

## 6. Workflow นักศึกษา

### Cornell + Zettelkasten + Spaced Repetition

**Step 1: จดในชั้นเรียน → Daily Note**
- ใช้ Daily-Note-Template
- เขียน free-form ไม่ต้องสวย

**Step 2: หลังเรียน → Permanent Note (Zettelkasten)**
- เปิด note ใหม่ใน `03-Notes/`
- ชื่อแบบ "Atomic concept" เช่น "Bayes Theorem ในการตัดสินใจ"
- 1 note = 1 idea
- Link ไปยัง related notes

**Step 3: เตรียมสอบ → Spaced Repetition**
- ใช้ plugin "Spaced Repetition"
- เขียน flashcards ใน note
- ระบบจะนัด review อัตโนมัติ

**Step 4: ทบทวนรายสัปดาห์ → MOC Update**
- ทุกเย็นวันศุกร์ เปิด MOC
- เพิ่ม note ใหม่ที่สร้างในสัปดาห์
- จัดหมวดหมู่ใหม่

---

## 7. เคล็ดลับเพิ่มเติม

### 7.1 Hotkeys ที่ใช้บ่อย

| Key | Action |
|-----|--------|
| `Ctrl/Cmd + N` | New note |
| `Ctrl/Cmd + P` | Command Palette |
| `Ctrl/Cmd + O` | Quick switcher (ค้นหา note) |
| `Ctrl/Cmd + G` | Open graph view |
| `Ctrl/Cmd + E` | Toggle edit/preview |
| `Alt + click` | Create link |

### 7.2 Naming Convention

- **Daily Note**: `YYYY-MM-DD.md` (ใช้ Calendar plugin)
- **Course Note**: `CS101-Chapter-3.md` (รหัสวิชา-หัวข้อ)
- **Permanent Note**: ชื่อ concept เช่น "Pareto Principle.md"
- **MOC**: `MOC-[Topic].md` เช่น `MOC-Statistics.md`
- **Research**: `AuthorYear-Topic.md` เช่น `Smith2024-NLP.md`

### 7.3 Tag Convention

ใช้ tag เป็นหมวดกว้าง:
- `#course/cs101`
- `#concept/algorithm`
- `#exam-prep/midterm`
- `#status/in-progress`
- `#status/mastered`

### 7.4 Backup

- ใช้ **Obsidian Sync** (4 USD/mo) — sync ข้ามอุปกรณ์
- หรือ **Git** (ฟรี) — backup + version control
- หรือ **iCloud/Google Drive** (ฟรี) — แต่ระวัง conflict

---

## 8. เริ่มต้น 5 นาที

1. [ ] ติดตั้ง Obsidian
2. [ ] สร้าง vault ใหม่
3. [ ] ติดตั้ง plugin: Dataview, Calendar, Templater
4. [ ] Copy ไฟล์ template ทั้งหมดจาก folder นี้ ไปยัง `Templates/` ใน vault
5. [ ] ตั้ง Daily Note template path ใน Settings
6. [ ] กด `Ctrl/Cmd + P` → "Daily note" → เริ่มเขียน

---

## 9. แหล่งเรียนรู้เพิ่ม

- [Obsidian Help](https://help.obsidian.md)
- [r/ObsidianMD](https://reddit.com/r/ObsidianMD)
- [Linking Your Thinking](https://www.linkingyourthinking.com) — Zettelkasten
- [Ali Abdaal](https://youtube.com/@aliabdaal) — Study with Obsidian

---

**Created by**: Ai Factory — hello@aifactory.co
**Updated**: 2026-06-05
**License**: Personal & team commercial use
```

## Source: `downloads/02-obsidian-student-kit/01-course-note-template.md`

```md
﻿---
type: course-note
course: ""
semester: ""
instructor: ""
status: in-progress
tags: [course]
date: {{date}}
---

# {{title}}

> **Course**: [ชื่อวิชา]
> **Date**: {{date}}
> **Duration**: [นาทีที่เรียน]
> **Resources**: [ลิงก์/textbook/คลิป]

---

## 1. Session Info

**Topic วันนี้**:
- [หัวข้อหลัก]
- [หัวข้อรอง]

**Learning Objectives**:
- [ ] เข้าใจ [อะไร]
- [ ] ทำ [อะไร] ได้
- [ ] อธิบาย [อะไร] ได้

---

## 2. Cornell Notes

### 2.1 Cues (คำถาม/keywords)

| # | Cue / Question |
|---|---------------|
| 1 | [คำถามที่ 1] |
| 2 | [คำถามที่ 2] |
| 3 | [คำถามที่ 3] |
| 4 | [คำถามที่ 4] |
| 5 | [คำถามที่ 5] |

### 2.2 Notes (สรุปเนื้อหา)

#### Concept 1: [ชื่อ]
- คือ [อธิบาย]
- ตัวอย่าง: [ยกตัวอย่าง]
- เชื่อมโยงกับ: [[Permanent Note 1]] [[Permanent Note 2]]

#### Concept 2: [ชื่อ]
- ...

#### Concept 3: [ชื่อ]
- ...

### 2.3 Summary (สรุป ≤ 100 คำ)

[เขียนสรุปทั้งบทเรียนใน 100 คำ — ต้องอ่านแล้วเข้าใจ essence]

---

## 3. Zettelkasten — Permanent Notes

แยกเป็น atomic notes ใน `03-Notes/`:

- [ ] [Permanent Note 1]([[03-Notes/permanent-1]])
- [ ] [Permanent Note 2]([[03-Notes/permanent-2]])
- [ ] [Permanent Note 3]([[03-Notes/permanent-3]])

**ทุก permanent note ควรมี**:
- คำอธิบาย 1 idea
- ตัวอย่าง/analogy
- Links ไป related notes
- Tags

---

## 4. Spaced Repetition Flashcards

> ใช้ plugin "Spaced Repetition" — เขียน Q&A แล้ว algorithm จะนัด review

### Card 1
**Q**: [คำถาม]
**A**: [คำตอบสั้น]
<!--SR:!2026-06-08,1,230-->

### Card 2
**Q**: [คำถาม]
**A**: [คำตอบสั้น]
<!--SR:!2026-06-08,1,230-->

### Card 3
**Q**: [คำถาม]
**A**: [คำตอบสั้น]
<!--SR:!2026-06-08,1,230-->

### Card 4 (Application)
**Q**: ถ้า [สถานการณ์] จะใช้ [concept] ยังไง
**A**: [คำตอบ]
<!--SR:!2026-06-08,1,230-->

### Card 5 (Application)
**Q**: เปรียบเทียบ X vs Y ต่างกันยังไง
**A**: [คำตอบ]
<!--SR:!2026-06-08,1,230-->

---

## 5. Action Items

- [ ] อ่าน [chapter X] ใน textbook
- [ ] ทำ [exercise Y]
- [ ] สร้าง permanent notes 3 อัน
- [ ] Review flashcards วันพรุ่งนี้
- [ ] ถาม [instructor] เรื่อง [Z]

---

## 6. Connections

**อ่านก่อน**:
- [[01-Daily/{{date:YYYY-MM-DD}}]]
- [[Previous session]]

**อ่านต่อ**:
- [[Next session]]

**Related Courses**:
- [[MOC-CourseName]]

**External Resources**:
- [YouTube link]
- [Paper link]
- [Article link]

---

## 7. Reflection (ปลายสัปดาห์)

**3 สิ่งที่เรียนรู้วันนี้**:
1.
2.
3.

**1 อย่างที่ยังงง**:
-

**Confidence Level**: 1-5
- Concept 1: ⭐⭐⭐⭐
- Concept 2: ⭐⭐⭐
- Concept 3: ⭐⭐⭐⭐⭐

---

**Created by**: Ai Factory — hello@aifactory.co
**Updated**: 2026-06-05
```
