# n8n-sme-workflow-pack delivery bundle

This bundle contains the original AI Factory delivery assets.
Source files are preserved below with their relative paths.

## Source: `downloads/07-n8n-sme-workflow-pack/README.md`

```md
﻿# n8n SME Workflow Pack
**5 Production-Ready n8n Workflows สำหรับ SME ไทย — Import แล้วใช้ได้เลย**

> 📦 Pack นี้มาพร้อมกับ **AI Automation Workflow Cheatsheet** (product #5)  
> 🎯 เป้าหมาย: ลดงานซ้ำ ๆ 15+ ชั่วโมง/สัปดาห์ แทนการจ้าง VA 15,000 บาท/เดือน

---

## สารบัญ Workflow

| # | Workflow | ใช้กับ | เวลาที่ประหยัด/สัปดาห์ |
|---|---|---|---|
| 01 | [LINE OA Auto-Reply + Ticket Routing](#01-line) | ร้านค้า/ร้านอาหาร/คลินิก | 5-8 ชม. |
| 02 | [Invoice OCR → Google Sheets → LINE](#02-invoice) | บริษัท/ร้านค้า | 6-10 ชม. |
| 03 | [Daily Report (POS → AI → Email/Slack)](#03-report) | ร้านอาหาร/คาเฟ่/รีเทล | 2-3 ชม. |
| 04 | [Facebook Lead Enrichment + Scoring](#04-lead) | เอเจนซี่/ทีมขาย | 4-6 ชม. |
| 05 | [Blog to 30 Social Posts](#05-content) | Content creator/SME | 8-12 ชม. |

**รวม:** 25-39 ชั่วโมง/สัปดาห์ → ประหยัดเงิน 25,000-40,000 บาท/เดือน (คิดที่ 1,000 บาท/ชม.)

---

## Quick Start (5 นาที)

### Prerequisites
- n8n installed (self-hosted หรือ cloud)
  - Self-hosted: `docker run -it --rm --name n8n -p 5678:5678 n8nio/n8n`
  - Cloud: https://app.n8n.cloud (free trial 14 วัน)
- Accounts: OpenAI (API key), Google (Sheets), LINE OA, Slack
- งบประมาณ: ~600-2,000 บาท/เดือน (ขึ้นกับ usage)

### Import Workflow (3 ขั้นตอน)

1. **เปิด n8n** → คลิก "Workflows" ที่ sidebar
2. **คลิก "Import from File"** (หรือ `Ctrl/Cmd + I`)
3. **เลือกไฟล์ .json** จาก folder นี้ → คลิก Import

✅ Workflow จะปรากฏในรายการ — ยังไม่ activate

### Configure Credentials (5 นาที)

ก่อน activate ต้องตั้ง credentials ที่จำเป็น:

| Workflow | Required Credentials |
|---|---|
| 01 LINE OA | LINE Channel Access Token, OpenAI API Key, Google Sheets OAuth, Slack Webhook |
| 02 Invoice OCR | Google Vision API Key, OpenAI API Key, Google Sheets, LINE |
| 03 Daily Report | POS API, OpenAI API Key, Email SMTP, Slack Webhook |
| 04 FB Lead | Facebook Page Token, Apollo API, OpenAI, HubSpot Token, Slack, Email |
| 05 Content | Blog RSS URL, OpenAI API Key, Airtable, Buffer |

**วิธีตั้ง credentials ใน n8n:**
1. ไปที่ Settings → Credentials
2. คลิก "Add Credential" → เลือก type
3. กรอก API key / token
4. คลิก "Test" → ถ้า OK → "Save"

**วิธีตั้ง Environment Variables (สำหรับ JSON references):**
1. ไปที่ Settings → Variables
2. เพิ่ม: `OPENAI_API_KEY`, `LINE_CHANNEL_ACCESS_TOKEN`, `SPREADSHEET_ID`, etc.
3. ใน workflow ใช้ `{{ $env.VARIABLE_NAME }}`

### Test & Activate (2 นาที)

1. เปิด workflow ที่ import มา
2. คลิก "Execute Workflow" (มุมขวาล่าง) เพื่อทดสอบ
3. ตรวจสอบ output ในแต่ละ node (คลิกที่ node)
4. ถ้า OK → toggle "Active" ที่มุมขวาบน → workflow จะทำงานอัตโนมัติ

---

<a id="01-line"></a>
## 01 - LINE OA Auto-Reply + Ticket Routing

### Flow Diagram
```
[LINE OA] → [Webhook] → [Has Events?] → [AI Classify] → [Switch] 
                                                            ├─ product → [Reply] → [Log Sheets]
                                                            ├─ order → [Reply] → [Log Sheets]
                                                            ├─ complaint → [Reply] → [Log] → [Slack Alert]
                                                            └─ other → [Reply] → [Log]
```

### Setup
- **LINE OA Channel:** สร้างที่ https://developers.line.biz/console/
- **Webhook URL:** copy จาก n8n webhook node → ใส่ใน LINE Console
- **OpenAI:** ใช้ gpt-4o-mini (ถูก + เร็ว)
- **Google Sheets:** สร้าง sheet "LINE_Logs" ใน Spreadsheet

### Customize
- เปลี่ยน AI prompt ใน node "AI Classify Intent" → เพิ่ม intent อื่น ๆ
- เปลี่ยน switch routing → เพิ่มเงื่อนไข
- เปลี่ยน Slack channel → แก้ `#urgent-customer`

### Cost
- LINE OA: free (official account) / 5,000 บาท/เดือน (verified)
- OpenAI gpt-4o-mini: ~600 บาท/เดือน (1,000 messages)
- Google Sheets: free
- n8n self-hosted: ~400 บาท/เดือน (VPS)

