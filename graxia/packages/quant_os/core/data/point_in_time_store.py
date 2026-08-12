"""Point-in-time feature store — append-only, never overwrite.

Each row records a value alongside two timestamps:
  - value_date: the date the value describes (e.g. COT Tuesday close)
  - published_at: the timestamp the value actually became knowable

This lets any historical query_time reconstruct 'what was known as of timestamp T'
honestly, avoiding subtle lookahead leakage from publication lag.
"""
import pandas as pd
from pathlib import Path


def store_point_in_time(
    series_name: str,
    value_date: pd.Timestamp,
    published_at: pd.Timestamp,
    value: float,
) -> dict:
    return {
        "series": series_name,
        "value_date": pd.Timestamp(value_date),
        "published_at": pd.Timestamp(published_at),
        "published_lag": pd.Timestamp(published_at) - pd.Timestamp(value_date),
        "value": float(value),
    }


def as_of(df: pd.DataFrame, query_time: pd.Timestamp) -> pd.DataFrame:
    visible = df[df["published_at"] <= query_time]
    if visible.empty:
        return visible
    return visible.sort_values("published_at").groupby("series").tail(1)


COLS = ["series", "value_date", "published_at", "published_lag", "value"]


class PointInTimeStore:
    def __init__(self) -> None:
        self._df = pd.DataFrame(columns=COLS)
        self._df["value_date"] = pd.to_datetime(self._df["value_date"])
        self._df["published_at"] = pd.to_datetime(self._df["published_at"])

    def append(
        self,
        series_name: str,
        value_date: pd.Timestamp,
        published_at: pd.Timestamp,
        value: float,
    ) -> None:
        row = store_point_in_time(series_name, value_date, published_at, value)
        new_row = pd.DataFrame([row])
        self._df = pd.concat([self._df, new_row], ignore_index=True)

    def to_dataframe(self) -> pd.DataFrame:
        return self._df.sort_values("published_at").reset_index(drop=True)

    def save(self, path: str) -> None:
        self.to_dataframe().to_parquet(path, index=False)

    def load(self, path: str) -> None:
        if not Path(path).exists():
            raise FileNotFoundError(f"PIT store file not found: {path}")
        self._df = pd.read_parquet(path)

    def get_as_of(self, query_time: pd.Timestamp) -> pd.DataFrame:
        return as_of(self._df, query_time)

    def get_latest(self) -> pd.DataFrame:
        return self._df.sort_values("published_at").groupby("series").tail(1)
