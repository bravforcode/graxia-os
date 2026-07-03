"""Verify reproducibility of backtest results."""
import hashlib
import sys
from pathlib import Path


def main():
    data_dir = Path(__file__).resolve().parent.parent / "data"
    if not data_dir.exists():
        print("No data directory")
        sys.exit(1)
    csvs = list(data_dir.glob("*.csv"))
    if not csvs:
        print("No CSV files to verify")
        return
    for csv in sorted(csvs):
        h = hashlib.sha256(csv.read_bytes()).hexdigest()
        print(f"{csv.name}: {h[:16]}")


if __name__ == "__main__":
    main()
