import os, httpx, pathlib, json, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
for l in p.read_text(encoding="utf-8").splitlines():
    if l.strip().startswith("FASTWORK_JWT="):
        jwt=l.split("=",1)[1].strip()
        break
h={"Authorization": f"Bearer {jwt}", "Content-Type":"application/json", "fw-locale":"th"}
# get subcategory
r=httpx.post("https://gateway.fastwork.co/graphql", headers=h, json={"query":"query { categories { subcategory_groups { subcategories { id slug title category_id active minimum_price } } } }"}, timeout=15)
data=r.json()
subs=[]
for c in data["data"]["categories"]:
    for g in c["subcategory_groups"]:
        for s in g["subcategories"]:
            if s["slug"]=="data-engineering":
                subs.append(s)
print(subs[0])
sub=subs[0]
payload={"category_id": sub["category_id"], "subcategory_id": sub["id"], "title":"ทดสอบสร้างสินค้า", "description":"ทดสอบรายละเอียด", "attribute_value_ids":[], "tag_ids":[]}
print("payload", payload)
r2=httpx.post("https://api.fastwork.co/api/v4/products", headers=h, json=payload, timeout=15)
print("status", r2.status_code)
print(r2.text[:4000])
# try GET the created product if id returned
try:
    j=r2.json()
    pid=j.get("id") or j.get("data",{}).get("id")
    print("pid", pid)
    if pid:
        r3=httpx.get(f"https://api.fastwork.co/api/v4/products/{pid}", headers=h, timeout=15)
        print("GET", r3.text[:2000])
except Exception as e:
    print(e)
