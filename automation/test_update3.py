import os, httpx, pathlib, json, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
for l in p.read_text(encoding="utf-8").splitlines():
    if l.strip().startswith("FASTWORK_JWT="):
        jwt=l.split("=",1)[1].strip()
        break
h={"Authorization": f"Bearer {jwt}", "Content-Type":"application/json", "fw-locale":"th"}
# get existing product to copy payload
pid_old="a12ec038-36fd-4842-8e4a-119498950931"
r=httpx.get(f"https://api.fastwork.co/api/v4/products/{pid_old}", headers=h, timeout=15)
old=r.json()
print("old keys", list(old.keys())[:20])
# try PUT to new product with full payload
pid_new="cd2050df-e4ff-49c2-9fc5-a7ebe3f220dc"
payload={
    "title":"ทดสอบสร้างสินค้า แก้ไขเต็ม",
    "description":"ทดสอบรายละเอียดเต็ม",
    "extra_description": old.get("extra_description"),
    "category_id": old["category_id"],
    "subcategory_id": old["subcategory_id"],
    "base_price": 14900,
    "base_delivery_time": 7,
}
print("payload", payload)
r2=httpx.put(f"https://api.fastwork.co/api/v4/products/{pid_new}", headers=h, json=payload, timeout=15)
print("PUT", r2.status_code, r2.text[:2000])
# also try POST to same
r3=httpx.post(f"https://api.fastwork.co/api/v4/products/{pid_new}", headers=h, json=payload, timeout=15)
print("POST", r3.status_code, r3.text[:2000])
