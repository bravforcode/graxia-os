import httpx, re, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Cookie": f"accessToken={jwt}", "User-Agent":"Mozilla/5.0"}
r=httpx.get("https://seller.fastwork.co/", headers=h, timeout=15)
html=r.text
# search for product id or slug
if "a12ec038" in html:
    print("found a12ec in html")
    idx=html.find("a12ec038")
    print(html[idx-500:idx+500].replace("\n"," ")[:1000])
else:
    print("a12ec not in html")
# search for any product link
m=re.findall(r'href="[^"]*product[^"]*"', html, re.IGNORECASE)
print(m[:10])
m2=re.findall(r'"/api[^"]*"', html)
print(m2[:10])
# check for seller api
if "seller" in html.lower():
    idx=html.lower().find("seller")
    print(html[idx-500:idx+500][:1000])