**Total: ~1,000 บาท/เดือน**

---

<a id="02-invoice"></a>
## 02 - Invoice OCR to Google Sheets

### Flow Diagram
```
[LINE/Webhook] → [Download Image] → [Google Vision OCR] → [GPT-4 Extract] 
                                                                ↓
                                                      [Save to Sheets] → [Notify LINE]
```

### Setup
- **Google Cloud Vision:** Enable API → สร้าง API Key
- **Google Sheets:** สร้าง sheet "Invoices" พร้อม columns
- **LINE:** ใช้ Push API แทน Reply (ส่งหา admin โดยตรง)

### Customize
- เพิ่ม validation (ถ้า total > X บาท → ต้องอนุมัติ)
- เพิ่ม OCR ภาษาอื่น (Google Vision รองรับ 50+ ภาษา)
- เปลี่ยน GPT-4 → ใช้ Claude หรือ Gemini ก็ได้

### Cost
- Google Vision: ~$1.50/1,000 images ≈ 50 บาท
- OpenAI GPT-4o: ~800 บาท/เดือน (500 invoices)
- Google Sheets: free
- LINE Push: free

**Total: ~1,200 บาท/เดือน** (ที่ 500 invoices/เดือน)

---

<a id="03-report"></a>
## 03 - Daily Report POS to Email & Slack

### Flow Diagram
```
[CRON 8am] → [Fetch POS] → [Aggregate] → [AI Summary] → [Email] 
                                                       └─ [Slack]
```

### Setup
- **POS API:** ต้องมี API endpoint ของระบบ POS (REST API)
- **Email SMTP:** Gmail App Password / SendGrid / Mailgun
- **Slack:** สร้าง Incoming Webhook

### Customize
- เปลี่ยนเวลา trigger → CRON expression
- เพิ่ม comparison (เทียบกับสัปดาห์ก่อน)
- เพิ่ม chart ใน email (PNG จาก QuickChart.io)

### Cost
- OpenAI gpt-4o-mini: ~200 บาท/เดือน
- Email: free (Gmail) / $15/เดือน (SendGrid)
- Slack: free tier

**Total: ~400 บาท/เดือน**

---

<a id="04-lead"></a>
## 04 - Facebook Lead Enrichment + Scoring

### Flow Diagram
```
[FB Lead Ad] → [Webhook] → [Get Lead] → [Apollo Enrich] → [AI Score] 
                                                            ↓
                                                       [Switch]
                                                            ├─ hot → [HubSpot] + [Slack]
                                                            ├─ warm → [Email Auto-Reply]
                                                            └─ cold → [Email Auto-Reply]
```

### Setup
- **Facebook Lead Ads:** เปิด Lead Ads ใน Ads Manager
- **Apollo.io:** API key + ตั้ง budget
- **HubSpot:** Free CRM + Private App Token
- **Slack:** Webhook สำหรับ #hot-leads

### Customize
- เปลี่ยน scoring criteria → ปรับ prompt
- เพิ่ม HubSpot workflow (assign sales rep)
- เพิ่ม SMS notification (Twilio)

### Cost
- Facebook Lead Ads: free (จ่ายแค่ค่า impression)
- Apollo.io: 49 USD/mo ≈ 1,700 บาท/เดือน (basic)
- OpenAI: ~200 บาท/เดือน
- HubSpot: free (basic CRM)

**Total: ~2,000 บาท/เดือน**

---

<a id="05-content"></a>
## 05 - Blog to 30 Social Posts

### Flow Diagram
```
[RSS Trigger] → [Fetch Article] → [GPT-4 Generate 30] → [Split by Platform] 
                                                              ↓
                                                    [Save Airtable] → [Schedule Buffer]
```

### Setup
- **Blog RSS:** ต้องมี RSS feed (`/feed` หรือ `/rss.xml`)
- **Airtable:** สร้าง base "Content Calendar"
- **Buffer:** Pro plan 6 USD/mo ≈ 200 บาท/เดือน

### Customize
- เปลี่ยนจำนวนโพสต์ (10/20/30/50)
- เปลี่ยน platforms เพิ่ม (TikTok, YouTube Shorts)
- เพิ่ม image generation (DALL-E 3 / Midjourney)

### Cost
- OpenAI GPT-4o: ~800 บาท/เดือน (3 articles)
- Buffer: 200 บาท/เดือน
- Airtable: free tier

**Total: ~1,000 บาท/เดือน** (ที่ 3 บทความ/เดือน)

---

## Deployment Options

### Option A: Self-Hosted (ถูกสุด)
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Run n8n
docker run -d --restart unless-stopped \
  --name n8n \
  -p 5678:5678 \
  -e N8N_HOST=yourdomain.com \
  -e WEBHOOK_URL=https://yourdomain.com/ \
  -v n8n_data:/home/node/.n8n \
  n8nio/n8n

