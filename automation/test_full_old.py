import httpx, pathlib, json, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Authorization": f"Bearer {jwt}", "Content-Type":"application/json", "fw-locale":"th"}
old_id="a12ec038-36fd-4842-8e4a-119498950931"
new_id="cd2050df-e4ff-49c2-9fc5-a7ebe3f220dc"
old=httpx.get(f"https://api.fastwork.co/api/v4/products/{old_id}", headers=h, timeout=15).json()
# prepare full payload: use old but change title
payload=dict(old)
payload["title"]="ทดสอบ full old payload"
# remove readonly fields
for k in ["id","slug","status","show","user_id","algolia_status","ban_type","banned_at","ban_days","badges","option_images","is_hot","is_pro","ready_to_work_at","is_instant_hire","is_standard_verified","enable_translation","last_approved_at","show_phone_number","is_live","badges_new","is_new_onboard","worksteps","tags","socials","images","subcategory","category","attribute_values","packages","websites"]:
    payload.pop(k, None)
print("payload keys", list(payload.keys()))
print(json.dumps(payload, ensure_ascii=False)[:800])
r=httpx.put(f"https://api.fastwork.co/api/v4/products/{new_id}", headers=h, json=payload, timeout=15)
print("PUT", r.status_code, r.text[:2000])
