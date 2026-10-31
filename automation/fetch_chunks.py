import httpx, re, sys, pathlib
sys.stdout.reconfigure(encoding="utf-8")
chunks=["4174-1dbc72bc4d2c7262","6310-9f4021979d80a5cb","6018-45063a1edadadaa1","2953.ccb697a75b498b16","449.c88093fa71d17aac"]
for c in chunks:
    if "." in c and "-" not in c.split(".")[0]:
        # like 2953.ccb...
        url=f"https://fastwork.co/_next/static/chunks/{c}.js"
    else:
        url=f"https://fastwork.co/_next/static/chunks/{c}.js"
    try:
        r=httpx.get(url, timeout=30)
        print(c, r.status_code, len(r.text))
        s=r.text
        # save
        pathlib.Path(f"C:/Users/menum/AppData/Local/Temp/opencode/fw_{c}.js").write_text(s, encoding="utf-8")
        # search
        for pat in ["/api/v4/products","/products","attribute_value","tag_ids"]:
            if pat in s:
                idx=s.find(pat)
                print("  found", pat, s[max(0,idx-300):idx+600].replace("\n"," ")[:800])
    except Exception as e:
        print(e)
