"""
Feature Store — Caching and reuse of computed features for ML pipeline.

Features are stored as Parquet files partitioned by symbol/timeframe/date,
with TTL-based cache invalidation and summary statistics.

⚠️ CANONICAL SOURCE OF TRUTH for live inference features.
`compute_live_features()` is THE single implementation used by both the
live inference path (api/signal_service.py /api/signal endpoint) AND the
live model retrain path (signal_service._retrain_model()).

DO NOT duplicate this logic elsewhere. ml.pipeline.FeatureEngineer.generate_features()
has a SEPARATE vocabulary (~35 features, different names) and must be unified
with this function before any cross-system model deployment (see H4 in review).
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).parent / ".feature_cache"

# Canonical live-feature vocabulary (~40 features) computed by compute_live_features().
# This is the single feature-name list shared by the live inference path
# (api/signal_service.py) and the live-retrain path — both derive their feature
# columns from this function so the two can never silently diverge by construction.
LIVE_FEATURE_COLUMNS: list[str] = (
    [f"ret_{p}bar" for p in (1, 5, 10, 15, 30, 60)]
    + [f"atr_{w}" for w in (7, 14, 21)]
    + [f"rvol_{w}" for w in (10, 20, 60)]
    + [f"rsi_{p}" for p in (7, 14, 21)]
    + [
        "stoch_k",
        "stoch_d",
        "cci_20",
        "willr_14",
        "ema_5_dist",
        "ema_10_dist",
        "ema_20_dist",
        "ema_200_dist",
        "sma_20_50_cross",
        "bb_width",
        "bb_pctb",
        "bb_squeeze",
        "obv_slope_20",
        "vol_ratio_20",
        "vol_ratio_10",
        "body_ratio",
        "upper_shadow",
        "lower_shadow",
        "is_doji",
        "is_hammer",
        "is_bull_engulf",
        "is_asian_session",
        "is_london_session",
        "is_ny_session",
        "day_of_week",
        "day_of_month",
        "month",
    ]
)


def compute_feature_list_hash(feature_names: list[str]) -> str:
    """Compute a deterministic, order-sensitive hash of an ordered feature-name list.

    This is THE canonical hashing algorithm for the ``feature_list_hash`` field on
    ``ml.model_registry.ModelMetadata``. Any code that needs to verify "does this
    live feature vector match what a registered model expects" MUST call this same
    function on both sides of the comparison — a different algorithm computing
    "the same" hash defeats the purpose of the check.

    Order matters (unlike a set-based hash) because feature order determines
    column position in the X matrix fed to the model; a reordering of the same
    names would silently reshuffle a model's inputs.

    Args:
        feature_names: Ordered list of feature column names.

    Returns:
        Hex-encoded SHA-256 digest of the pipe-joined, order-preserved names.
    """
    raw = "|".join(feature_names)
    return hashlib.sha256(raw.encode()).hexdigest()


def compute_live_features(live_df: Any, feature_cols: list[str]) -> Any:
    """Compute the canonical ~40 live features on OHLCV data.

    This is the single feature-computation implementation used by BOTH the live
    inference path (api/signal_service.py's /api/signal endpoint) and the live
    model retrain path (api/signal_service.py's _retrain_model()) — previously
    these two call sites each had their own hand-maintained copy of this logic,
    which was the "three disconnected feature computations" problem this function
    resolves for the live-feature vocabulary.

    Args:
        live_df: DataFrame with open/high/low/close/volume columns and a
            DatetimeIndex (used for session/calendar features).
        feature_cols: Ordered list of feature column names to select and return.
            Any name not producible by this function is filled with 0.0 as a
            safety fallback (and a warning is logged) — this mirrors the prior
            behavior in signal_service.py so existing feature-mismatch tests
            keep passing without silently guessing an unfamiliar feature name.

    Returns:
        numpy array of shape (1, len(feature_cols)) — the most recent bar's
        feature vector, in the order of feature_cols.
    """
    import numpy as np
    import pandas as pd

    df = live_df.copy()

    # Input validation — reject NaN/inf/negative prices
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            if df[col].isna().any():
                logger.warning("feature.NaN_input", column=col)
                df[col] = df[col].fillna(method="ffill").fillna(method="bfill")
            if np.isinf(df[col]).any():
                logger.warning("feature.inf_input", column=col)
                df[col] = df[col].replace([np.inf, -np.inf], np.nan).fillna(method="ffill").fillna(method="bfill")
    # Ensure high >= low >= 0
    if "high" in df.columns and "low" in df.columns:
        df["low"] = df["low"].clip(lower=0)
        df["high"] = df["high"].clip(lower=df["low"])

    # Returns
    for p in [1, 5, 10, 15, 30, 60]:
        df[f"ret_{p}bar"] = df["close"].pct_change(p)

    # ATR
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift()).abs(),
            (df["low"] - df["close"].shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    for w in [7, 14, 21]:
        df[f"atr_{w}"] = tr.rolling(w).mean()

    # Realized Volatility
    log_ret = np.log(df["close"] / df["close"].shift(1))
    for w in [10, 20, 60]:
        df[f"rvol_{w}"] = log_ret.rolling(w).std() * np.sqrt(252 * 96)

    # RSI
    delta = df["close"].diff()
    for p in [7, 14, 21]:
        gain = delta.clip(lower=0).rolling(p).mean()
        loss = (-delta.clip(upper=0)).rolling(p).mean()
        rs = gain / loss.replace(0, np.nan)
        df[f"rsi_{p}"] = 100 - (100 / (1 + rs))

    # Stochastic
    low14 = df["low"].rolling(14).min()
    high14 = df["high"].rolling(14).max()
    df["stoch_k"] = 100 * (df["close"] - low14) / (high14 - low14).replace(0, np.nan)
    df["stoch_d"] = df["stoch_k"].rolling(3).mean()

    # CCI
    tp = (df["high"] + df["low"] + df["close"]) / 3
    df["cci_20"] = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).std())

    # Williams %R
    df["willr_14"] = -100 * (high14 - df["close"]) / (high14 - low14).replace(0, np.nan)

    # EMA distances
    for p in [5, 10, 20, 200]:
        ema = df["close"].ewm(span=p, adjust=False).mean()
        df[f"ema_{p}_dist"] = (df["close"] - ema) / ema

    # SMA cross
    sma20 = df["close"].rolling(20).mean()
    sma50 = df["close"].rolling(50).mean()
    df["sma_20_50_cross"] = (sma20 - sma50) / sma50

    # Bollinger Bands
    sma20_bb = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    upper_bb = sma20_bb + 2 * std20
    lower_bb = sma20_bb - 2 * std20
    df["bb_width"] = (upper_bb - lower_bb) / sma20_bb
    df["bb_pctb"] = (df["close"] - lower_bb) / (upper_bb - lower_bb).replace(0, np.nan)
    df["bb_squeeze"] = (df["bb_width"] < df["bb_width"].rolling(120).mean()).astype(float)

    # Volume
    if "volume" not in df.columns and "tick_volume" in df.columns:
        df["volume"] = df["tick_volume"]
    elif "volume" not in df.columns:
        df["volume"] = 0
    obv = (np.sign(df["close"].diff()) * df["volume"]).fillna(0).cumsum()

    def _safe_slope(x):
        if len(x) < 2:
            return 0.0
        try:
            slope = np.polyfit(range(len(x)), x, 1)[0]
            if np.isnan(slope) or np.isinf(slope):
                return 0.0
            return slope
        except (np.linalg.LinAlgError, ValueError):
            return 0.0

    df["obv_slope_20"] = obv.rolling(20).apply(_safe_slope, raw=True)
    vol_ma20 = df["volume"].rolling(20).mean()
    vol_ma10 = df["volume"].rolling(10).mean()
    df["vol_ratio_20"] = df["volume"] / vol_ma20.replace(0, np.nan)
    df["vol_ratio_10"] = df["volume"] / vol_ma10.replace(0, np.nan)

    # Candlestick patterns
    body = (df["close"] - df["open"]).abs()
    candle_range = (df["high"] - df["low"]).replace(0, np.nan)
    df["body_ratio"] = body / candle_range
    df["upper_shadow"] = (df["high"] - df[["open", "close"]].max(axis=1)) / candle_range
    df["lower_shadow"] = (df[["open", "close"]].min(axis=1) - df["low"]) / candle_range
    df["is_doji"] = (body / candle_range < 0.10).astype(float)
    df["is_hammer"] = ((df["lower_shadow"] > 0.6) & (body / candle_range < 0.3)).astype(float)
    prev_bearish = df["open"].shift(1) > df["close"].shift(1)
    curr_bullish = df["close"] > df["open"]
    df["is_bull_engulf"] = (
        prev_bearish & curr_bullish & (df["close"] > df["open"].shift(1)) & (df["open"] < df["close"].shift(1))
    ).astype(float)

    # Session flags (UTC) — use bar time from index
    try:
        hour = df.index.hour
    except AttributeError:
        hour = pd.DatetimeIndex(df.index).hour
    df["is_asian_session"] = ((hour >= 0) & (hour < 8)).astype(float)
    df["is_london_session"] = ((hour >= 8) & (hour < 16)).astype(float)
    df["is_ny_session"] = ((hour >= 13) & (hour < 21)).astype(float)

    # Calendar
    try:
        df["day_of_week"] = df.index.dayofweek
        df["day_of_month"] = df.index.day
        df["month"] = df.index.month
    except AttributeError:
        idx = pd.DatetimeIndex(df.index)
        df["day_of_week"] = idx.dayofweek
        df["day_of_month"] = idx.day
        df["month"] = idx.month

    # Select only model features
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        logger.warning("feature.mismatch", missing_count=len(missing), sample=missing[:5])
        for c in missing:
            df[c] = 0.0

    result = df[feature_cols].fillna(0).values
    return result[-1:]


@dataclass(frozen=True)
class FeatureMetadata:
    """Metadata about a cached feature set."""

    cache_key: str
    symbol: str
    timeframe: str
    feature_names: list[str]
    row_count: int
    date_start: str
    date_end: str
    created_at: str
    expires_at: str
    file_path: str
    file_size_bytes: int = 0


@dataclass
class FeatureStats:
    """Summary statistics for a cached feature set."""

    cache_key: str
    symbol: str
    timeframe: str
    row_count: int
    feature_count: int
    date_range: str
    age_hours: float
    is_expired: bool
    stats: dict[str, dict[str, float]] = field(default_factory=dict)


class FeatureStore:
    """
    Feature caching layer that stores computed features as Parquet files.

    Features are partitioned by symbol/timeframe/date to enable efficient
    partial loading and cache invalidation. Each cached entry has a TTL
    after which it is considered stale.

    Args:
        cache_dir: Root directory for cached feature files.
        default_ttl_hours: Default time-to-live for cached features in hours.
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        default_ttl_hours: float = 24.0,
    ) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._default_ttl = timedelta(hours=default_ttl_hours)
        self._meta_dir = self._cache_dir / "_metadata"
        self._meta_dir.mkdir(exist_ok=True)
        logger.info(
            "feature_store_initialized",
            cache_dir=str(self._cache_dir),
            default_ttl_hours=default_ttl_hours,
        )

    # -- public API -----------------------------------------------------------

    def store_features(
        self,
        data: Any,  # pandas DataFrame or dict of column arrays
        *,
        symbol: str,
        timeframe: str,
        feature_names: list[str],
        date_start: str,
        date_end: str,
        ttl_hours: float | None = None,
        tags: list[str] | None = None,
    ) -> FeatureMetadata:
        """
        Store a feature DataFrame to the cache.

        Data is written as Parquet under {cache_dir}/{symbol}/{timeframe}/.

        Args:
            data: DataFrame with feature columns and a DatetimeIndex.
            symbol: Trading symbol (e.g. "XAUUSD").
            timeframe: Bar timeframe (e.g. "M15", "H1").
            feature_names: List of feature column names.
            date_start: Start date of the data (ISO format).
            date_end: End date of the data (ISO format).
            ttl_hours: Override default TTL for this entry.
            tags: Optional tags for discovery.

        Returns:
            FeatureMetadata of the stored entry.
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas is required for FeatureStore")

        cache_key = self._build_cache_key(symbol, timeframe, date_start, date_end)
        partition_dir = self._cache_dir / symbol / timeframe
        partition_dir.mkdir(parents=True, exist_ok=True)
        file_path = partition_dir / f"{cache_key}.parquet"

        # Write parquet
        df = pd.DataFrame(data)
        df.to_parquet(file_path, index=False, engine="pyarrow")
        file_size = file_path.stat().st_size

        now = datetime.now(UTC)
        ttl = timedelta(hours=ttl_hours) if ttl_hours else self._default_ttl
        expires_at = now + ttl

        metadata = FeatureMetadata(
            cache_key=cache_key,
            symbol=symbol,
            timeframe=timeframe,
            feature_names=feature_names,
            row_count=len(df),
            date_start=date_start,
            date_end=date_end,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            file_path=str(file_path),
            file_size_bytes=file_size,
        )

        # Persist metadata sidecar
        meta_path = self._meta_dir / f"{cache_key}.json"
        with open(meta_path, "w") as f:
            json.dump(
                {
                    **{k: v for k, v in metadata.__dict__.items()},
                    "tags": tags or [],
                },
                f,
                indent=2,
            )

        logger.info(
            "features_stored",
            cache_key=cache_key,
            symbol=symbol,
            timeframe=timeframe,
            row_count=metadata.row_count,
            feature_count=len(feature_names),
            file_size_bytes=file_size,
        )
        return metadata

    def load_features(
        self,
        *,
        symbol: str,
        timeframe: str,
        date_start: str | None = None,
        date_end: str | None = None,
        force: bool = False,
    ) -> Any | None:
        """
        Load cached features from the store.

        If date_start/date_end are None, returns the most recent non-expired
        cache entry for the symbol/timeframe combination.

        Args:
            symbol: Trading symbol.
            timeframe: Bar timeframe.
            date_start: Filter by start date.
            date_end: Filter by end date.
            force: If True, return expired entries too.

        Returns:
            pandas DataFrame or None if no valid cache hit.
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas is required for FeatureStore")

        candidates = self._find_entries(symbol, timeframe)

        if date_start and date_end:
            cache_key = self._build_cache_key(symbol, timeframe, date_start, date_end)
            candidates = [c for c in candidates if c.cache_key == cache_key]

        if not candidates:
            logger.debug("cache_miss", symbol=symbol, timeframe=timeframe)
            return None

        # Sort by created_at descending, pick newest
        candidates.sort(key=lambda m: m.created_at, reverse=True)
        best = candidates[0]

        # Check TTL
        if not force and self._is_expired(best):
            logger.info("cache_expired", cache_key=best.cache_key)
            return None

        file_path = Path(best.file_path)
        if not file_path.exists():
            logger.warning("cache_file_missing", cache_key=best.cache_key)
            return None

        df = pd.read_parquet(file_path)
        logger.info(
            "cache_hit",
            cache_key=best.cache_key,
            row_count=len(df),
            feature_count=len(best.feature_names),
        )
        return df

    def get_feature_stats(
        self,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> list[FeatureStats]:
        """
        Get summary statistics for cached features.

        Args:
            symbol: Optional filter by symbol.
            timeframe: Optional filter by timeframe.

        Returns:
            List of FeatureStats for matching cache entries.
        """
        entries = self._list_all_metadata()
        if symbol:
            entries = [e for e in entries if e.symbol == symbol]
        if timeframe:
            entries = [e for e in entries if e.timeframe == timeframe]

        results: list[FeatureStats] = []
        for entry in entries:
            age = self._age_hours(entry)
            is_expired = self._is_expired(entry)
            date_range = f"{entry.date_start} → {entry.date_end}"

            # Compute per-column stats if parquet exists
            col_stats: dict[str, dict[str, float]] = {}
            file_path = Path(entry.file_path)
            if file_path.exists():
                try:
                    col_stats = self._compute_parquet_stats(file_path)
                except Exception as exc:
                    logger.warning(
                        "stats_computation_failed",
                        cache_key=entry.cache_key,
                        error=str(exc),
                    )

            results.append(
                FeatureStats(
                    cache_key=entry.cache_key,
                    symbol=entry.symbol,
                    timeframe=entry.timeframe,
                    row_count=entry.row_count,
                    feature_count=len(entry.feature_names),
                    date_range=date_range,
                    age_hours=round(age, 2),
                    is_expired=is_expired,
                    stats=col_stats,
                )
            )

        return results

    def invalidate_expired(self) -> int:
        """
        Remove all expired cache entries.

        Returns:
            Number of entries removed.
        """
        entries = self._list_all_metadata()
        removed = 0
        for entry in entries:
            if self._is_expired(entry):
                self._delete_entry(entry)
                removed += 1
        if removed > 0:
            logger.info("expired_entries_invalidated", count=removed)
        return removed

    def clear(self, symbol: str | None = None) -> int:
        """
        Clear all cached features, optionally filtered by symbol.

        Args:
            symbol: If provided, only clear entries for this symbol.

        Returns:
            Number of entries removed.
        """
        entries = self._list_all_metadata()
        if symbol:
            entries = [e for e in entries if e.symbol == symbol]
        for entry in entries:
            self._delete_entry(entry)
        logger.info("cache_cleared", count=len(entries), symbol=symbol)
        return len(entries)

    # -- private helpers ------------------------------------------------------

    def _build_cache_key(self, symbol: str, timeframe: str, date_start: str, date_end: str) -> str:
        """Build a deterministic cache key from inputs."""
        raw = f"{symbol}|{timeframe}|{date_start}|{date_end}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _find_entries(self, symbol: str, timeframe: str) -> list[FeatureMetadata]:
        """Find all cache entries for a symbol/timeframe."""
        partition_dir = self._cache_dir / symbol / timeframe
        if not partition_dir.exists():
            return []
        entries: list[FeatureMetadata] = []
        for meta_file in self._meta_dir.glob("*.json"):
            try:
                with open(meta_file) as f:
                    data = json.load(f)
                if data.get("symbol") == symbol and data.get("timeframe") == timeframe:
                    entries.append(
                        FeatureMetadata(
                            cache_key=data["cache_key"],
                            symbol=data["symbol"],
                            timeframe=data["timeframe"],
                            feature_names=data["feature_names"],
                            row_count=data["row_count"],
                            date_start=data["date_start"],
                            date_end=data["date_end"],
                            created_at=data["created_at"],
                            expires_at=data["expires_at"],
                            file_path=data["file_path"],
                            file_size_bytes=data.get("file_size_bytes", 0),
                        )
                    )
            except (json.JSONDecodeError, KeyError):
                continue
        return entries

    def _list_all_metadata(self) -> list[FeatureMetadata]:
        """List all cached feature metadata."""
        entries: list[FeatureMetadata] = []
        for meta_file in self._meta_dir.glob("*.json"):
            try:
                with open(meta_file) as f:
                    data = json.load(f)
                entries.append(
                    FeatureMetadata(
                        cache_key=data["cache_key"],
                        symbol=data["symbol"],
                        timeframe=data["timeframe"],
                        feature_names=data["feature_names"],
                        row_count=data["row_count"],
                        date_start=data["date_start"],
                        date_end=data["date_end"],
                        created_at=data["created_at"],
                        expires_at=data["expires_at"],
                        file_path=data["file_path"],
                        file_size_bytes=data.get("file_size_bytes", 0),
                    )
                )
            except (json.JSONDecodeError, KeyError):
                continue
        return entries

    def _is_expired(self, entry: FeatureMetadata) -> bool:
        """Check if a cache entry has passed its TTL."""
        try:
            expires = datetime.fromisoformat(entry.expires_at)
            return datetime.now(UTC) > expires
        except (ValueError, TypeError):
            return True

    def _age_hours(self, entry: FeatureMetadata) -> float:
        """Return age of entry in hours."""
        try:
            created = datetime.fromisoformat(entry.created_at)
            delta = datetime.now(UTC) - created
            return delta.total_seconds() / 3600.0
        except (ValueError, TypeError):
            return 0.0

    def _delete_entry(self, entry: FeatureMetadata) -> None:
        """Remove a cache entry and its metadata."""
        file_path = Path(entry.file_path)
        if file_path.exists():
            file_path.unlink()
        meta_path = self._meta_dir / f"{entry.cache_key}.json"
        if meta_path.exists():
            meta_path.unlink()

    def _compute_parquet_stats(self, file_path: Path) -> dict[str, dict[str, float]]:
        """Compute min/max/mean/std for each numeric column in a parquet file."""
        try:
            import pandas as pd
        except ImportError:
            return {}

        df = pd.read_parquet(file_path)
        stats: dict[str, dict[str, float]] = {}
        for col in df.select_dtypes(include="number").columns:
            series = df[col].dropna()
            if len(series) == 0:
                continue
            stats[col] = {
                "min": float(series.min()),
                "max": float(series.max()),
                "mean": float(series.mean()),
                "std": float(series.std()),
                "null_count": float(df[col].isna().sum()),
            }
        return stats
