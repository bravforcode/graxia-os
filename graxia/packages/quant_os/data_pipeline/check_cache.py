import json
d = json.loads(open(r"C:\Users\menum\graxia os\graxia\packages\quant_os\data_pipeline\storage\market_cache.json").read())
for k, v in d.items():
    print(f"  {k}: {v['close']:.2f} ({v['updated'][:16]})")
