import pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
new_id="cd2050df-e4ff-49c2-9fc5-a7ebe3f220dc"

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    ctx=browser.new_context()
    # need to set cookie? fetch will use Authorization header, not cookie, so not needed
    page=ctx.new_page()
    page.goto("https://fastwork.co", wait_until="domcontentloaded")
    payload={"title":"ทดสอบ แก้ไข via browser fetch","description":"desc via browser"}
    res=page.evaluate("""async ({payload, jwt, pid}) => {
        const r = await fetch(`https://api.fastwork.co/api/v4/products/${pid}`, {
            method:"PUT",
            headers:{"Content-Type":"application/json","Authorization":"Bearer "+jwt,"fw-locale":"th"},
            body: JSON.stringify(payload)
        });
        const txt = await r.text();
        return {status: r.status, body: txt.slice(0,2000), headers: Object.fromEntries(r.headers.entries())};
    }""", {"payload": payload, "jwt": jwt, "pid": new_id})
    print(res)
    browser.close()
