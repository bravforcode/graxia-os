import httpx, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Authorization": f"Bearer {jwt}", "Content-Type":"application/json", "fw-locale":"th"}
new_id="cd2050df-e4ff-49c2-9fc5-a7ebe3f220dc"
suffixes=["draft","general","content","info","detail","basic","worksteps","media","images","tags","attributes","description","title","data","product","info","edit","save","update"]
for suffix in suffixes:
    for method in ["PUT","POST","PATCH"]:
        url=f"https://api.fastwork.co/api/v4/products/{new_id}/{suffix}"
        try:
            if method=="PUT":
                r=httpx.put(url, headers=h, json={"title":"test"}, timeout=8)
            elif method=="POST":
                r=httpx.post(url, headers=h, json={"title":"test"}, timeout=8)
            else:
                r=httpx.patch(url, headers=h, json={"title":"test"}, timeout=8)
            if r.status_code not in [404,405]:
                print(f"{method} {suffix} {r.status_code} {r.text[:400]}")
        except Exception as e:
            pass
# also try without suffix but with different method
for method in ["PATCH","POST"]:
    url=f"https://api.fastwork.co/api/v4/products/{new_id}"
    try:
        if method=="PATCH":
            r=httpx.patch(url, headers=h, json={"title":"test"}, timeout=8)
        else:
            r=httpx.post(url, headers=h, json={"title":"test"}, timeout=8)
        if r.status_code not in [404,405]:
            print(f"{method} no suffix {r.status_code} {r.text[:400]}")
    except: pass
