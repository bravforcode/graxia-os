import httpx, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Authorization": f"Bearer {jwt}", "Content-Type":"application/json", "fw-locale":"th", "Cookie": f"accessToken={jwt}"}
new_id="cd2050df-e4ff-49c2-9fc5-a7ebe3f220dc"
for base in ["https://seller.fastwork.co", "https://api.fastwork.co"]:
    for path in [f"/api/v4/products/{new_id}", f"/api/products/{new_id}"]:
        url=base+path
        try:
            r=httpx.put(url, headers=h, json={"title":"test via seller"}, timeout=10)
            print(base, path, r.status_code, r.text[:300])
        except Exception as e:
            print(e)
