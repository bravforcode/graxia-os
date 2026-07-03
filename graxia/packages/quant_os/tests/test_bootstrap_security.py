"""
Bootstrap Security Tests — SQL injection via table/symbol names.

verify_bootstrap.py constructs SQL strings from table names returned by
DuckDB SHOW TABLES.  If an attacker can influence table or symbol names,
f'{t[0]}' interpolation is vulnerable.

Tests validate that the bootstrap script rejects or safely handles
malicious identifiers.
"""

import re

import pytest


# ---------------------------------------------------------------------------
# Patterns that should never appear in SQL-interpolated identifiers
# ---------------------------------------------------------------------------

# Characters that enable SQL injection in DuckDB / standard SQL
_INJECTION_CHARS = re.compile(r"[;'\")\-\-]|(/\*)|(\*/)|(\bDROP\b)|(\bDELETE\b)|(\bINSERT\b)|(\bUPDATE\b)", re.IGNORECASE)

# Reasonable symbol whitelist: uppercase letters, digits, underscore, dot, slash
_SYMBOL_RE = re.compile(r"^[A-Z0-9_.\/]+$")

# Reasonable table-name whitelist
_TABLE_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _is_safe_table_name(name: str) -> bool:
    """Return True if *name* is a safe DuckDB table identifier."""
    if not name or len(name) > 128:
        return False
    if _INJECTION_CHARS.search(name):
        return False
    return bool(_TABLE_RE.match(name))


def _is_safe_symbol(name: str) -> bool:
    """Return True if *name* is a safe trading symbol."""
    if not name or len(name) > 20:
        return False
    return bool(_SYMBOL_RE.match(name))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNormalBootstrapPasses:
    """Legitimate table/symbol names must pass validation."""

    def test_normal_table_names(self):
        for name in ["ohlcv", "signals", "orders", "trades", "features"]:
            assert _is_safe_table_name(name), f"'{name}' should be safe"

    def test_normal_symbols(self):
        for sym in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"]:
            assert _is_safe_symbol(sym), f"'{sym}' should be safe"


class TestMaliciousTableNameRejected:
    """SQL-injection payloads disguised as table names must be rejected."""

    @pytest.mark.parametrize("name", [
        "ohlcv; DROP TABLE ohlcv--",
        "ohlcv') OR 1=1--",
        "ohlcv/*comment*/",
        "'; DELETE FROM signals; --",
        "ohlcv; INSERT INTO signals VALUES(1)",
        "table_name_with_'quote",
        "",
        "a" * 200,  # excessively long
    ])
    def test_malicious_table_name_rejected(self, name: str):
        assert _is_safe_table_name(name) is False, f"'{name}' must be rejected"


class TestMaliciousSymbolRejected:
    """SQL-injection payloads disguised as trading symbols must be rejected."""

    @pytest.mark.parametrize("symbol", [
        "XAUUSD; DROP TABLE ohlcv--",
        "EURUSD' OR '1'='1",
        "'; DELETE FROM trades; --",
        "BTCUSD/*bypass*/",
        "USDJPY; UPDATE accounts SET balance=0",
        "symbol with spaces",
        "symbol-with-dashes",
        "",
    ])
    def test_malicious_symbol_rejected(self, symbol: str):
        assert _is_safe_symbol(symbol) is False, f"'{symbol}' must be rejected"
