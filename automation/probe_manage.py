import httpx, re, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Cookie": f"accessToken={jwt}", "User-Agent":"Mozilla/5.0"}
for path in ["/account/products","/manage-product","/manage-products","/my-products","/product/create","/products/create","/start-selling/create"]:
    url=f"https://fastwork.co{path}"
    r=httpx.get(url, headers=h, timeout=15, follow_redirects=True)
    print(path, r.status_code, r.url, len(r.text))
    if r.status_code==200 and "product" in r.text.lower():
        print(r.text[:1000].replace("\n"," ")[:1000])
