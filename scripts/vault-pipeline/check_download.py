"""check_download.py — Check downloaded file"""

import os

f = r"C:\Users\menum\graxia os\graxia\packages\quant_os\fin_model\fin_model.tar.gz"
print(f"Size: {os.path.getsize(f)} bytes")

with open(f, "rb") as fh:
    header = fh.read(100)
    print(f"Header bytes: {header[:20]}")
    print(f"Is gzip: {header[:2] == b'\\x1f\\x8b'}")
    # Check if it's HTML
    try:
        text = header.decode("utf-8", errors="ignore")
        if "<html" in text.lower() or "<!doctype" in text.lower():
            print("ERROR: Downloaded HTML page, not the actual file!")
        else:
            print(f"First chars: {text[:50]}")
    except:
        pass
