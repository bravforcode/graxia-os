import httpx, pathlib, json, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Authorization": f"Bearer {jwt}", "Content-Type":"application/json", "fw-locale":"th"}
# get old product full
old_id="a12ec038-36fd-4842-8e4a-119498950931"
new_id="cd2050df-e4ff-49c2-9fc5-a7ebe3f220dc"
r=httpx.get(f"https://api.fastwork.co/api/v4/products/{old_id}", headers=h, timeout=15)
old=r.json()
print("old title", old["title"])
# prepare update payload with same structure as old but new title
payload={
    "title":"ทดสอบแก้ไขด้วย full payload",
    "description": old["description"],
    "extra_description": old["extra_description"],
    "category_id": old["category_id"],
    "subcategory_id": old["subcategory_id"],
    "base_price": 14900,
    "base_delivery_time": 7,
    "auto_message": old.get("auto_message"),
    "enable_auto_message": old.get("enable_auto_message"),
}
print("payload keys", payload.keys())
for url in [f"https://api.fastwork.co/api/v4/products/{new_id}", f"https://api.fastwork.co/api/v4/products/{new_id}/general"]:
    for method in ["PUT","PATCH","POST"]:
        try:
            if method=="PUT":
                r2=httpx.put(url, headers=h, json=payload, timeout=15)
            elif method=="PATCH":
                r2=httpx.patch(url, headers=h, json=payload, timeout=15)
            else:
                r2=httpx.post(url, headers=h, json=payload, timeout=15)
            print(method, url, r2.status_code, r2.text[:600].replace("\n"," "))
        except Exception as e:
            print(e)
