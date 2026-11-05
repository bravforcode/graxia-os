import pathlib, os, json, sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

# load JWT
jwt=""
p=pathlib.Path(".env.local")
for l in p.read_text(encoding="utf-8").splitlines():
    if l.strip().startswith("FASTWORK_JWT="):
        jwt=l.split("=",1)[1].strip()
        break
if not jwt:
    print("no JWT"); sys.exit(1)

with sync_playwright() as pw:
    try:
        browser=pw.chromium.launch(channel="chrome", headless=False, args=["--disable-blink-features=AutomationControlled"])
    except:
        browser=pw.chromium.launch(headless=False)
    ctx=browser.new_context()
    # set cookie for fastwork.co
    ctx.add_cookies([{"name":"accessToken","value":jwt,"domain":"fastwork.co","path":"/"}])
    ctx.add_cookies([{"name":"accessToken","value":jwt,"domain":".fastwork.co","path":"/"}])
    page=ctx.new_page()

    def on_req(req):
        if "api.fastwork.co" in req.url and "product" in req.url.lower():
            print(f"\n>>> REQUEST {req.method} {req.url}")
            try:
                print("  postData:", req.post_data[:3000] if req.post_data else None)
            except: pass
            print("  headers:", {k:v for k,v in req.headers.items() if k.lower() in ['content-type','authorization']})
    page.on("request", on_req)
    page.on("response", lambda r: print(f"<<< RESPONSE {r.status} {r.url} -> {r.text()[:500] if 'product' in r.url.lower() else ''}") if "product" in r.url.lower() else None)

    print("เปิด seller หน้า...")
    page.goto("https://fastwork.co/seller/products", wait_until="domcontentloaded")
    print("หน้าโหลดแล้ว — กรุณาคลิก 'สร้างบริการ' / 'เพิ่มบริการ' แล้วกรอกฟอร์มจนกด 'บันทึก' — ผมจะดัก payload ให้")
    print("รอ 120 วินาที...")
    page.wait_for_timeout(120000)
    browser.close()
