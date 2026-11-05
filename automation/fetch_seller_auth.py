import httpx, re, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Cookie": f"accessToken={jwt}", "User-Agent":"Mozilla/5.0"}
r=httpx.get("https://seller.fastwork.co/", headers=h, timeout=15)
html=r.text
# find next static chunks
chunks=re.findall(r'/_next/static/chunks/[^"\']+\.js', html)
print("chunks", chunks[:20])
# also find assets
assets=re.findall(r'/assets/[^"\']+\.js', html)
print("assets", assets[:10])
# fetch each and search for product API
for url in chunks[:10]:
    full="https://seller.fastwork.co"+url
    try:
        txt=httpx.get(full, timeout=15).text
        if "api" in txt.lower() and "product" in txt.lower():
            print(f"FOUND in {url}")
            idx=txt.lower().find("product")
            print(txt[max(0,idx-500):idx+800].replace("\n"," ")[:1200])
    except Exception as e:
        print(e)
for url in assets:
    full="https://seller.fastwork.co"+url
    try:
        txt=httpx.get(full, timeout=15).text
        if "api/v4" in txt:
            print(f"FOUND api in {url}")
            idx=txt.find("api/v4")
            print(txt[max(0,idx-500):idx+800].replace("\n"," ")[:1200])
    except Exception as e:
        print(e)
