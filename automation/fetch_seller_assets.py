import httpx, re, sys
sys.stdout.reconfigure(encoding="utf-8")
r=httpx.get("https://seller.fastwork.co/", timeout=20)
html=r.text
print(re.findall(r'src="([^"]+)"', html))
# also fetch authorize
r2=httpx.get("https://seller.fastwork.co/assets/authorize--09_7aGs.js", timeout=20)
print(len(r2.text), r2.text[:500])