# Use reverse proxy (nginx/caddy)
# Add SSL with Let's Encrypt
```

**ค่าใช้จ่าย:** VPS 4GB RAM ≈ 400-600 บาท/เดือน (DigitalOcean, Hetzner, Vultr)

### Option B: n8n Cloud (ง่ายสุด)
- ไปที่ https://app.n8n.cloud
- สมัคร Starter plan 20 EUR/mo ≈ 800 บาท/เดือน
- ไม่ต้องจัดการ infrastructure
- ได้ 2,500 workflow executions/เดือน

### Option C: Railway (กลาง ๆ)
- ไปที่ https://railway.app
- Deploy จาก GitHub repo
- ใช้ n8n docker image
- เริ่มต้น $5/mo ≈ 175 บาท/เดือน

---

## Troubleshooting

### Workflow ไม่ทำงาน
1. ตรวจสอบ "Active" toggle (ต้องเปิด)
2. ดู Executions tab → มี error อะไร
3. ตรวจสอบ credentials (token หมดอายุ?)
4. ตรวจสอบ webhook URL (ตรงกับ LINE/FB ที่ตั้งไว้ไหม)

### AI ให้ผลผิดพลาด
1. ปรับ temperature ใน OpenAI node (0 = แม่น, 1 = สร้างสรรค์)
2. เพิ่ม few-shot examples ใน prompt
3. เปลี่ยน model (gpt-4o > gpt-4o-mini > gpt-3.5)
4. เพิ่ม JSON schema validation

### ค่าใช้จ่ายเกิน budget
1. ใช้ gpt-4o-mini แทน gpt-4o (ประหยัด 95%)
2. Cache results (ไม่เรียก AI ซ้ำถ้าข้อมูลเหมือนเดิม)
3. Self-host n8n แทนใช้ cloud
4. ลด trigger frequency (เช่น ทุก 2 ชม. แทนทุก 30 นาที)

### Performance ช้า
1. Self-host ใกล้ผู้ใช้ (Singapore region สำหรับ TH)
2. เพิ่ม RAM (อย่างน้อย 4GB)
3. ใช้ PostgreSQL แทน SQLite
4. ตั้ง worker mode (queue)

---

## Advanced: เพิ่ม Workflow เอง

### ใช้ AI ช่วยเขียน Workflow
Prompt ที่แนะนำ:
```
ฉันต้องการ n8n workflow ที่:
- Trigger: [เมื่อมี event อะไร]
- Process: [ทำอะไรกับข้อมูล]
- Output: [ส่งไปที่ไหน]

ช่วยสร้าง JSON สำหรับ n8n import พร้อม:
1. Node ที่จำเป็น
2. Credentials ที่ต้องตั้ง
3. Error handling
4. Logging
```

### เชื่อมต่อ Service อื่น ๆ
n8n มี 400+ integrations ให้เชื่อมต่อ:
- Notion, Airtable, Google Sheets, Excel
- LINE, Telegram, WhatsApp, Discord, Slack
- Salesforce, HubSpot, Pipedrive
- Stripe, PayPal, PromptPay
- MySQL, PostgreSQL, MongoDB
- AWS S3, Google Cloud Storage

ดูเพิ่ม: https://n8n.io/integrations/

---

## Support & Updates

📧 Email: support@aifactory.co  
💬 Facebook Group: "n8n Thailand"  
📚 Docs: https://docs.n8n.io  
🔄 Updates: ฟรีตลอดชีพ — subscribe email ของเรา

---

**License:** สำหรับผู้ซื้อ license 1 คน/1 บริษัท  
ห้าม redistribute / resell / เผยแพร่ต่อ

**Made with ❤️ for Thai SME community — มิถุนายน 2026**
```

## Source: `downloads/07-n8n-sme-workflow-pack/01-line-oa-auto-reply.json`

