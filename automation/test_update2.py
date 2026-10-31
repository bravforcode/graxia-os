import os, httpx, pathlib, json, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
for l in p.read_text(encoding="utf-8").splitlines():
    if l.strip().startswith("FASTWORK_JWT="):
        jwt=l.split("=",1)[1].strip()
        break
h={"Authorization": f"Bearer {jwt}", "Content-Type":"application/json", "fw-locale":"th"}
pid="cd2050df-e4ff-49c2-9fc5-a7ebe3f220dc"
# try submit with payload
for payload in [{"title":"ทดสอบ แก้ไข","description":"desc"},{"title":"test","description":"desc","category_id":"59ee9443-71d7-4a10-bf5d-79bcb60565ed"}]:
    r=httpx.put(f"https://api.fastwork.co/api/v4/products/{pid}/submit", headers=h, json=payload, timeout=15)
    print("submit with payload", payload.keys(), r.status_code, r.text[:800])
# also try gateway product mutation
# try PUT /api/v4/product/{id}
for url in [f"https://api.fastwork.co/api/v4/product/{pid}", f"https://api.fastwork.co/api/v4/product.update", f"https://api.fastwork.co/api/v4/products/{pid}/general"]:
    for payload in [{"title":"test"}]:
        try:
            r=httpx.put(url, headers=h, json=payload, timeout=10)
            if r.status_code!=404:
                print(url, r.status_code, r.text[:500])
        except: pass
