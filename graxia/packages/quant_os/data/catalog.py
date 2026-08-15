"""
catalog.py — Data Catalog Loader

Loads data/catalog.yaml and provides query functions:
- get_assets_for_source(provider_name) → list of assets
- get_source_for_asset(symbol) → list of sources
- get_missing_keys() → list of missing API keys
- validate_catalog() → health check
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

CATALOG_PATH = Path(__file__).parent / "catalog.yaml"


def _load_catalog() -> dict:
    """Load catalog.yaml from project root."""
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"Catalog not found: {CATALOG_PATH}")
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_assets_for_source(provider: str) -> list[dict[str, Any]]:
    """Get all assets that use a specific provider."""
    catalog = _load_catalog()
    results = []

    for asset_class in ["forex", "metals", "indices", "crypto"]:
        class_data = catalog.get(asset_class, {})
        for category in ["pairs", "symbols"]:
            for item in class_data.get(category, []):
                symbol = item.get("symbol", "")
                for src in item.get("sources", []):
                    if src.get("provider") == provider:
                        results.append({
                            "symbol": symbol,
                            "asset_class": asset_class,
                            "provider": provider,
                            "instrument": src.get("instrument") or src.get("pair") or src.get("ticker"),
                            "timeframes": src.get("timeframes", []),
                            "schedule": src.get("schedule", ""),
                            "storage": src.get("storage", ""),
                        })
    return results


def get_source_for_asset(symbol: str) -> list[dict[str, Any]]:
    """Get all sources for a specific symbol."""
    catalog = _load_catalog()
    results = []

    for asset_class in ["forex", "metals", "indices", "crypto"]:
        class_data = catalog.get(asset_class, {})
        for category in ["pairs", "symbols"]:
            for item in class_data.get(category, []):
                if item.get("symbol", "").upper() == symbol.upper():
                    for src in item.get("sources", []):
                        results.append({
                            "provider": src.get("provider"),
                            "instrument": src.get("instrument") or src.get("pair") or src.get("ticker"),
                            "timeframes": src.get("timeframes", []),
                            "schedule": src.get("schedule", ""),
                            "storage": src.get("storage", ""),
                        })
    return results


def get_missing_keys() -> list[str]:
    """Check which API keys are missing from environment."""
    catalog = _load_catalog()
    missing = []

    # Check providers with api_key_env
    for section in ["onchain", "news", "alternative"]:
        providers = catalog.get(section, {})
        if isinstance(providers, dict):
            for key, val in providers.items():
                if isinstance(val, dict):
                    env_var = val.get("api_key_env", "")
                    status = val.get("status", "")
                    if env_var and status in ("missing", "not_configured"):
                        if not os.getenv(env_var):
                            missing.append(f"{section}/{key}: {env_var}")
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            env_var = item.get("api_key_env", "")
                            status = item.get("status", "")
                            if env_var and status in ("missing", "not_configured"):
                                if not os.getenv(env_var):
                                    missing.append(f"{section}/{item.get('name', key)}: {env_var}")
    return missing


def get_all_symbols() -> list[str]:
    """Get all tradeable symbols from catalog."""
    catalog = _load_catalog()
    symbols = []

    for asset_class in ["forex", "metals", "indices", "crypto"]:
        class_data = catalog.get(asset_class, {})
        for category in ["pairs", "symbols"]:
            for item in class_data.get(category, []):
                sym = item.get("symbol", "")
                if sym:
                    symbols.append(sym)
    return sorted(symbols)


def get_schedules() -> dict[str, str]:
    """Get all unique schedules and what they run."""
    catalog = _load_catalog()
    schedules = {}

    for asset_class in ["forex", "metals", "indices", "crypto"]:
        class_data = catalog.get(asset_class, {})
        for category in ["pairs", "symbols"]:
            for item in class_data.get(category, []):
                for src in item.get("sources", []):
                    sched = src.get("schedule", "")
                    provider = src.get("provider", "")
                    if sched:
                        key = f"{provider}:{sched}"
                        if key not in schedules:
                            schedules[key] = []
                        schedules[key].append(item.get("symbol", ""))

    return schedules


def validate_catalog() -> dict:
    """Run a health check on the catalog."""
    catalog = _load_catalog()
    symbols = get_all_symbols()
    missing = get_missing_keys()

    # Count sources per provider
    provider_counts: dict[str, int] = {}
    for asset_class in ["forex", "metals", "indices", "crypto"]:
        class_data = catalog.get(asset_class, {})
        for category in ["pairs", "symbols"]:
            for item in class_data.get(category, []):
                for src in item.get("sources", []):
                    p = src.get("provider", "unknown")
                    provider_counts[p] = provider_counts.get(p, 0) + 1

    return {
        "total_symbols": len(symbols),
        "symbols": symbols,
        "provider_counts": provider_counts,
        "missing_keys": missing,
        "macro_series": len(catalog.get("macro", {}).get("fred_series", [])),
        "cot_reports": len(catalog.get("cot", {}).get("reports", [])),
        "status": "healthy" if not missing else f"{len(missing)} missing API keys",
    }


if __name__ == "__main__":
    import json

    result = validate_catalog()
    print(json.dumps(result, indent=2))
