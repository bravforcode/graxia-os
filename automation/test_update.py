import os, httpx, pathlib, json, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
for l in p.read_text(encoding="utf-8").splitlines():
    if l.strip().startswith("FASTWORK_JWT="):
        jwt=l.split("=",1)[1].strip()
        break
h={"Authorization": f"Bearer {jwt}", "Content-Type":"application/json", "fw-locale":"th"}
pid="cd2050df-e4ff-49c2-9fc5-a7ebe3f220dc"
payload={"title":"ทดสอบสร้างสินค้า แก้ไข","description":"ทดสอบรายละเอียด แก้ไข"}
for suffix in ["/detail","/info","/content","/update","/edit","/draft",""]:
    for method in ["PUT","POST","PATCH"]:
        url=f"https://api.fastwork.co/api/v4/products/{pid}{suffix}"
        try:
            if method=="PUT":
                r=httpx.put(url, headers=h, json=payload, timeout=10)
            elif method=="POST":
                r=httpx.post(url, headers=h, json=payload, timeout=10)
            else:
                r=httpx.patch(url, headers=h, json=payload, timeout=10)
            if r.status_code not in [404,405]:
                print(method, url, r.status_code, r.text[:800].replace("\n"," "))
        except Exception as e:
            print(e)
