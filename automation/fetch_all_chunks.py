import httpx, re, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Cookie": f"accessToken={jwt}", "User-Agent":"Mozilla/5.0"}
r=httpx.get("https://seller.fastwork.co/", headers=h, timeout=15)
html=r.text
chunks=re.findall(r'/_next/static/chunks/[^"\']+\.js', html)
print("found", len(chunks), chunks)
for url in chunks:
    full="https://seller.fastwork.co"+url
    try:
        txt=httpx.get(full, timeout=15).text
        # search for product-related API
        if "product" in txt.lower() and "api" in txt.lower():
            print(f"\n=== {url} ===")
            # find api/v4
            for m in re.finditer(r"api/v4[^\"]*", txt):
                start=max(0,m.start()-300)
                print(txt[start:m.end()+500].replace("\n"," ")[:1200])
                print("---")
        # also search for title in same file as product
        if "title" in txt.lower() and "product" in txt.lower():
            # count
            pass
    except Exception as e:
        print(e)
