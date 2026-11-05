import httpx, re, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Cookie": f"accessToken={jwt}", "User-Agent":"Mozilla/5.0"}
r=httpx.get("https://seller.fastwork.co/", headers=h, timeout=15)
html=r.text
chunks=re.findall(r'/_next/static/chunks/[^"\']+\.js', html)
for url in chunks:
    full="https://seller.fastwork.co"+url
    txt=httpx.get(full, timeout=15).text
    if "getMyServices" in txt or "MyServices" in txt:
        print("FOUND getMyServices in", url)
        idx=txt.find("getMyServices")
        print(txt[idx-400:idx+600].replace("\n"," ")[:1000])
