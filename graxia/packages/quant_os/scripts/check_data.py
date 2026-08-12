"""Check data inventory after mega_download."""
from pathlib import Path
from collections import defaultdict
import csv

d = Path("data")
files = sorted(d.glob("*.csv"))
print(f"Total CSV files: {len(files)}")
total_size = sum(f.stat().st_size for f in files)
print(f"Total size: {total_size/1024/1024:.1f} MB")

total_bars = 0
by_sym = defaultdict(list)
for f in files:
    stem = f.stem
    parts = stem.split("_")
    if len(parts) >= 2:
        sym = parts[0]
        tf = "_".join(parts[1:])
        by_sym[sym].append(tf)
    else:
        by_sym["OTHER"].append(stem)
    if f.stat().st_size > 100 and f.name.startswith(("EUR","GBP","USD","AUD","NZD","XAU","XAG","XPT","XPD","US30","NAS","BTC","ETH")):
        with open(f, encoding="utf-8") as fh:
            total_bars += sum(1 for _ in csv.reader(fh)) - 1

print(f"Total estimated bars: {total_bars:,}")
print()

all_tfs = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]
for sym in sorted(by_sym):
    tfs = sorted(by_sym[sym])
    if sym == "OTHER":
        continue
    missing = [tf for tf in all_tfs if tf not in tfs]
    extra = [tf for tf in tfs if tf not in all_tfs]
    parts = []
    if missing:
        parts.append("MISSING: " + ", ".join(missing))
    if extra:
        parts.append("EXTRA: " + ", ".join(extra))
    suffix = " [" + "; ".join(parts) + "]" if parts else ""
    print(f"  {sym}: {len(tfs)} TFs{suffix}")

if "OTHER" in by_sym:
    print(f"  OTHER files: {by_sym['OTHER']}")
