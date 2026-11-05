import httpx, sys
sys.stdout.reconfigure(encoding="utf-8")
for url in ["https://api.fastwork.co/docs","https://api.fastwork.co/swagger","https://api.fastwork.co/openapi.json","https://api.fastwork.co/api/docs"]:
    try:
        r=httpx.get(url, timeout=10)
        print(url, r.status_code, r.text[:500].replace("\n"," ")[:500])
    except Exception as e:
        print(e)
