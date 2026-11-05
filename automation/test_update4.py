import httpx, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Authorization": f"Bearer {jwt}", "Content-Type":"application/json", "fw-locale":"th"}
new_id="cd2050df-e4ff-49c2-9fc5-a7ebe3f220dc"
payload={"id": new_id, "title":"ทดสอบ อัปเดต via product.update","description":"desc"}
for url in [
    "https://api.fastwork.co/api/v4/product.update",
    "https://api.fastwork.co/api/v4/product_update",
    "https://api.fastwork.co/api/v4/products.update",
    "https://api.fastwork.co/api/v4/product/update",
]:
    try:
        r=httpx.post(url, headers=h, json=payload, timeout=10)
        print(url, r.status_code, r.text[:800].replace("\n"," "))
    except Exception as e:
        print(e)
# also try PUT with same
for url in [f"https://api.fastwork.co/api/v4/products/{new_id}/update"]:
    try:
        r=httpx.put(url, headers=h, json={"title":"test"}, timeout=10)
        print(url, r.status_code, r.text[:800])
    except Exception as e:
        print(e)
