"""
Feature Store — Caching and reuse of computed features for ML pipeline.

Features are stored as Parquet files partitioned by symbol/timeframe/date,
with TTL-based cache invalidation and summary statistics.
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

        # Write parquet — preserve DatetimeIndex
        df = pd.DataFrame(data)
        if isinstance(df.index, pd.DatetimeIndex):
            df.to_parquet(file_path, index=True, engine="pyarrow")
        else:
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

        # Restore DatetimeIndex if first column is datetime (written with index=True)
        if not isinstance(df.index, pd.DatetimeIndex):
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    df.set_index(col, inplace=True)
                    df.index.name = None
                    break

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
