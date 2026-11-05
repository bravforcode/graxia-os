import pathlib, os, sys, json
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx=browser.new_context()
    page=ctx.new_page()
    page.goto("https://fastwork.co", wait_until="domcontentloaded")
    # test fetch via evaluate
    for payload in [
        {"category_id":"59ee9443-71d7-4a10-bf5d-79bcb60565ed","subcategory_id":"6ed71488-478d-4e4a-a1f3-d7cf56ce9340","title":"ทดสอบ A","description":"desc A","attribute_value_ids":[],"tag_ids":[]},
        {"categoryId":"59ee9443-71d7-4a10-bf5d-79bcb60565ed","subcategoryId":"6ed71488-478d-4e4a-a1f3-d7cf56ce9340","name":"ทดสอบ B","description":"desc B"},
        {"title":"ทดสอบ C","description":"desc C","category_id":"59ee9443-71d7-4a10-bf5d-79bcb60565ed","subcategory_id":"6ed71488-478d-4e4a-a1f3-d7cf56ce9340","images":[]},
    ]:
        res=page.evaluate("""async ({payload, jwt}) => {
            const r = await fetch("https://api.fastwork.co/api/v4/products", {
                method:"POST",
                headers:{"Content-Type":"application/json","Authorization":"Bearer "+jwt,"fw-locale":"th"},
                body: JSON.stringify(payload)
            });
            const txt = await r.text();
            return {status: r.status, body: txt.slice(0,1000)};
        }""", {"payload": payload, "jwt": jwt})
        print("payload", list(payload.keys()), res)
    browser.close()
