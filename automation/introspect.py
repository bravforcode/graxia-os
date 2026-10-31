import os, httpx, pathlib, json, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
for l in p.read_text(encoding="utf-8").splitlines():
    if l.strip().startswith("FASTWORK_JWT="):
        os.environ["FASTWORK_JWT"]=l.split("=",1)[1].strip()
        break
jwt=os.environ["FASTWORK_JWT"]
h={"Authorization": f"Bearer {jwt}", "Content-Type":"application/json", "fw-locale":"th"}
q=json.dumps({"query":"{ __schema { queryType { name } mutationType { name } } }"})
r=httpx.post("https://gateway.fastwork.co/graphql", headers=h, content=q, timeout=15)
print(r.status_code)
print(r.text[:4000])
