import httpx, re, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Cookie": f"accessToken={jwt}", "User-Agent":"Mozilla/5.0"}
for path in ["/products/create","/product/create","/products/new","/create-product","/seller/products/create"]:
    url=f"https://seller.fastwork.co{path}"
    try:
        r=httpx.get(url, headers=h, timeout=15, follow_redirects=True)
        print(path, r.status_code, len(r.text))
        if r.status_code==200:
            m=re.findall(r'/_next/static/chunks/[^"\']+\.js', r.text)
            print(m[:10])
            # check for api in html
            if "api" in r.text.lower():
                print("api found")
    except Exception as e:
        print(e)
