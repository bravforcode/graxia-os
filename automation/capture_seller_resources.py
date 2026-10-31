import pathlib, os, sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright
import httpx

# load JWT
jwt=""
p=pathlib.Path(".env.local")
for l in p.read_text(encoding="utf-8").splitlines():
    if l.strip().startswith("FASTWORK_JWT="):
        jwt=l.split("=",1)[1].strip()
        break

with sync_playwright() as pw:
    try:
        browser=pw.chromium.launch(channel="chrome", headless=False, args=["--disable-blink-features=AutomationControlled"])
    except:
        browser=pw.chromium.launch(headless=False)
    ctx=browser.new_context()
    ctx.add_cookies([{"name":"accessToken","value":jwt,"domain":"fastwork.co","path":"/"}])
    ctx.add_cookies([{"name":"accessToken","value":jwt,"domain":".fastwork.co","path":"/"}])
    # also for seller domain
    ctx.add_cookies([{"name":"accessToken","value":jwt,"domain":"seller.fastwork.co","path":"/"}])
    page=ctx.new_page()
    # capture requests
    reqs=[]
    def on_req(r):
        if "fastwork" in r.url and ("product" in r.url.lower() or "api" in r.url):
            reqs.append((r.method, r.url, r.post_data))
            print(f"REQ {r.method} {r.url} {str(r.post_data)[:300] if r.post_data else ''}")
    page.on("request", on_req)
    print("goto seller")
    page.goto("https://seller.fastwork.co", wait_until="domcontentloaded", timeout=20000)
    print("title", page.title())
    # list resources
    urls=page.evaluate("() => performance.getEntriesByType('resource').map(r=>r.name)")
    print("resources", urls[:20])
    # try to fetch each js and search
    for u in urls:
        if u.endswith(".js"):
            try:
                txt=httpx.get(u, timeout=10).text
                if "api/v4/products" in txt:
                    print(f"FOUND product API in {u}")
                    idx=txt.find("api/v4/products")
                    print(txt[max(0,idx-500):idx+800].replace("\n"," ")[:1000])
            except: pass
    print("wait 15s for manual")
    page.wait_for_timeout(15000)
    print("captured", len(reqs))
    for m,u,d in reqs:
        print(m,u,d[:500] if d else "")
    browser.close()
