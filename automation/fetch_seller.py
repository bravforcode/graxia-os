import httpx, re, sys
sys.stdout.reconfigure(encoding="utf-8")
r=httpx.get('https://fastwork.co/start-selling', timeout=20, headers={'User-Agent':'Mozilla/5.0'})
print(r.status_code)
html=r.text
m=re.findall(r'src="([^"]*start-selling[^"]*)"', html)
print("start-selling chunks:", m[:5])
# find all _next scripts
m2=re.findall(r'/_next/static/chunks/[^"\']+', html)
print("chunks sample", m2[:5])
# find API URL
if 'api.fastwork.co' in html:
    print("api found in html")
    # print snippet
    idx=html.find('api.fastwork.co')
    print(html[idx-500:idx+500][:1000])
