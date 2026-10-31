import pathlib, os, sys, json, httpx
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Authorization": f"Bearer {jwt}", "Content-Type":"application/json", "fw-locale":"th"}
# try gateway delete mutations
for q in [
    'mutation { deleteProduct(id: "33d0a220-adec-4fc3-9f9c-de1b981e031b") { id } }',
    'mutation { deleteProduct(productId: "33d0a220-adec-4fc3-9f9c-de1b981e031b") { id } }',
    'mutation { removeProduct(id: "33d0a220-adec-4fc3-9f9c-de1b981e031b") }',
    'mutation { archiveProduct(id: "33d0a220-adec-4fc3-9f9c-de1b981e031b") { id } }',
]:
    try:
        r=httpx.post("https://gateway.fastwork.co/graphql", headers=h, json={"query": q}, timeout=15)
        print(q[:50], r.status_code, r.text[:800])
    except Exception as e:
        print(e)
# also try REST delete with different base
for url in ["https://api.fastwork.co/api/v4/products/33d0a220-adec-4fc3-9f9c-de1b981e031b/delete","https://api.fastwork.co/api/products/33d0a220-adec-4fc3-9f9c-de1b981e031b"]:
    try:
        r=httpx.delete(url, headers=h, timeout=10)
        print(url, r.status_code, r.text[:500])
    except Exception as e:
        print(e)
