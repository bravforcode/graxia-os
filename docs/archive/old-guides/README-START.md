# ═══════════════════════════════════════════════════════════════════════════════

# 🚀 GRAXIA OS — START HERE

# ═══════════════════════════════════════════════════════════════════════════════

## ⚡ เริ่มใช้งาน (ใช้อันนี้อันเดียว!)

```powershell
# ดู help
.\graxia.ps1

# ถ้าเจอ error "Pool overlaps" - ล้าง network ก่อน
.\cleanup-network.ps1 -Force

# สตาร์ททั้งหมด (30+ services, 100 features)
.\graxia.ps1 up

# หรือเช็คสถานะ
.\graxia.ps1 status
.\graxia.ps1 verify
```

---

## 📦 ไฟล์หลักที่ใช้ (อันเดียวจบ!)

| ไฟล์                        | รายละเอียด                   |
| --------------------------- | ---------------------------- |
| **`graxia.ps1`**            | 🎯 **CLI หลัก** - รวมทั้งหมด |
| `docker-compose.brutal.yml` | 30+ services config          |
| `.env`                      | Environment variables        |

---

## 🎯 คำสั่งที่มี

| คำสั่ง            | ทำอะไร                   |
| ----------------- | ------------------------ |
| `up`              | สตาร์ททั้งหมด (8 phases) |
| `down`            | หยุดทั้งหมด              |
| `status`          | เช็คสถานะ                |
| `verify`          | เช็ค 100 features        |
| `logs [service]`  | ดู logs                  |
| `shell [service]` | เข้า container           |
| `fix`             | ซ่อมอัตโนมัติ            |
| `clean`           | ล้าง Docker              |
| `doctor`          | ตรวจสอบละเอียด           |

---

## 🔥 ดียกว่าเดิมยังไง?

✅ **ไฟล์เดียว** - ไม่ต้องเปิดหลายไฟล์
✅ **Sub-Agents ฝังในไฟล์** - ไม่ต้องไฟล์แยก
✅ **Auto-fix** - ซ่อมปัญหาเอง
✅ **Comprehensive verify** - เช็คละเอียดทั้ง 100 features
✅ **No duplicate Verbose** - แก้ error แล้ว

---

## 🎉 พร้อมใช้แล้ว!

```powershell
.\graxia.ps1 up
```

**99% Operational • 100 Features • One Command!** 🔥
