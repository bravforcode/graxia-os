import httpx, json, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
p=pathlib.Path(".env.local")
jwt=[l.split("=",1)[1].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip().startswith("FASTWORK_JWT=")][0]
h={"Authorization": f"Bearer {jwt}", "Content-Type":"application/json", "fw-locale":"th"}
queries=[
    'mutation { updateProduct(id: "33d0a220-adec-4fc3-9f9c-de1b981e031b", input: {title: "test"}) { id title } }',
    'mutation { createProduct(input: {title: "test", categoryId: "59ee9443-71d7-4a10-bf5d-79bcb60565ed"}) { id } }',
    'mutation { updateProductTags(productId: "33d0a220-adec-4fc3-9f9c-de1b981e031b", tagIds: []) { id } }',
]
for q in queries:
    r=httpx.post("https://gateway.fastwork.co/graphql", headers=h, json={"query": q}, timeout=15)
    print(q[:60], r.text[:1500].replace("\n"," "))
