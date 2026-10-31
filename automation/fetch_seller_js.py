import httpx, re, sys
sys.stdout.reconfigure(encoding="utf-8")
url="https://seller.fastwork.co/assets/index-8VWLOXkh.js"
r=httpx.get(url, timeout=30)
print(len(r.text))
# search product
for pat in ["/api/v4/products","/products","attribute_value","tag_ids","category_id"]:
    if pat in r.text:
        idx=r.text.find(pat)
        print(pat, r.text[max(0,idx-400):idx+600].replace("\n"," ")[:900])
        print("---")
# save
open("C:/Users/menum/AppData/Local/Temp/seller_index.js","w",encoding="utf-8").write(r.text)
print("saved")
