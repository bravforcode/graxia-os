#!/usr/bin/env python3
"""Alternative Data Ingestion Pipeline.

Ingests economic calendar events, news sentiment, market regime labels,
and session indicators into the Quant OS data warehouse.

Usage:
    python scripts/ingest_alternative.py --type economic_calendar --start 2024-01-01 --end 2024-12-31
    python scripts/ingest_alternative.py --type news_sentiment --input news.csv
    python scripts/ingest_alternative.py --type regimes --input data/warehouse/ohlcv/EURUSD/M15/data.parquet
    python scripts/ingest_alternative.py --type sessions --start 2024-01-01 --end 2024-12-31
    python scripts/ingest_alternative.py --type all --start 2024-01-01 --end 2024-12-31 --symbols EURUSD,GBPUSD,XAUUSD
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import date as Date, datetime, timedelta, UTC
from typing import Any, ClassVar, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests
from bs4 import BeautifulSoup


# ── Constants ──

FOREX_FACTORY_URL = "https://www.forexfactory.com/calendar"
OUTPUT_BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "warehouse", "alternative",
)

IMPACT_LABELS = {"3": "high", "2": "medium", "1": "low", "0": "none"}

SESSION_RANGES = [
    ("asian", timedelta(hours=0), timedelta(hours=9)),
    ("european", timedelta(hours=8), timedelta(hours=17)),
    ("us", timedelta(hours=13), timedelta(hours=22)),
]

# ── Data Models ──

@dataclass
class EconomicEvent:
    date: str
    time: str
    currency: str
    event_name: str
    impact: str
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_table(self) -> pa.Table:
        data = self.to_dict()
        timestamp = self._parse_timestamp()
        return pa.table({
            "timestamp": pa.array([timestamp], type=pa.timestamp("s", tz="UTC")),
            "currency": pa.array([self.currency]),
            "event_name": pa.array([self.event_name]),
            "impact": pa.array([self.impact]),
            "actual": pa.array([self._parse_float(self.actual)]),
            "forecast": pa.array([self._parse_float(self.forecast)]),
            "previous": pa.array([self._parse_float(self.previous)]),
        })

    def _parse_timestamp(self) -> datetime:
        if self.time and self.time != "All Day":
            hour, minute = self.time.replace("am", "").replace("pm", "").strip().split(":")
            h = int(hour) + (12 if "pm" in self.time.lower() and int(hour) != 12 else 0)
            h = h - 12 if "am" in self.time.lower() and int(hour) == 12 else h
            m = int(minute)
        else:
            h, m = 0, 0
        dt = datetime.strptime(self.date, "%Y-%m-%d").replace(hour=h, minute=m, tzinfo=UTC)
        return dt

    @staticmethod
    def _parse_float(val: Optional[str]) -> Optional[float]:
        if val is None or val in ("", "-"):
            return None
        cleaned = val.replace("%", "").replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def table_schema() -> pa.Schema:
        return pa.schema([
            ("timestamp", pa.timestamp("s", tz="UTC")),
            ("currency", pa.string()),
            ("event_name", pa.string()),
            ("impact", pa.string()),
            ("actual", pa.float64()),
            ("forecast", pa.float64()),
            ("previous", pa.float64()),
        ])


@dataclass
class NewsSentimentRecord:
    timestamp: datetime
    source: str
    headline: str
    sentiment_score: float
    relevance: list[str] = field(default_factory=list)

    @staticmethod
    def table_schema() -> pa.Schema:
        return pa.schema([
            ("timestamp", pa.timestamp("s", tz="UTC")),
            ("source", pa.string()),
            ("headline", pa.string()),
            ("sentiment_score", pa.float64()),
            ("relevance", pa.list_(pa.string())),
        ])


@dataclass
class RegimeLabel:
    timestamp: datetime
    symbol: str
    volatility_regime: str
    trend_regime: str
    liquidity_regime: str

    @staticmethod
    def table_schema() -> pa.Schema:
        return pa.schema([
            ("timestamp", pa.timestamp("s", tz="UTC")),
            ("symbol", pa.string()),
            ("volatility_regime", pa.string()),
            ("trend_regime", pa.string()),
            ("liquidity_regime", pa.string()),
        ])


@dataclass
class SessionIndicator:
    timestamp: datetime
    session: str
    is_weekend: bool
    is_holiday: bool

    @staticmethod
    def table_schema() -> pa.Schema:
        return pa.schema([
            ("timestamp", pa.timestamp("s", tz="UTC")),
            ("session", pa.string()),
            ("is_weekend", pa.bool_()),
            ("is_holiday", pa.bool_()),
        ])


# ── Abstract Ingestion Source ──

class IngestionSource(ABC):
    """Base class for all alternative data ingestion sources."""

    @abstractmethod
    def ingest(self, **kwargs) -> list[pa.Table]:
        """Fetch, parse, and return PyArrow tables."""

    @abstractmethod
    def output_path(self) -> str:
        """Return the relative output subdirectory for this source."""

    def write(self, tables: list[pa.Table], base_dir: str) -> list[str]:
        """Write tables to a single Parquet file and return written paths."""
        out_dir = os.path.join(base_dir, self.output_path())
        os.makedirs(out_dir, exist_ok=True)
        non_empty = [t for t in tables if t.num_rows > 0]
        if not non_empty:
            return []
        combined = pa.concat_tables(non_empty) if len(non_empty) > 1 else non_empty[0]
        path = os.path.join(out_dir, "data.parquet")
        pq.write_table(combined, path, version="2.6")
        return [path]

    def write_run_record(self, base_dir: str, params: dict[str, Any]):
        """Save a JSON run record for audit."""
        out_dir = os.path.join(base_dir, self.output_path())
        os.makedirs(out_dir, exist_ok=True)
        record = {
            "source": self.__class__.__name__,
            "run_time_utc": datetime.now(UTC).isoformat(),
            **params,
        }
        path = os.path.join(out_dir, "run_record.json")
        with open(path, "w") as f:
            json.dump(record, f, indent=2)


# ── 1. Economic Calendar (Forex Factory) ──

class ForexFactoryCalendar(IngestionSource):
    """Ingest economic calendar events from Forex Factory HTML."""

    FF_HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    def __init__(self, start: Date, end: Date):
        self.start = start
        self.end = end

    def output_path(self) -> str:
        return "economic_calendar"

    def ingest(self, **kwargs) -> list[pa.Table]:
        events = []
        cur = self.start
        while cur <= self.end:
            chunk = self._fetch_day(cur)
            events.extend(chunk)
            cur += timedelta(days=1)
        if not events:
            print("  [WARN] No calendar events fetched")
            return [pa.table({c: pa.array([], type=t) for c, t in zip(
                EconomicEvent.table_schema().names,
                [f.type for f in EconomicEvent.table_schema()],
            )})]
        return [self._events_to_table(events)]

    def _fetch_day(self, dt: Date) -> list[EconomicEvent]:
        """Fetch and parse a single day's calendar page."""
        url = f"{FOREX_FACTORY_URL}?day={dt.month:02d}{dt.day:02d}.{dt.year}"
        try:
            resp = requests.get(url, headers=self.FF_HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [WARN] Failed to fetch {dt.isoformat()}: {e}")
            return []
        return self._parse_html(resp.text, dt)

    def _parse_html(self, html: str, default_date: Date) -> list[EconomicEvent]:
        """Parse Forex Factory calendar HTML into structured events."""
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("tr.calendar__row")
        events = []
        current_date = default_date.isoformat()

        for row in rows:
            if "calendar__row--day" in row.get("class", []):
                date_cell = row.select_one("td.calendar__cell--day")
                if date_cell:
                    parsed = self._parse_date_cell(date_cell.get_text(strip=True))
                    if parsed:
                        current_date = parsed
                continue

            if "calendar__row--event" not in row.get("class", []) and "calendar__row" not in row.get("class", []):
                continue

            cells = row.select("td")
            if len(cells) < 5:
                continue

            time_cell = row.select_one("td.calendar__cell--time")
            currency_cell = row.select_one("td.calendar__cell--currency")
            impact_cell = row.select_one("td.calendar__cell--impact")
            event_cell = row.select_one("td.calendar__cell--event")

            if not event_cell:
                continue

            event_time = time_cell.get_text(strip=True) if time_cell else ""
            currency = currency_cell.get_text(strip=True) if currency_cell else ""
            impact = self._parse_impact(impact_cell) if impact_cell else "none"
            event_name = event_cell.get_text(strip=True)

            actual, forecast, previous = None, None, None
            actual_cell = row.select_one("td.calendar__cell--actual")
            forecast_cell = row.select_one("td.calendar__cell--forecast")
            previous_cell = row.select_one("td.calendar__cell--previous")
            if actual_cell:
                actual = actual_cell.get_text(strip=True) or None
            if forecast_cell:
                forecast = forecast_cell.get_text(strip=True) or None
            if previous_cell:
                previous = previous_cell.get_text(strip=True) or None

            events.append(EconomicEvent(
                date=current_date,
                time=event_time,
                currency=currency,
                event_name=event_name,
                impact=impact,
                actual=actual,
                forecast=forecast,
                previous=previous,
            ))

        return events

    @staticmethod
    def _parse_date_cell(text: str) -> Optional[str]:
        """Parse Forex Factory date header like 'Tue Jan 2' into YYYY-MM-DD."""
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        parts = text.split()
        if len(parts) < 3:
            return None
        try:
            month = months.get(parts[1].lower()[:3])
            day = int(parts[2].rstrip(","))
            year = datetime.now(UTC).year
            return f"{year:04d}-{month:02d}-{day:02d}"
        except (ValueError, KeyError, IndexError):
            return None

    @staticmethod
    def _parse_impact(cell) -> str:
        """Extract impact level from the impact cell."""
        impact_spans = cell.select("span")
        for span in impact_spans:
            cls = " ".join(span.get("class", []))
            if "impact--high" in cls:
                return "high"
            if "impact--medium" in cls:
                return "medium"
            if "impact--low" in cls:
                return "low"
        return "none"

    @staticmethod
    def _events_to_table(events: list[EconomicEvent]) -> pa.Table:
        """Convert list of EconomicEvent to PyArrow table."""
        timestamps = []
        currencies = []
        event_names = []
        impacts = []
        actuals = []
        forecasts = []
        previouses = []

        for ev in events:
            timestamps.append(ev._parse_timestamp())
            currencies.append(ev.currency)
            event_names.append(ev.event_name)
            impacts.append(ev.impact)
            actuals.append(ev._parse_float(ev.actual))
            forecasts.append(ev._parse_float(ev.forecast))
            previouses.append(ev._parse_float(ev.previous))

        return pa.table({
            "timestamp": pa.array(timestamps, type=pa.timestamp("s", tz="UTC")),
            "currency": pa.array(currencies),
            "event_name": pa.array(event_names),
            "impact": pa.array(impacts),
            "actual": pa.array(actuals, type=pa.float64()),
            "forecast": pa.array(forecasts, type=pa.float64()),
            "previous": pa.array(previouses, type=pa.float64()),
        }, schema=EconomicEvent.table_schema())


# ── 2. News Sentiment (Skeleton / Factory) ──

class NewsSentimentIngestor(IngestionSource):
    """Source-agnostic news sentiment ingestor with factory pattern.

    Supports:
      - CSV import (batch): columns [timestamp, source, headline, sentiment_score, relevance]
      - API integration via subclass (NewsSentimentIngestor.register_source)
    """

    _sources: ClassVar[dict[str, type["NewsSourceAdapter"]]] = {}

    def __init__(self, csv_path: Optional[str] = None, api_source: Optional[str] = None):
        self.csv_path = csv_path
        self.api_source = api_source

    def output_path(self) -> str:
        return "news_sentiment"

    @classmethod
    def register_source(cls, name: str, adapter: type["NewsSourceAdapter"]):
        cls._sources[name] = adapter

    def ingest(self, **kwargs) -> list[pa.Table]:
        tables = []

        if self.csv_path:
            table = self._ingest_csv(self.csv_path)
            if table and table.num_rows > 0:
                tables.append(table)

        if self.api_source and self.api_source in self._sources:
            adapter = self._sources[self.api_source]()
            table = adapter.fetch(**kwargs)
            if table and table.num_rows > 0:
                tables.append(table)

        if not tables:
            schema = NewsSentimentRecord.table_schema()
            tables.append(pa.table(
                {c: pa.array([], type=t) for c, t in zip(
                    schema.names, [f.type for f in schema],
                )},
                schema=schema,
            ))

        return tables

    @staticmethod
    def _ingest_csv(path: str) -> Optional[pa.Table]:
        """Import news sentiment from a CSV file."""
        if not os.path.exists(path):
            print(f"  [ERROR] CSV not found: {path}")
            return None
        try:
            df = pd.read_csv(path, parse_dates=["timestamp"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        except Exception as e:
            print(f"  [ERROR] Failed to read CSV {path}: {e}")
            return None

        required = {"timestamp", "source", "headline", "sentiment_score"}
        missing = required - set(df.columns)
        if missing:
            print(f"  [ERROR] CSV missing columns: {missing}")
            return None

        df["relevance"] = df.get("relevance", "").apply(
            lambda x: [s.strip() for s in str(x).split(",") if s.strip()] if pd.notna(x) else []
        )
        df["sentiment_score"] = df["sentiment_score"].clip(-1, 1)
        df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp", "headline"])

        if "relevance" in df.columns:
            relevance_arr = pa.array(
                df["relevance"].tolist(),
                type=pa.list_(pa.string()),
            )
        else:
            relevance_arr = pa.array([[] for _ in range(len(df))], type=pa.list_(pa.string()))

        return pa.table({
            "timestamp": pa.array(df["timestamp"].values, type=pa.timestamp("s", tz="UTC")),
            "source": pa.array(df["source"].values),
            "headline": pa.array(df["headline"].values),
            "sentiment_score": pa.array(df["sentiment_score"].values, type=pa.float64()),
            "relevance": relevance_arr,
        }, schema=NewsSentimentRecord.table_schema())


class NewsSourceAdapter(ABC):
    """Adapter interface for external news APIs."""

    @abstractmethod
    def fetch(self, **kwargs) -> pa.Table:
        """Fetch news from an external API and return as PyArrow table."""


# ── 3. Market Regime Labels ──

class RegimeLabelComputer(IngestionSource):
    """Compute volatility, trend, and liquidity regime labels from OHLCV data."""

    def __init__(self, input_path: str, symbols: Optional[list[str]] = None):
        self.input_path = input_path
        self.symbols = symbols

    def output_path(self) -> str:
        return "regimes"

    def ingest(self, **kwargs) -> list[pa.Table]:
        if os.path.isdir(self.input_path):
            tables = self._process_directory()
            if tables:
                return tables
        else:
            result = self._process_file(self.input_path)
            if result is not None:
                return [result]

        return [
            pa.table({c: pa.array([], type=t) for c, t in zip(
                RegimeLabel.table_schema().names,
                [f.type for f in RegimeLabel.table_schema()],
            )})
        ]

    def _process_directory(self) -> list[pa.Table]:
        """Walk a directory tree and process all parquet files."""
        tables = []
        for root, dirs, files in os.walk(self.input_path):
            for f in files:
                if f.endswith(".parquet") and not f.startswith("."):
                    path = os.path.join(root, f)
                    t = self._process_file(path)
                    if t:
                        tables.append(t)
        return tables

    def _process_file(self, path: str) -> Optional[pa.Table]:
        """Compute regime labels for a single OHLCV parquet file."""
        if not os.path.exists(path):
            print(f"  [ERROR] File not found: {path}")
            return None

        try:
            df = pd.read_parquet(path)
        except Exception as e:
            print(f"  [ERROR] Failed to read {path}: {e}")
            return None

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.set_index("timestamp")
        else:
            df.index = pd.to_datetime(df.index, utc=True)

        df = df.sort_index()
        symbol = self._infer_symbol(path, df)
        labels = self._compute_labels(df, symbol)
        table = self._labels_to_table(labels)
        print(f"  [OK] {symbol}: {len(labels)} regime labels from {os.path.basename(path)}")
        return table

    def _infer_symbol(self, path: str, df: pd.DataFrame) -> str:
        """Try to infer symbol from path or dataframe."""
        if self.symbols and len(self.symbols) == 1:
            return self.symbols[0]
        if "symbol" in df.columns:
            return df["symbol"].iloc[0]
        parts = path.replace("\\", "/").split("/")
        for p in parts:
            if p.upper() in ("EURUSD", "GBPUSD", "XAUUSD", "USDJPY", "GBPJPY", "EURJPY"):
                return p.upper()
        return "UNKNOWN"

    def _compute_labels(self, df: pd.DataFrame, symbol: str) -> list[RegimeLabel]:
        """Compute regime labels for each row."""
        has_ohlc = all(c in df.columns for c in ["close", "high", "low"])
        has_spread = "spread_mean" in df.columns

        df = df.copy()
        n = len(df)
        labels = []

        if has_ohlc:
            tr = pd.concat([
                df["high"] - df["low"],
                (df["high"] - df["close"].shift(1)).abs(),
                (df["low"] - df["close"].shift(1)).abs(),
            ], axis=1).max(axis=1)
            df["atr_14"] = tr.rolling(14).mean()
            df["sma_50"] = df["close"].rolling(50, min_periods=1).mean()
            df["sma_200"] = df["close"].rolling(200, min_periods=1).mean()

        if has_spread:
            df["spread_rolling_median"] = df["spread_mean"].rolling(14, min_periods=1).median()
            df["spread_pct"] = df["spread_mean"] / (df["spread_rolling_median"] + 1e-10)

        for i in range(n):
            ts = df.index[i]

            vol_regime = self._volatility_regime(df, i)
            trend_regime = self._trend_regime(df, i)
            liq_regime = self._liquidity_regime(df, i)

            labels.append(RegimeLabel(
                timestamp=ts,
                symbol=symbol,
                volatility_regime=vol_regime,
                trend_regime=trend_regime,
                liquidity_regime=liq_regime,
            ))

        return labels

    @staticmethod
    def _volatility_regime(df: pd.DataFrame, i: int) -> str:
        if "atr_14" not in df.columns or "close" not in df.columns:
            return "unknown"
        atr = df["atr_14"].iloc[i]
        close = df["close"].iloc[i]
        if pd.isna(atr) or pd.isna(close) or close <= 0:
            return "unknown"
        atr_pct = atr / close
        series = df["atr_14"] / df["close"]
        rolling = series.iloc[:i+1].dropna()
        if len(rolling) < 5:
            return "unknown"
        low_thresh = rolling.quantile(0.33)
        high_thresh = rolling.quantile(0.67)
        if atr_pct <= low_thresh:
            return "low"
        elif atr_pct >= high_thresh:
            return "high"
        return "medium"

    @staticmethod
    def _trend_regime(df: pd.DataFrame, i: int) -> str:
        if "sma_50" not in df.columns or "sma_200" not in df.columns:
            return "unknown"
        sma50 = df["sma_50"].iloc[i]
        sma200 = df["sma_200"].iloc[i]
        close = df["close"].iloc[i]
        if pd.isna(sma50) or pd.isna(sma200) or pd.isna(close):
            return "unknown"
        if sma50 > sma200 and close > sma50:
            return "bullish"
        elif sma50 < sma200 and close < sma50:
            return "bearish"
        return "neutral"

    @staticmethod
    def _liquidity_regime(df: pd.DataFrame, i: int) -> str:
        if "spread_pct" not in df.columns:
            return "unknown"
        sp = df["spread_pct"].iloc[i]
        if pd.isna(sp):
            return "unknown"
        series = df["spread_pct"].iloc[:i+1].dropna()
        if len(series) < 5:
            return "unknown"
        low_thresh = series.quantile(0.33)
        high_thresh = series.quantile(0.67)
        if sp <= low_thresh:
            return "high"
        elif sp >= high_thresh:
            return "low"
        return "medium"

    @staticmethod
    def _labels_to_table(labels: list[RegimeLabel]) -> pa.Table:
        schema = RegimeLabel.table_schema()
        return pa.table({
            "timestamp": pa.array([l.timestamp for l in labels], type=pa.timestamp("s", tz="UTC")),
            "symbol": pa.array([l.symbol for l in labels]),
            "volatility_regime": pa.array([l.volatility_regime for l in labels]),
            "trend_regime": pa.array([l.trend_regime for l in labels]),
            "liquidity_regime": pa.array([l.liquidity_regime for l in labels]),
        }, schema=schema)


# ── 4. Session Indicators ──

class SessionIndicatorComputer(IngestionSource):
    """Compute session indicators (Tokyo/London/NY) from timestamps."""

    WEEKEND_DAYS: ClassVar[set[int]] = {5, 6}

    def __init__(self, start: Date, end: Date, freq: str = "15min"):
        self.start = start
        self.end = end
        self.freq = freq

    def output_path(self) -> str:
        return "sessions"

    def ingest(self, **kwargs) -> list[pa.Table]:
        timestamps = pd.date_range(
            start=pd.Timestamp(self.start, tz="UTC"),
            end=pd.Timestamp(self.end, tz="UTC") + timedelta(days=1) - timedelta(seconds=1),
            freq=self.freq,
            tz="UTC",
        )
        indicators = [self._compute(t) for t in timestamps]
        return [self._indicators_to_table(indicators)]

    def _compute(self, ts: pd.Timestamp) -> SessionIndicator:
        session = self._resolve_session(ts)
        is_weekend = ts.weekday() in self.WEEKEND_DAYS
        return SessionIndicator(
            timestamp=ts.to_pydatetime(),
            session=session,
            is_weekend=is_weekend,
            is_holiday=False,
        )

    @staticmethod
    def _resolve_session(ts: pd.Timestamp) -> str:
        """Return the active session label for a UTC timestamp."""
        total_seconds = ts.hour * 3600 + ts.minute * 60 + ts.second
        active = []
        for name, start, end in SESSION_RANGES:
            s = int(start.total_seconds())
            e = int(end.total_seconds())
            if s <= total_seconds < e:
                active.append(name)
        if len(active) >= 2:
            return "overlap"
        if len(active) == 1:
            return active[0]
        return "closed"

    @staticmethod
    def _indicators_to_table(indicators: list[SessionIndicator]) -> pa.Table:
        schema = SessionIndicator.table_schema()
        return pa.table({
            "timestamp": pa.array(
                [i.timestamp for i in indicators],
                type=pa.timestamp("s", tz="UTC"),
            ),
            "session": pa.array([i.session for i in indicators]),
            "is_weekend": pa.array([i.is_weekend for i in indicators]),
            "is_holiday": pa.array([i.is_holiday for i in indicators]),
        }, schema=schema)


# ── CLI ──

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Alternative Data Ingestion Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--type", type=str, choices=["economic_calendar", "news_sentiment", "regimes", "sessions", "all"],
        default="all", help="Data source to ingest (default: all)",
    )
    parser.add_argument(
        "--output", type=str, default=OUTPUT_BASE,
        help=f"Output base directory (default: {OUTPUT_BASE})",
    )
    parser.add_argument(
        "--start", type=str, default="2024-01-01",
        help="Start date YYYY-MM-DD (default: 2024-01-01)",
    )
    parser.add_argument(
        "--end", type=str, default="2024-12-31",
        help="End date YYYY-MM-DD (default: 2024-12-31)",
    )
    parser.add_argument(
        "--symbols", type=str, default="",
        help="Comma-separated symbol list (e.g. EURUSD,GBPUSD,XAUUSD)",
    )
    parser.add_argument(
        "--input", type=str, default="",
        help="Input path for regimes (OHLCV parquet) or news_sentiment (CSV)",
    )
    parser.add_argument(
        "--db-path", type=str, default="",
        help="DuckDB database path (reserved for future use)",
    )
    parser.add_argument(
        "--session-freq", type=str, default="15min",
        help="Session indicator frequency (default: 15min, use '1h' for hourly)",
    )
    return parser.parse_args(argv)


def main():
    args = parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = []

    try:
        start = Date.fromisoformat(args.start)
        end = Date.fromisoformat(args.end)
    except ValueError as e:
        print(f"  [ERROR] Invalid date: {e}")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    print(f"{'='*60}")
    print("ALTERNATIVE DATA INGESTION PIPELINE")
    print(f"  Type: {args.type}")
    print(f"  Output: {args.output}")
    print(f"  Period: {start} -> {end}")
    if symbols:
        print(f"  Symbols: {', '.join(symbols)}")
    print(f"{'='*60}")

    completed = []
    errors = []

    if args.type in ("economic_calendar", "all"):
        print("\n--- Economic Calendar (Forex Factory) ---")
        try:
            ingestor = ForexFactoryCalendar(start, end)
            tables = ingestor.ingest()
            paths = ingestor.write(tables, args.output)
            ingestor.write_run_record(args.output, {
                "type": "economic_calendar",
                "start": args.start,
                "end": args.end,
            })
            total_rows = sum(t.num_rows for t in tables)
            print(f"  [OK] {total_rows} events -> {len(paths)} files")
            completed.append(("economic_calendar", total_rows))
        except Exception as e:
            print(f"  [ERROR] {e}")
            errors.append(("economic_calendar", str(e)))

    if args.type in ("news_sentiment", "all"):
        print("\n--- News Sentiment (skeleton) ---")
        try:
            csv_path = args.input if args.input and args.type == "news_sentiment" else ""
            ingestor = NewsSentimentIngestor(csv_path=csv_path or None)
            tables = ingestor.ingest()
            paths = ingestor.write(tables, args.output)
            ingestor.write_run_record(args.output, {
                "type": "news_sentiment",
                "csv_input": args.input or None,
            })
            total_rows = sum(t.num_rows for t in tables)
            print(f"  [OK] {total_rows} records -> {len(paths)} files")
            completed.append(("news_sentiment", total_rows))
        except Exception as e:
            print(f"  [ERROR] {e}")
            errors.append(("news_sentiment", str(e)))

    if args.type in ("regimes", "all"):
        print("\n--- Market Regime Labels ---")
        input_path = args.input
        if not input_path:
            # Auto-discover: look for OHLCV parquet in warehouse
            default_ohlcv = os.path.join(
                os.path.dirname(args.output), "ohlcv"
            )
            if os.path.exists(default_ohlcv):
                input_path = default_ohlcv

        if not input_path:
            # Try artifacts
            artifacts_ohlcv = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "artifacts", "features",
            )
            if os.path.exists(artifacts_ohlcv):
                input_path = artifacts_ohlcv

        if not input_path:
            print("  [SKIP] No input path for regime computation. Use --input.")
            errors.append(("regimes", "no input path"))
        else:
            try:
                ingestor = RegimeLabelComputer(input_path, symbols=symbols or None)
                tables = ingestor.ingest()
                paths = ingestor.write(tables, args.output)
                ingestor.write_run_record(args.output, {
                    "type": "regimes",
                    "input": input_path,
                    "symbols": symbols,
                })
                total_rows = sum(t.num_rows for t in tables)
                print(f"  [OK] {total_rows} regime labels -> {len(paths)} files")
                completed.append(("regimes", total_rows))
            except Exception as e:
                print(f"  [ERROR] {e}")
                errors.append(("regimes", str(e)))

    if args.type in ("sessions", "all"):
        print("\n--- Session Indicators ---")
        try:
            ingestor = SessionIndicatorComputer(start, end, freq=args.session_freq)
            tables = ingestor.ingest()
            paths = ingestor.write(tables, args.output)
            ingestor.write_run_record(args.output, {
                "type": "sessions",
                "start": args.start,
                "end": args.end,
                "freq": args.session_freq,
            })
            total_rows = sum(t.num_rows for t in tables)
            print(f"  [OK] {total_rows} session indicators -> {len(paths)} files")
            completed.append(("sessions", total_rows))
        except Exception as e:
            print(f"  [ERROR] {e}")
            errors.append(("sessions", str(e)))

    # Summary
    print(f"\n{'='*60}")
    print("INGESTION SUMMARY")
    for name, rows in completed:
        print(f"  [OK] {name}: {rows} rows")
    for name, err in errors:
        print(f"  [FAIL] {name}: {err}")
    if not completed and not errors:
        print("  Nothing was ingested.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