```json
{
  "name": "01 - LINE OA Auto-Reply + Ticket Routing",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "line-oa-webhook",
        "responseMode": "onReceived",
        "responseData": "allEntries",
        "options": {}
      },
      "id": "f1a2b3c4-0001-4000-8000-000000000001",
      "name": "LINE Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 1,
      "position": [240, 300],
      "webhookId": "line-oa-webhook-uuid"
    },
    {
      "parameters": {
        "conditions": {
          "number": [
            {
              "value1": "={{ $json.body.events.length }}",
              "operation": "larger",
              "value2": 0
            }
          ]
        }
      },
      "id": "f1a2b3c4-0001-4000-8000-000000000002",
      "name": "Has Events?",
      "type": "n8n-nodes-base.if",
      "typeVersion": 1,
      "position": [460, 300]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "https://api.line.me/v2/bot/message/reply",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "Authorization",
              "value": "Bearer {{ $env.LINE_CHANNEL_ACCESS_TOKEN }}"
            },
            {
              "name": "Content-Type",
              "value": "application/json"
            }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"replyToken\": \"{{ $json.body.events[0].replyToken }}\",\n  \"messages\": [\n    {\n      \"type\": \"text\",\n      \"text\": \"สวัสดีค่ะ {{ $json.body.events[0].source.userId }} ขอบคุณที่ทักมา กำลังส่งต่อให้เจ้าหน้าที่ค่ะ\"\n    }\n  ]\n}",
        "options": {}
      },
      "id": "f1a2b3c4-0001-4000-8000-000000000003",
      "name": "Reply to LINE",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [900, 200]
    },
    {
      "parameters": {
        "operation": "message",
        "modelId": {
          "__rl": true,
          "value": "gpt-4o-mini",
          "mode": "list",
          "cachedResultName": "gpt-4o-mini"
        },
        "messages": {
          "messageValues": [
            {
              "role": "system",
              "content": "คุณเป็น AI จัดหมวดข้อความ LINE OA ของร้านค้า\nจัดหมวดข้อความลูกค้าเป็น 1 ใน 4 ประเภท:\n- product_inquiry (ถามเกี่ยวกับสินค้า/ราคา/สต็อก)\n- order (ต้องการสั่งซื้อ)\n- complaint (ร้องเรียน/ปัญหา)\n- other (อื่น ๆ)\n\nตอบเป็น JSON เท่านั้น: {\"intent\": \"...\", \"confidence\": 0.0-1.0, \"summary\": \"...\"}"
            },
            {
              "role": "user",
              "content": "={{ $json.body.events[0].message.text }}"
            }
          ]
        },
        "options": {
          "responseFormat": "json_object"
        }
      },
      "id": "f1a2b3c4-0001-4000-8000-000000000004",
      "name": "AI Classify Intent",
      "type": "@n8n/n8n-nodes-langchain.openAi",
      "typeVersion": 1,
      "position": [680, 300]
    },
    {
      "parameters": {
        "rules": {
          "values": [
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "loose"
                },
                "conditions": [
                  {
                    "leftValue": "={{ $json.choices[0].message.content }}",
                    "rightValue": "product_inquiry",
                    "operator": {
                      "type": "string",
                      "operation": "contains"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "product"
            },
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "loose"
                },
                "conditions": [
                  {
                    "leftValue": "={{ $json.choices[0].message.content }}",
                    "rightValue": "order",
                    "operator": {
                      "type": "string",
                      "operation": "contains"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "order"
            },
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "loose"
                },
                "conditions": [
                  {
                    "leftValue": "={{ $json.choices[0].message.content }}",
                    "rightValue": "complaint",
                    "operator": {
                      "type": "string",
                      "operation": "contains"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "complaint"
            }
          ]
        },
        "options": {
          "fallbackOutput": "extra",
          "renameFallbackOutput": "other"
        }
      },
      "id": "f1a2b3c4-0001-4000-8000-000000000005",
      "name": "Switch by Intent",
      "type": "n8n-nodes-base.switch",
      "typeVersion": 3,
      "position": [900, 300]
    },
    {
      "parameters": {
        "operation": "append",
        "documentId": {
          "__rl": true,
          "value": "={{ $env.SPREADSHEET_ID }}",
          "mode": "id"
        },
        "sheetName": {
          "__rl": true,
          "value": "LINE_Logs",
          "mode": "name"
        },
        "columns": {
          "mappingMode": "defineBelow",
          "value": {
            "timestamp": "={{ $now.toISO() }}",
            "userId": "={{ $node['LINE Webhook'].json.body.events[0].source.userId }}",
            "message": "={{ $node['LINE Webhook'].json.body.events[0].message.text }}",
            "intent": "={{ $json.choices[0].message.content }}",
            "status": "logged"
          }
        },
        "options": {}
      },
      "id": "f1a2b3c4-0001-4000-8000-000000000006",
      "name": "Log to Google Sheets",
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4,
      "position": [1140, 200]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "https://hooks.slack.com/services/XXXXX/YYYYY/ZZZZZ",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "Content-Type",
              "value": "application/json"
            }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"channel\": \"#urgent-customer\",\n  \"text\": \"🚨 *ลูกค้าร้องเรียนใหม่*\\nUser: {{ $node['LINE Webhook'].json.body.events[0].source.userId }}\\nข้อความ: {{ $node['LINE Webhook'].json.body.events[0].message.text }}\\nIntent: complaint\"\n}",
        "options": {}
      },
      "id": "f1a2b3c4-0001-4000-8000-000000000007",
      "name": "Alert Slack - Complaint",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [1140, 400]
    }
  ],
  "connections": {
    "LINE Webhook": {
      "main": [
        [
          {
            "node": "Has Events?",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Has Events?": {
      "main": [
        [
          {
            "node": "AI Classify Intent",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "AI Classify Intent": {
      "main": [
        [
          {
            "node": "Switch by Intent",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Switch by Intent": {
      "main": [
        [
          {
            "node": "Reply to LINE",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Reply to LINE",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Reply to LINE",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Reply to LINE",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Reply to LINE": {
      "main": [
        [
          {
            "node": "Log to Google Sheets",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Log to Google Sheets": {
      "main": [
        [
          {
            "node": "Alert Slack - Complaint",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "settings": {
    "executionOrder": "v1",
    "saveExecutionProgress": true,
    "saveManualExecutions": true,
    "saveDataSuccessExecution": "all",
    "saveDataErrorExecution": "all"
  },
  "staticData": null,
  "tags": [
    {
      "name": "line-oa",
      "id": "tag-1"
    },
    {
      "name": "customer-service",
      "id": "tag-2"
    }
  ],
  "active": false,
  "versionId": "1.0"
}
```

## Source: `downloads/07-n8n-sme-workflow-pack/02-invoice-ocr-to-sheets.json`

