import pandera as pa
from pandera import Check, Column, DataFrameSchema
import pandas as pd

XAUUSD_M15_SCHEMA = DataFrameSchema(
    columns={
        "open": Column(float, [Check.greater_than(500), Check.less_than(10000)]),
        "high": Column(float, [Check.greater_than(500), Check.less_than(10000)]),
        "low": Column(float, [Check.greater_than(500), Check.less_than(10000)]),
        "close": Column(float, [Check.greater_than(500), Check.less_than(10000)]),
        "volume": Column(float, Check.greater_than_or_equal_to(0)),
        "avg_spread": Column(float, [Check.greater_than_or_equal_to(0), Check.less_than(5.0)], nullable=True),
    },
    checks=[
        Check(lambda df: (df["high"] >= df["low"]).all(), error="high < low detected"),
        Check(lambda df: (df["high"] >= df["open"]).all(), error="high < open detected"),
        Check(lambda df: (df["high"] >= df["close"]).all(), error="high < close detected"),
        Check(lambda df: (df["low"] <= df["open"]).all(), error="low > open detected"),
        Check(lambda df: (df["low"] <= df["close"]).all(), error="low > close detected"),
        Check(
            lambda df: (df["close"].pct_change().iloc[1:].abs() < 0.05).all(),
            error="Price jump >5% detected - check data integrity",
        ),
    ],
    index=pa.Index(pa.DateTime, name="timestamp"),
    coerce=True,
)


def validate_ohlcv(df: pd.DataFrame, source: str = "unknown") -> pd.DataFrame:
    try:
        validated = XAUUSD_M15_SCHEMA.validate(df)
        print(f"\u2705 OHLCV validation passed: {len(validated):,} bars from {source}")
        return validated
    except pa.errors.SchemaError as e:
        print(f"\u274c Schema validation FAILED [{source}]: {e}")
        raise
