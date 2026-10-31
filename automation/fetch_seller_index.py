import httpx, re, sys
sys.stdout.reconfigure(encoding="utf-8")
url="https://seller.fastwork.co/_next/static/chunks/pages/index-249744576f96013f.js"
r=httpx.get(url, timeout=20)
print(len(r.text))
txt=r.text
for pat in ["api", "product", "category", "subcategory"]:
    if pat in txt.lower():
        idx=txt.lower().find(pat)
        print(pat, txt[max(0,idx-400):idx+800].replace("\n"," ")[:1000])
        print("---")
