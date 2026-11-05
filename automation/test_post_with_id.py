import httpx, pathlib, sys, json
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Authorization": f"Bearer {jwt}", "Content-Type":"application/json", "fw-locale":"th"}
new_id="cd2050df-e4ff-49c2-9fc5-a7ebe3f220dc"
payload={"id": new_id, "title":"ทดสอบ POST with id","description":"desc","category_id":"59ee9443-71d7-4a10-bf5d-79bcb60565ed","subcategory_id":"6ed71488-478d-4e4a-a1f3-d7cf56ce9340"}
r=httpx.post("https://api.fastwork.co/api/v4/products", headers=h, json=payload, timeout=15)
print(r.status_code, r.text[:2000])