```json
{
  "name": "02 - Invoice OCR to Google Sheets",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "invoice-upload",
        "responseMode": "onReceived",
        "options": {}
      },
      "id": "f2a2b3c4-0002-4000-8000-000000000001",
      "name": "Invoice Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 1,
      "position": [240, 300]
    },
    {
      "parameters": {
        "method": "GET",
        "url": "={{ $json.body.imageUrl }}",
        "options": {
          "response": {
            "response": {
              "responseFormat": "file"
            }
          }
        }
      },
      "id": "f2a2b3c4-0002-4000-8000-000000000002",
      "name": "Download Image",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [460, 300]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "https://vision.googleapis.com/v1/images:annotate",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "Authorization",
              "value": "Bearer {{ $env.GOOGLE_VISION_API_KEY }}"
            }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"requests\": [\n    {\n      \"image\": {\n        \"content\": \"{{ $binary.data.toString('base64') }}\"\n      },\n      \"features\": [\n        {\"type\": \"TEXT_DETECTION\"}\n      ]\n    }\n  ]\n}",
        "options": {}
      },
      "id": "f2a2b3c4-0002-4000-8000-000000000003",
      "name": "Google Vision OCR",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [680, 300]
    },
    {
      "parameters": {
        "operation": "message",
        "modelId": {
          "__rl": true,
          "value": "gpt-4o",
          "mode": "list",
          "cachedResultName": "gpt-4o"
        },
        "messages": {
          "messageValues": [
            {
              "role": "system",
              "content": "คุณเป็น AI แยกข้อมูลจาก OCR text ของบิล/ใบเสร็จ\nแยกข้อมูลเป็น JSON: \n{\n  \"vendor\": \"ชื่อร้าน/บริษัท\",\n  \"date\": \"YYYY-MM-DD\",\n  \"items\": [{\"name\": \"...\", \"qty\": 1, \"price\": 0}],\n  \"subtotal\": 0,\n  \"vat\": 0,\n  \"total\": 0,\n  \"currency\": \"THB\"\n}\n\nถ้าข้อมูลไม่ชัด → ใส่ null และระบุใน notes"
            },
            {
              "role": "user",
              "content": "={{ $json.responses[0].fullTextAnnotation.text }}"
            }
          ]
        },
        "options": {
          "responseFormat": "json_object"
        }
      },
      "id": "f2a2b3c4-0002-4000-8000-000000000004",
      "name": "Extract Fields with GPT-4",
      "type": "@n8n/n8n-nodes-langchain.openAi",
      "typeVersion": 1,
      "position": [900, 300]
    },
    {
      "parameters": {
        "operation": "append",
        "documentId": {
          "__rl": true,
          "value": "={{ $env.SPREADSHEET_ID }}",
          "mode": "id"
        },
        "sheetName": {
          "__rl": true,
          "value": "Invoices",
          "mode": "name"
        },
        "columns": {
          "mappingMode": "defineBelow",
          "value": {
            "timestamp": "={{ $now.toISO() }}",
            "vendor": "={{ $json.choices[0].message.content.vendor }}",
            "date": "={{ $json.choices[0].message.content.date }}",
            "total": "={{ $json.choices[0].message.content.total }}",
            "currency": "={{ $json.choices[0].message.content.currency }}",
            "items_count": "={{ $json.choices[0].message.content.items.length }}",
            "raw_json": "={{ $json.choices[0].message.content }}",
            "status": "success"
          }
        }
      },
      "id": "f2a2b3c4-0002-4000-8000-000000000005",
      "name": "Save to Sheets",
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4,
      "position": [1120, 300]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "https://api.line.me/v2/bot/message/push",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "Authorization",
              "value": "Bearer {{ $env.LINE_CHANNEL_ACCESS_TOKEN }}"
            },
            {
              "name": "Content-Type",
              "value": "application/json"
            }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"to\": \"{{ $env.LINE_USER_ID_ADMIN }}\",\n  \"messages\": [\n    {\n      \"type\": \"text\",\n      \"text\": \"✅ บันทึกบิลสำเร็จ\\nร้าน: {{ $json.choices[0].message.content.vendor }}\\nยอด: {{ $json.choices[0].message.content.total }} บาท\"\n    }\n  ]\n}"
      },
      "id": "f2a2b3c4-0002-4000-8000-000000000006",
      "name": "Notify LINE Admin",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [1340, 300]
    }
  ],
  "connections": {
    "Invoice Webhook": {
      "main": [
        [
          {
            "node": "Download Image",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Download Image": {
      "main": [
        [
          {
            "node": "Google Vision OCR",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Google Vision OCR": {
      "main": [
        [
          {
            "node": "Extract Fields with GPT-4",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Extract Fields with GPT-4": {
      "main": [
        [
          {
            "node": "Save to Sheets",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Save to Sheets": {
      "main": [
        [
          {
            "node": "Notify LINE Admin",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "settings": {
    "executionOrder": "v1",
    "saveExecutionProgress": true,
    "saveDataSuccessExecution": "all",
    "saveDataErrorExecution": "all"
  },
  "staticData": null,
  "tags": [
    {
      "name": "invoice",
      "id": "tag-1"
    },
    {
      "name": "ocr",
      "id": "tag-2"
    }
  ],
  "active": false,
  "versionId": "1.0"
}
```

## Source: `downloads/07-n8n-sme-workflow-pack/03-daily-report-pos.json`

