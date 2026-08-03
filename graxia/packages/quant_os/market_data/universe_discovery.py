"""Broker symbol discovery (Phase 1).

Enumerates MT5 symbols via symbols_get(), classifies them into the asset-class
allowlist (forex / metals / commodities / indices), sanity-checks spread, and
writes new symbols into tradeable_universe.json as "candidate" entries.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from broker.mt5_gateway import Mt5UnavailableError, get_current_tick, get_symbols

ASSET_CLASS_ALLOWLIST: frozenset[str] = frozenset({"forex", "metals", "commodities", "indices"})
MAX_SANITY_SPREAD_BPS: float = 50.0
SYMBOL_NAME_RE = re.compile(r"^[A-Z0-9_]{2,12}$")

# path-based classification hints; unknown paths are rejected.
# Order matters: more specific paths (Metals) must precede generic ones (Forex).
_PATH_HINTS: list[tuple[str, str]] = [
    ("Metals", "metals"),
    ("Commodities", "commodities"),
    ("Energies", "commodities"),
    ("Indices", "indices"),
    ("Forex", "forex"),
]


def classify_symbol(name: str, path: str) -> str | None:
    """Return the asset class for a broker symbol, or None to reject."""
    if not SYMBOL_NAME_RE.match(name):
        return None
    for hint, asset_class in _PATH_HINTS:
        if hint.lower() in path.lower():
            return asset_class
    return None


def spread_bps_from_tick(tick: dict) -> float:
    """Convert a get_current_tick() dict into spread in basis points."""
    mid = (tick["bid"] + tick["ask"]) / 2.0
    if mid <= 0:
        return float("inf")
    return (tick["ask"] - tick["bid"]) / mid * 10_000.0


def sanity_check(symbol: str) -> bool:
    """A symbol passes the sanity bar if we can fetch a tick and its spread
    is not absurd. Fail-closed: any MT5 error rejects the symbol."""
    try:
        tick = get_current_tick(symbol)
    except Mt5UnavailableError:
        return False
    return spread_bps_from_tick(tick) <= MAX_SANITY_SPREAD_BPS


def discover_new_candidates(
    symbols: list[dict],
    universe: dict,
) -> list[dict]:
    """Return candidate entries for broker symbols not already in any
    status array of the universe."""
    known = {
        entry["symbol"]
        for key in ("tradeable", "measuring", "verifying", "candidate", "excluded")
        for entry in universe.get(key, [])
    }
    candidates: list[dict] = []
    for s in symbols:
        asset_class = classify_symbol(s["name"], s.get("path", ""))
        if asset_class is None or asset_class not in ASSET_CLASS_ALLOWLIST:
            continue
        if s["name"] in known:
            continue
        candidates.append(
            {
                "symbol": s["name"],
                "asset_class": asset_class,
                "broker_path": s.get("path", ""),
            }
        )
    return candidates


def update_universe(universe_path: str | Path, candidates: list[dict]) -> list[str]:
    """Append candidate entries to tradeable_universe.json (atomic write).
    Returns the symbols added."""
    path = Path(universe_path)
    universe = json.loads(path.read_text(encoding="utf-8"))
    added: list[str] = []
    candidate_list = universe.setdefault("candidate", [])
    existing = {e["symbol"] for e in candidate_list}
    for entry in candidates:
        if entry["symbol"] in existing:
            continue
        candidate_list.append(entry)
        existing.add(entry["symbol"])
        added.append(entry["symbol"])
    if added:
        universe["_meta"]["updated"] = datetime.now(UTC).date().isoformat()
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".universe_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(universe, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, str(path))
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover new broker symbols as universe candidates")
    parser.add_argument(
        "--universe", default=str(Path(__file__).resolve().parent.parent / "config" / "tradeable_universe.json")
    )
    parser.add_argument("--write", action="store_true", help="Write candidates into the universe file")
    args = parser.parse_args()

    universe_path = Path(args.universe)
    universe = json.loads(universe_path.read_text(encoding="utf-8"))

    symbols = get_symbols()
    candidates = discover_new_candidates(symbols, universe)
    print(f"Broker symbols enumerated: {len(symbols)}; new candidates: {len(candidates)}")
    for c in candidates:
        print(f"  candidate: {c['symbol']} ({c['asset_class']})")

    if args.write and candidates:
        added = update_universe(universe_path, candidates)
        print(f"Wrote {len(added)} candidates to {universe_path}")
    elif args.write:
        print("No new candidates to write.")


if __name__ == "__main__":
    main()
