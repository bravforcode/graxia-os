"""Create EURUSD data manifests."""
import hashlib
import json
from pathlib import Path

DATA_DIR = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\data")
MANIFEST_DIR = DATA_DIR / "manifests"
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

for tf in ["D1", "H1", "M15"]:
    csv = DATA_DIR / f"EURUSD_{tf}.csv"
    if not csv.exists():
        print(f"SKIP {tf}: file not found")
        continue
    content = csv.read_text()
    sha = hashlib.sha256(content.encode()).hexdigest()
    lines = content.strip().split("\n")
    header = lines[0].split(",")
    first = lines[1].split(",")
    last = lines[-1].split(",")
    manifest = {
        "symbol": "EURUSD",
        "timeframe": tf,
        "source": "MT5",
        "rows": len(lines) - 1,
        "start_date": first[0],
        "end_date": last[0],
        "sha256": sha,
        "columns": header,
        "created_at": "2026-06-22",
    }
    out = MANIFEST_DIR / f"EURUSD_{tf}_manifest.json"
    out.write_text(json.dumps(manifest, indent=2))
    print(f"Created {out.name}: {manifest['rows']} rows, SHA={sha[:16]}...")