```json
{
  "name": "03 - Daily Report POS to Email & Slack",
  "nodes": [
    {
      "parameters": {
        "rule": {
          "interval": [
            {
              "field": "cronExpression",
              "expression": "0 8 * * *"
            }
          ]
        }
      },
      "id": "f3a2b3c4-0003-4000-8000-000000000001",
      "name": "Daily 8am Trigger",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1,
      "position": [240, 300]
    },
    {
      "parameters": {
        "method": "GET",
        "url": "={{ $env.POS_API_URL }}/v1/sales?date={{ $now.format('YYYY-MM-DD') }}",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "Authorization",
              "value": "Bearer {{ $env.POS_API_KEY }}"
            }
          ]
        },
        "options": {}
      },
      "id": "f3a2b3c4-0003-4000-8000-000000000002",
      "name": "Fetch POS Data",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [460, 300]
    },
    {
      "parameters": {
        "jsCode": "// Aggregate sales data\nconst sales = items[0].json.transactions || [];\nconst totalRevenue = sales.reduce((sum, t) => sum + t.amount, 0);\nconst orderCount = sales.length;\nconst avgOrder = orderCount > 0 ? totalRevenue / orderCount : 0;\nconst topItems = {};\nsales.forEach(t => {\n  (t.items || []).forEach(i => {\n    topItems[i.name] = (topItems[i.name] || 0) + (i.qty || 1);\n  });\n});\nconst sorted = Object.entries(topItems).sort((a, b) => b[1] - a[1]).slice(0, 5);\nreturn [{\n  json: {\n    date: new Date().toISOString().split('T')[0],\n    totalRevenue,\n    orderCount,\n    avgOrder,\n    topItems: sorted\n  }\n}];"
      },
      "id": "f3a2b3c4-0003-4000-8000-000000000003",
      "name": "Aggregate Sales",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [680, 300]
    },
    {
      "parameters": {
        "operation": "message",
        "modelId": {
          "__rl": true,
          "value": "gpt-4o-mini",
          "mode": "list",
          "cachedResultName": "gpt-4o-mini"
        },
        "messages": {
          "messageValues": [
            {
              "role": "system",
              "content": "คุณเป็น AI วิเคราะห์ยอดขายร้านอาหารไทย\nรับข้อมูล JSON ของยอดขายวันนี้ แล้วสร้างสรุปภาษาไทย (3-5 bullet points):\n1. ยอดขายรวม + เปรียบเทียบเมื่อวาน (ถ้ามีข้อมูล)\n2. Top 3 เมนูขายดี\n3. ช่วงเวลาที่ขายดีที่สุด (ถ้ามีข้อมูล)\n4. Insight / คำแนะนำ 1-2 ข้อ\n5. สัญญาณเตือน (ถ้ายอดผิดปกติ)\n\nใช้ภาษาเป็นกันเอง เหมือนคุยกับเจ้าของร้าน"
            },
            {
              "role": "user",
              "content": "=ข้อมูลยอดขาย: {{ JSON.stringify($json) }}"
            }
          ]
        }
      },
      "id": "f3a2b3c4-0003-4000-8000-000000000004",
      "name": "AI Summary Thai",
      "type": "@n8n/n8n-nodes-langchain.openAi",
      "typeVersion": 1,
      "position": [900, 300]
    },
    {
      "parameters": {
        "fromEmail": "report@yourcompany.com",
        "toEmail": "={{ $env.OWNER_EMAIL }}",
        "subject": "=📊 รายงานยอดขายวันที่ {{ $now.format('DD/MM/YYYY') }}",
        "html": "=<h2>สรุปยอดขายประจำวัน</h2>\n<p><b>ยอดรวม:</b> {{ $node['Aggregate Sales'].json.totalRevenue }} บาท</p>\n<p><b>จำนวนออเดอร์:</b> {{ $node['Aggregate Sales'].json.orderCount }}</p>\n<hr>\n<pre>{{ $json.choices[0].message.content }}</pre>",
        "options": {}
      },
      "id": "f3a2b3c4-0003-4000-8000-000000000005",
      "name": "Send Email Report",
      "type": "n8n-nodes-base.emailSend",
      "typeVersion": 2,
      "position": [1120, 200]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "={{ $env.SLACK_WEBHOOK_URL }}",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "Content-Type",
              "value": "application/json"
            }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"channel\": \"#daily-report\",\n  \"blocks\": [\n    {\n      \"type\": \"header\",\n      \"text\": {\n        \"type\": \"plain_text\",\n        \"text\": \"📊 รายงานยอดขายวันที่ {{ $now.format('DD/MM/YYYY') }}\"\n      }\n    },\n    {\n      \"type\": \"section\",\n      \"fields\": [\n        {\"type\": \"mrkdwn\", \"text\": \"*ยอดรวม:*\\n{{ $node['Aggregate Sales'].json.totalRevenue }} บาท\"},\n        {\"type\": \"mrkdwn\", \"text\": \"*ออเดอร์:*\\n{{ $node['Aggregate Sales'].json.orderCount }}\"}\n      ]\n    },\n    {\n      \"type\": \"section\",\n      \"text\": {\n        \"type\": \"mrkdwn\",\n        \"text\": \"{{ $json.choices[0].message.content }}\"\n      }\n    }\n  ]\n}"
      },
      "id": "f3a2b3c4-0003-4000-8000-000000000006",
      "name": "Post to Slack",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [1120, 400]
    }
  ],
  "connections": {
    "Daily 8am Trigger": {
      "main": [
        [
          {
            "node": "Fetch POS Data",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Fetch POS Data": {
      "main": [
        [
          {
            "node": "Aggregate Sales",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Aggregate Sales": {
      "main": [
        [
          {
            "node": "AI Summary Thai",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "AI Summary Thai": {
      "main": [
        [
          {
            "node": "Send Email Report",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Post to Slack",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "settings": {
    "executionOrder": "v1",
    "saveDataSuccessExecution": "all",
    "saveDataErrorExecution": "all"
  },
  "staticData": null,
  "tags": [
    {
      "name": "daily-report",
      "id": "tag-1"
    }
  ],
  "active": false,
  "versionId": "1.0"
}
```

## Source: `downloads/07-n8n-sme-workflow-pack/04-fb-lead-enrichment.json`

