"""
notebooklm_combine_all.py — Combine ALL vault data into one file for manual upload to NotebookLM
Output: notebooklm_all_trading_data.md
User uploads this single file to NotebookLM via web UI
"""

from pathlib import Path
import os

VAULT = Path(os.environ["USERPROFILE"]) / "Documents" / "ObsidianVault" / "Second Brain"
OUTPUT = Path(__file__).parent / "notebooklm_all_trading_data.md"


def read_file(p):
    try:
        return p.read_text(encoding="utf-8")
    except:
        return ""


sections = []

# Header
sections.append("# Master Trading Intelligence — All Data\n")
sections.append("This notebook contains ALL trading data from the quant_os system.\n")
sections.append("---\n")

# Strategies
sections.append("\n# PART 1: TRADING STRATEGIES\n")
d = VAULT / "skills/trading/strategies"
for f in sorted(d.glob("*.md")):
    if f.name == "Index.md":
        continue
    txt = read_file(f)
    if len(txt.strip()) > 50:
        sections.append(f"\n## {f.stem}\n")
        sections.append(txt)

# Backtest Results
sections.append("\n\n# PART 2: BACKTEST RESULTS\n")
d = VAULT / "03-resources/trading/backtest"
for f in sorted(d.glob("*.md")):
    txt = read_file(f)
    if len(txt.strip()) > 50:
        sections.append(f"\n## {f.stem}\n")
        sections.append(txt)

# Macro Analysis
sections.append("\n\n# PART 3: MACRO ANALYSIS\n")
d = VAULT / "03-resources/trading/macro"
for f in sorted(d.glob("*.md")):
    txt = read_file(f)
    if len(txt.strip()) > 50:
        sections.append(f"\n## {f.stem}\n")
        sections.append(txt)

# ML Models
sections.append("\n\n# PART 4: ML MODELS\n")
d = VAULT / "03-resources/trading/models"
for f in sorted(d.glob("*.md")):
    if f.name == "Index.md":
        continue
    txt = read_file(f)
    if len(txt.strip()) > 50:
        sections.append(f"\n## {f.stem}\n")
        sections.append(txt)

# Trade Journal
sections.append("\n\n# PART 5: TRADE JOURNAL\n")
d = VAULT / "07-Daily/trades"
for f in sorted(d.glob("*.md")):
    txt = read_file(f)
    if len(txt.strip()) > 50:
        sections.append(f"\n## {f.stem}\n")
        sections.append(txt)

# Risk, Regime, Signals, Attribution, Ensemble
for sub_name, sub_path in [
    ("RISK MANAGEMENT", "03-resources/trading/risk"),
    ("REGIME DETECTION", "03-resources/trading/regime"),
    ("SIGNAL QUALITY", "03-resources/trading/signals"),
    ("ATTRIBUTION", "03-resources/trading/attribution"),
    ("ENSEMBLE", "03-resources/trading/ensemble"),
]:
    d = VAULT / sub_path
    if not d.exists():
        continue
    files = list(d.glob("*.md"))
    if not files:
        continue
    sections.append(f"\n\n# PART: {sub_name}\n")
    for f in sorted(files):
        txt = read_file(f)
        if len(txt.strip()) > 50:
            sections.append(f"\n## {f.stem}\n")
            sections.append(txt)

# Combine
combined = "\n".join(sections)
OUTPUT.write_text(combined, encoding="utf-8")

print(f"Created: {OUTPUT}")
print(f"Size: {len(combined):,} chars ({len(combined)/1000:.0f} KB)")
print(f"Sections: {combined.count('## ')} subsections")
print()
print("NEXT STEP:")
print("  1. Open https://notebooklm.google.com/")
print("  2. Open your notebook")
print("  3. Click 'Add source' -> 'Copied text'")
print(f"  4. Paste the content from: {OUTPUT}")
print("  5. Or upload the .md file directly")
