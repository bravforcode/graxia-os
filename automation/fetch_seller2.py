import httpx, re, sys
sys.stdout.reconfigure(encoding="utf-8")
# try seller domain
for url in ["https://seller.fastwork.co", "https://fastwork.co/seller/products"]:
    try:
        r=httpx.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0"}, follow_redirects=True)
        print(url, r.status_code, len(r.text))
        print(r.text[:1500].replace("\n"," ")[:1500])
        print("---")
    except Exception as e:
        print(e)
