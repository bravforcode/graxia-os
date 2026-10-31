import httpx, re, sys, pathlib
sys.stdout.reconfigure(encoding="utf-8")
url="https://fastwork.co/_next/static/chunks/pages/start-selling-2568bb244561824e.js"
r=httpx.get(url, timeout=30)
print("status", r.status_code, "len", len(r.text))
s=r.text
# save
pathlib.Path("C:/Users/menum/AppData/Local/Temp/opencode/fw_start-selling.js").write_text(s, encoding="utf-8")
# search for product creation
for pat in ["/api/v4/products", "product", "packages", "category_id", "subcategory_id"]:
    if pat in s:
        print(f"found {pat}")
        idx=s.find(pat)
        print(s[max(0,idx-400):idx+800].replace("\n"," ")[:900])
        print("---")
# also check for create
