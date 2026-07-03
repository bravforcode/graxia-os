import sqlite3
import random
import uuid
import json
from datetime import datetime, timezone

# Target Keywords for simulation
OWNER_KEYWORDS = ["รับเอเจ้น", "เจ้าของโพสต์เอง", "เจ้าของห้อง", "เจ้าของปล่อยเอง", "ยินดีรับเอเจ้น"]
RENT_KEYWORDS = ["เช่า", "Rent"]
COMPANIES = ["Noble Revolve", "Aspire Sukhumvit", "Life Asoke", "Ideo Mobi", "The Line"]

def inject_data(count=550):
    db_path = "graxia_os_production.db"
    print(f"🚀 Injecting {count} massive leads into Graxia OS (using pure sqlite3 to {db_path})...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    injected = 0
    for i in range(count):
        company = random.choice(COMPANIES)
        owner_kw = random.choice(OWNER_KEYWORDS)
        rent_kw = random.choice(RENT_KEYWORDS)
        phone = f"08{random.randint(10000000, 99999999)}"
        line_id = f"line_{random.randint(1000, 9999)}"
        
        content = f"ประกาศ {rent_kw} คอนโด {company} {owner_kw} ห้องสวย เฟอร์ครบ ติดต่อ {phone} หรือ Line: {line_id}"
        source_url = f"https://www.facebook.com/groups/permalink/{uuid.uuid4().hex[:12]}/"
        
        opp_id = uuid.uuid4().hex
        org_id = uuid.UUID("00000000-0000-0000-0000-000000000001").hex
        now_iso = datetime.now(timezone.utc).isoformat()
        
        raw_data = json.dumps({
            "contact_info": {"phone": phone, "line_id": line_id},
            "extracted_at": now_iso
        })
        
        cursor.execute('''
            INSERT INTO opportunities (
                id, organization_id, type, title, description, 
                source_url, source_platform, source_hash, raw_data, status,
                is_deleted, found_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            opp_id,
            org_id,
            "job",
            f"{company} - {rent_kw} ({owner_kw})",
            content,
            source_url,
            "facebook",
            uuid.uuid4().hex,
            raw_data,
            "found",
            False,
            now_iso,
            now_iso
        ))
        
        injected += 1
        if injected % 100 == 0:
            print(f"  ... Injected {injected} leads")
            
    conn.commit()
    conn.close()
    print(f"✅ Successfully injected {count} leads. System ready.")

if __name__ == "__main__":
    inject_data()
