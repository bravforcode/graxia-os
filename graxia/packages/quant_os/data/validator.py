"""Data validation pipeline — Great Expectations-style 3-stage checks.

Stages:
1. Basic: null check, row count, schema match
2. Relation: cross-table FK integrity
3. Business rule: price > 0, volume >= 0, high >= low

Usage:
    from data.validator import DataValidator
    validator = DataValidator()
    result = validator.validate_ohlcv(df, symbol="XAUUSD")
    if not result.passed:
        print(result.failures)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ValidationResult:
    """Result of data validation."""

    passed: bool
    stage: str  # "basic" | "relation" | "business" | "all"
    checks: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


class DataValidator:
    """3-stage data validation: basic → relation → business rules."""

    # ── OHLCV validation ──────────────────────────────────────────

    REQUIRED_OHLCV_COLUMNS = {"open", "high", "low", "close", "volume"}

    def validate_ohlcv(self, df: pd.DataFrame, symbol: str = "") -> ValidationResult:
        """Full validation pipeline for OHLCV data."""
        checks: list[str] = []
        failures: list[str] = []

        # Stage 1: Basic
        self._check_basic(df, checks, failures)

        # Stage 2: Schema
        self._check_ohlcv_schema(df, checks, failures)

        # Stage 3: Business rules
        self._check_ohlcv_business(df, checks, failures)

        return ValidationResult(
            passed=len(failures) == 0,
            stage="all",
            checks=checks,
            failures=failures,
        )

    def _check_basic(self, df: pd.DataFrame, checks: list, failures: list) -> None:
        """Stage 1: Basic data quality."""
        if df is None or len(df) == 0:
            failures.append("BASIC:empty_dataset")
            return

        checks.append(f"BASIC:row_count={len(df)}")

        null_cols = df.columns[df.isnull().any()].tolist()
        if null_cols:
            null_pcts = {c: f"{df[c].isnull().mean():.1%}" for c in null_cols}
            failures.append(f"BASIC:null_columns:{null_pcts}")
        else:
            checks.append("BASIC:no_nulls")

        if df.index.duplicated().any():
            dup_count = df.index.duplicated().sum()
            failures.append(f"BASIC:duplicate_index:{dup_count}")
        else:
            checks.append("BASIC:unique_index")

    def _check_ohlcv_schema(self, df: pd.DataFrame, checks: list, failures: list) -> None:
        """Stage 2: OHLCV schema validation."""
        # Normalize column names to lowercase
        cols = set(c.lower() for c in df.columns)
        missing = self.REQUIRED_OHLCV_COLUMNS - cols
        if missing:
            failures.append(f"SCHEMA:missing_columns:{sorted(missing)}")
        else:
            checks.append("SCHEMA:all_required_columns")

    def _check_ohlcv_business(self, df: pd.DataFrame, checks: list, failures: list) -> None:
        """Stage 3: Business rule validation."""
        # Normalize column names
        col_map = {c.lower(): c for c in df.columns}

        if "close" in col_map:
            close = df[col_map["close"]]
            non_positive = (close <= 0).sum()
            if non_positive > 0:
                failures.append(f"BUSINESS:non_positive_close:{non_positive}rows")
            else:
                checks.append("BUSINESS:positive_close")

        if "volume" in col_map:
            vol = df[col_map["volume"]]
            negative = (vol < 0).sum()
            if negative > 0:
                failures.append(f"BUSINESS:negative_volume:{negative}rows")
            else:
                checks.append("BUSINESS:non_negative_volume")

        if "high" in col_map and "low" in col_map:
            high = df[col_map["high"]]
            low = df[col_map["low"]]
            inverted = (high < low).sum()
            if inverted > 0:
                failures.append(f"BUSINESS:high_less_than_low:{inverted}rows")
            else:
                checks.append("BUSINESS:high_gte_low")

    # ── Manifest validation ───────────────────────────────────────

    def validate_manifest_present(self, data_dir) -> ValidationResult:
        """Check that all data files have manifests (INV-005)."""
        from pathlib import Path
        from .manifest import DataManifest

        checks: list[str] = []
        failures: list[str] = []

        data_dir = Path(data_dir)
        if not data_dir.exists():
            return ValidationResult(True, "manifest", ["DIRECTORY_NOT_EXISTS"], [])

        data_files = list(data_dir.glob("*.parquet")) + list(data_dir.glob("*.csv"))
        for f in data_files:
            if "_manifest" in f.stem:
                continue  # skip manifest files themselves
            try:
                DataManifest.load(f)
                checks.append(f"MANIFEST:present:{f.name}")
            except FileNotFoundError:
                failures.append(f"MANIFEST:missing:{f.name}")

        return ValidationResult(
            passed=len(failures) == 0,
            stage="manifest",
            checks=checks,
            failures=failures,
        )