```json
{
  "name": "04 - Facebook Lead Enrichment + Scoring",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "fb-lead-webhook",
        "responseMode": "onReceived",
        "options": {}
      },
      "id": "f4a2b3c4-0004-4000-8000-000000000001",
      "name": "FB Lead Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 1,
      "position": [240, 300]
    },
    {
      "parameters": {
        "method": "GET",
        "url": "={{ $env.FB_GRAPH_API_URL }}/{{ $json.body.entry[0].changes[0].value.leadgen_id }}?access_token={{ $env.FB_PAGE_ACCESS_TOKEN }}",
        "options": {}
      },
      "id": "f4a2b3c4-0004-4000-8000-000000000002",
      "name": "Get Lead Details",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [460, 300]
    },
    {
      "parameters": {
        "method": "GET",
        "url": "https://api.apollo.io/v1/people/match",
        "sendQuery": true,
        "queryParameters": {
          "parameters": [
            {
              "name": "email",
              "value": "={{ $json.field_data.find(f => f.name === 'email')?.values[0] }}"
            }
          ]
        },
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "api_key",
              "value": "={{ $env.APOLLO_API_KEY }}"
            }
          ]
        },
        "options": {}
      },
      "id": "f4a2b3c4-0004-4000-8000-000000000003",
      "name": "Enrich with Apollo",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [680, 300]
    },
    {
      "parameters": {
        "operation": "message",
        "modelId": {
          "__rl": true,
          "value": "gpt-4o-mini",
          "mode": "list",
          "cachedResultName": "gpt-4o-mini"
        },
        "messages": {
          "messageValues": [
            {
              "role": "system",
              "content": "คุณเป็น AI วิเคราะห์ lead ฝั่งขาย\nรับข้อมูล lead: name, email, phone, message, company, title\nให้คะแนน 0-100 ตาม:\n- ความชัดเจนของความต้องการ (0-30)\n- งบประมาณที่ระบุ (0-30)\n- ตำแหน่ง/อำนาจตัดสินใจ (0-20)\n- ความเร่งด่วน (0-20)\n\nตอบเป็น JSON เท่านั้น: {\"score\": <0-100>, \"category\": \"hot/warm/cold\", \"reasoning\": \"...\", \"next_action\": \"...\"}"
            },
            {
              "role": "user",
              "content": "={{ JSON.stringify($json) }}"
            }
          ]
        },
        "options": {
          "responseFormat": "json_object"
        }
      },
      "id": "f4a2b3c4-0004-4000-8000-000000000004",
      "name": "AI Score Lead",
      "type": "@n8n/n8n-nodes-langchain.openAi",
      "typeVersion": 1,
      "position": [900, 300]
    },
    {
      "parameters": {
        "rules": {
          "values": [
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "loose"
                },
                "conditions": [
                  {
                    "id": "score-hot",
                    "leftValue": "={{ $json.choices[0].message.content }}",
                    "rightValue": "\"category\": \"hot\"",
                    "operator": {
                      "type": "string",
                      "operation": "contains"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "hot"
            },
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "loose"
                },
                "conditions": [
                  {
                    "id": "score-warm",
                    "leftValue": "={{ $json.choices[0].message.content }}",
                    "rightValue": "\"category\": \"warm\"",
                    "operator": {
                      "type": "string",
                      "operation": "contains"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "warm"
            }
          ]
        },
        "options": {
          "fallbackOutput": "extra",
          "renameFallbackOutput": "cold"
        }
      },
      "id": "f4a2b3c4-0004-4000-8000-000000000005",
      "name": "Route by Score",
      "type": "n8n-nodes-base.switch",
      "typeVersion": 3,
      "position": [1120, 300]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "={{ $env.HUBSPOT_API_URL }}/crm/v3/objects/contacts",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "Authorization",
              "value": "Bearer {{ $env.HUBSPOT_ACCESS_TOKEN }}"
            },
            {
              "name": "Content-Type",
              "value": "application/json"
            }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"properties\": {\n    \"email\": \"{{ $json.email }}\",\n    \"firstname\": \"{{ $json.first_name }}\",\n    \"lastname\": \"{{ $json.last_name }}\",\n    \"phone\": \"{{ $json.phone }}\",\n    \"lead_score\": \"{{ $json.choices[0].message.content.score }}\",\n    \"lead_category\": \"hot\",\n    \"lifecyclestage\": \"lead\"\n  }\n}"
      },
      "id": "f4a2b3c4-0004-4000-8000-000000000006",
      "name": "Push to HubSpot CRM",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [1340, 200]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "={{ $env.SLACK_WEBHOOK_URL }}",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "Content-Type",
              "value": "application/json"
            }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"channel\": \"#hot-leads\",\n  \"text\": \"🔥 *HOT LEAD ALERT*\\nชื่อ: {{ $json.first_name }} {{ $json.last_name }}\\nอีเมล: {{ $json.email }}\\nเบอร์: {{ $json.phone }}\\nข้อความ: {{ $json.message }}\\nScore: {{ $json.choices[0].message.content.score }}/100\"\n}"
      },
      "id": "f4a2b3c4-0004-4000-8000-000000000007",
      "name": "Slack Alert Hot",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [1560, 200]
    },
    {
      "parameters": {
        "fromEmail": "noreply@yourcompany.com",
        "toEmail": "={{ $json.email }}",
        "subject": "ขอบคุณที่สนใจบริการของเรา",
        "html": "=<p>สวัสดีครับ {{ $json.first_name }},</p><p>ขอบคุณที่ส่งข้อความมา เราได้รับข้อมูลของคุณเรียบร้อยแล้ว ทีมงานจะติดต่อกลับภายใน 24 ชั่วโมงครับ</p>",
        "options": {}
      },
      "id": "f4a2b3c4-0004-4000-8000-000000000008",
      "name": "Auto Reply Email",
      "type": "n8n-nodes-base.emailSend",
      "typeVersion": 2,
      "position": [1340, 400]
    }
  ],
  "connections": {
    "FB Lead Webhook": {
      "main": [
        [
          {
            "node": "Get Lead Details",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Get Lead Details": {
      "main": [
        [
          {
            "node": "Enrich with Apollo",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Enrich with Apollo": {
      "main": [
        [
          {
            "node": "AI Score Lead",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "AI Score Lead": {
      "main": [
        [
          {
            "node": "Route by Score",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Route by Score": {
      "main": [
        [
          {
            "node": "Push to HubSpot CRM",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Auto Reply Email",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Auto Reply Email",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Push to HubSpot CRM": {
      "main": [
        [
          {
            "node": "Slack Alert Hot",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "settings": {
    "executionOrder": "v1",
    "saveDataSuccessExecution": "all",
    "saveDataErrorExecution": "all"
  },
  "staticData": null,
  "tags": [
    {
      "name": "lead-scoring",
      "id": "tag-1"
    },
    {
      "name": "crm",
      "id": "tag-2"
    }
  ],
  "active": false,
  "versionId": "1.0"
}
```

