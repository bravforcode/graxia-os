import httpx, re, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Cookie": f"accessToken={jwt}", "User-Agent":"Mozilla/5.0"}
pid="cd2050df-e4ff-49c2-9fc5-a7ebe3f220dc"
for path in [f"/products/{pid}/edit", f"/product/{pid}/edit", f"/products/{pid}", f"/product/{pid}"]:
    url=f"https://seller.fastwork.co{path}"
    r=httpx.get(url, headers=h, timeout=15, follow_redirects=True)
    print(path, r.status_code, len(r.text))
    if r.status_code==200:
        chunks=re.findall(r'/_next/static/chunks/[^"\']+\.js', r.text)
        print(chunks[:10])
        if len(chunks)>0:
            # fetch one
            txt=httpx.get("https://seller.fastwork.co"+chunks[0], timeout=15).text
            print(txt[:500])
