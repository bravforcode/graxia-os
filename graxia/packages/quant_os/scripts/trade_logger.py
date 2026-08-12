import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "paper_trade_log.csv"
INTENDED_STOP = 6.30
HEADERS = [
    "timestamp", "direction", "entry_price", "exit_price", "exit_reason",
    "stop_filled_at", "intended_stop", "slippage", "pnl_gross", "pnl_net",
    "event_flag", "notes",
]
VALID_REASONS = {"natural", "stop_hit", "gap_through"}
VALID_DIRECTIONS = {"long", "short"}
VALID_EVENTS = {"none", "nfp", "fomc", "cpi", "other"}


def ensure_headers():
    if not CSV_PATH.exists():
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CSV_PATH, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)


def validate(row: dict) -> list[str]:
    errors = []
    if row["direction"] not in VALID_DIRECTIONS:
        errors.append(f"direction must be one of {VALID_DIRECTIONS}")
    if row["exit_reason"] not in VALID_REASONS:
        errors.append(f"exit_reason must be one of {VALID_REASONS}")
    if row.get("event_flag", "none") not in VALID_EVENTS:
        errors.append(f"event_flag must be one of {VALID_EVENTS}")
    for field in ("entry_price", "exit_price"):
        try:
            float(row[field])
        except (ValueError, KeyError):
            errors.append(f"{field} must be a number")
    if row["exit_reason"] in ("stop_hit", "gap_through"):
        if not row.get("stop_filled_at", "").strip():
            errors.append("stop_filled_at required when exit_reason is stop_hit or gap_through")
        else:
            try:
                float(row["stop_filled_at"])
            except ValueError:
                errors.append("stop_filled_at must be a number")
    return errors


def compute_pnl(row: dict) -> tuple[float, float]:
    entry = float(row["entry_price"])
    exit_ = float(row["exit_price"])
    mult = 1 if row["direction"] == "long" else -1
    pnl_gross = round((exit_ - entry) * mult, 2)
    pnl_net = pnl_gross
    return pnl_gross, pnl_net


def compute_slippage(row: dict) -> float:
    if row["exit_reason"] not in ("stop_hit", "gap_through"):
        return 0.0
    if not row.get("stop_filled_at", "").strip():
        return 0.0
    entry = float(row["entry_price"])
    fill = float(row["stop_filled_at"])
    actual_stop = abs(fill - entry)
    return round(actual_stop - INTENDED_STOP, 2)


def build_row(parts: list[str], notes: str = "") -> dict:
    ts = parts[0] if parts[0] else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    direction = parts[1]
    entry_price = parts[2]
    exit_price = parts[3]
    exit_reason = parts[4]
    stop_filled_at = parts[5] if len(parts) > 5 else ""
    raw_slippage = parts[6] if len(parts) > 6 else ""
    event_flag = parts[7] if len(parts) > 7 else "none"

    row = {
        "timestamp": ts,
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "stop_filled_at": stop_filled_at,
        "intended_stop": str(INTENDED_STOP),
        "slippage": raw_slippage,
        "pnl_gross": "",
        "pnl_net": "",
        "event_flag": event_flag,
        "notes": notes,
    }
    return row


def append_row(row: dict):
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writerow(row)


def interactive_loop():
    print("Paper Trade Logger — XAUUSD (stop $6.30)")
    print("Fields: timestamp|direction|entry_price|exit_price|exit_reason|stop_filled_at|slippage|event_flag")
    print("  event_flag: none|nfp|fomc|cpi|other (default: none)")
    print("Press Enter on empty line to quit.\n")
    count = 0
    while True:
        raw = input("trade> ").strip()
        if not raw:
            break
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) < 5:
            print("  ERROR: need at least timestamp|direction|entry_price|exit_price|exit_reason")
            continue
        row = build_row(parts)
        errs = validate(row)
        if errs:
            for e in errs:
                print(f"  ERROR: {e}")
            continue
        pnl_gross, pnl_net = compute_pnl(row)
        row["pnl_gross"] = str(pnl_gross)
        row["pnl_net"] = str(pnl_net)
        if not row["slippage"].strip():
            row["slippage"] = str(compute_slippage(row))
        append_row(row)
        count += 1
        print(f"  OK  — PnL: ${pnl_gross:.2f} (${pnl_net:.2f} net)")
    print(f"\n{count} trade(s) logged to {CSV_PATH}")


def single_entry(entry_str: str):
    parts = [p.strip() for p in entry_str.split("|")]
    if len(parts) < 5:
        print("ERROR: need at least timestamp|direction|entry_price|exit_price|exit_reason", file=sys.stderr)
        sys.exit(1)
    row = build_row(parts)
    errs = validate(row)
    if errs:
        for e in errs:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    pnl_gross, pnl_net = compute_pnl(row)
    row["pnl_gross"] = str(pnl_gross)
    row["pnl_net"] = str(pnl_net)
    if not row["slippage"].strip():
        row["slippage"] = str(compute_slippage(row))
    append_row(row)
    print(f"Logged: ${pnl_gross:.2f} gross / ${pnl_net:.2f} net")


def main():
    ensure_headers()
    parser = argparse.ArgumentParser(description="XAUUSD paper trade logger (stop $6.30)")
    parser.add_argument("--entry", help="Pipe-separated: timestamp|direction|entry_price|exit_price|exit_reason|stop_filled_at|slippage|event_flag")
    args = parser.parse_args()
    if args.entry:
        single_entry(args.entry)
    else:
        interactive_loop()


if __name__ == "__main__":
    main()