## Source: `downloads/07-n8n-sme-workflow-pack/05-content-repurposing.json`

```json
{
  "name": "05 - Blog to 30 Social Posts",
  "nodes": [
    {
      "parameters": {
        "feedUrl": "={{ $env.BLOG_RSS_URL }}",
        "options": {}
      },
      "id": "f5a2b3c4-0005-4000-8000-000000000001",
      "name": "RSS Feed Trigger",
      "type": "n8n-nodes-base.rssFeedReadTrigger",
      "typeVersion": 1,
      "position": [240, 300]
    },
    {
      "parameters": {
        "method": "GET",
        "url": "={{ $json.link }}",
        "options": {
          "response": {
            "response": {
              "responseFormat": "text"
            }
          }
        }
      },
      "id": "f5a2b3c4-0005-4000-8000-000000000002",
      "name": "Fetch Full Article",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [460, 300]
    },
    {
      "parameters": {
        "operation": "message",
        "modelId": {
          "__rl": true,
          "value": "gpt-4o",
          "mode": "list",
          "cachedResultName": "gpt-4o"
        },
        "messages": {
          "messageValues": [
            {
              "role": "system",
              "content": "คุณเป็น AI content repurposer มืออาชีพ\nรับบทความบล็อก 1 บทความ แล้วสร้าง 30 โพสต์ social media:\n- 10 Facebook posts (150-300 คำ, casual, มี CTA)\n- 10 Instagram captions (50-150 คำ, มี hashtag 5-10 ตัว)\n- 5 LinkedIn posts (100-200 คำ, professional)\n- 5 Twitter threads (5-7 tweets ต่อ thread, hook แรง)\n\nแต่ละโพสต์มี hook + body + CTA\nตอบเป็น JSON array 30 objects: [{\"platform\": \"facebook|instagram|linkedin|twitter\", \"content\": \"...\", \"hashtags\": []}]"
            },
            {
              "role": "user",
              "content": "=บทความ: {{ $json.data }}"
            }
          ]
        },
        "options": {
          "responseFormat": "json_object"
        }
      },
      "id": "f5a2b3c4-0005-4000-8000-000000000003",
      "name": "Generate 30 Posts",
      "type": "@n8n/n8n-nodes-langchain.openAi",
      "typeVersion": 1,
      "position": [680, 300]
    },
    {
      "parameters": {
        "jsCode": "// Parse and split posts by platform\nconst allPosts = JSON.parse($input.first().json.choices[0].message.content);\nconst posts = allPosts.posts || allPosts;\nconst grouped = {\n  facebook: posts.filter(p => p.platform === 'facebook'),\n  instagram: posts.filter(p => p.platform === 'instagram'),\n  linkedin: posts.filter(p => p.platform === 'linkedin'),\n  twitter: posts.filter(p => p.platform === 'twitter')\n};\nconst result = [];\nfor (const [platform, items] of Object.entries(grouped)) {\n  for (const item of items) {\n    result.push({ json: { platform, content: item.content, hashtags: item.hashtags || [] } });\n  }\n}\nreturn result;"
      },
      "id": "f5a2b3c4-0005-4000-8000-000000000004",
      "name": "Split by Platform",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [900, 300]
    },
    {
      "parameters": {
        "operation": "append",
        "documentId": {
          "__rl": true,
          "value": "={{ $env.AIRTABLE_BASE_ID }}",
          "mode": "id"
        },
        "sheetName": {
          "__rl": true,
          "value": "Content Calendar",
          "mode": "name"
        },
        "columns": {
          "mappingMode": "defineBelow",
          "value": {
            "platform": "={{ $json.platform }}",
            "content": "={{ $json.content }}",
            "hashtags": "={{ $json.hashtags.join(' ') }}",
            "status": "draft",
            "created_at": "={{ $now.toISO() }}"
          }
        }
      },
      "id": "f5a2b3c4-0005-4000-8000-000000000005",
      "name": "Save to Airtable",
      "type": "n8n-nodes-base.airtable",
      "typeVersion": 4,
      "position": [1120, 300]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "https://api.bufferapp.com/1/updates/create.json",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {
              "name": "Authorization",
              "value": "Bearer {{ $env.BUFFER_ACCESS_TOKEN }}"
            }
          ]
        },
        "sendQuery": true,
        "queryParameters": {
          "parameters": [
            {
              "name": "text",
              "value": "={{ $json.content }}"
            },
            {
              "name": "profile_ids[]",
              "value": "={{ $env.BUFFER_FB_PROFILE_ID }}"
            },
            {
              "name": "scheduled_at",
              "value": "={{ $now.plus({ days: 1 }).toISO() }}"
            }
          ]
        },
        "options": {}
      },
      "id": "f5a2b3c4-0005-4000-8000-000000000006",
      "name": "Schedule to Buffer",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [1340, 300]
    }
  ],
  "connections": {
    "RSS Feed Trigger": {
      "main": [
        [
          {
            "node": "Fetch Full Article",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Fetch Full Article": {
      "main": [
        [
          {
            "node": "Generate 30 Posts",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Generate 30 Posts": {
      "main": [
        [
          {
            "node": "Split by Platform",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Split by Platform": {
      "main": [
        [
          {
            "node": "Save to Airtable",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Save to Airtable": {
      "main": [
        [
          {
            "node": "Schedule to Buffer",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  },
  "settings": {
    "executionOrder": "v1",
    "saveDataSuccessExecution": "all",
    "saveDataErrorExecution": "all"
  },
  "staticData": null,
  "tags": [
    {
      "name": "content",
      "id": "tag-1"
    },
    {
      "name": "social-media",
      "id": "tag-2"
    }
  ],
  "active": false,
  "versionId": "1.0"
}
```
