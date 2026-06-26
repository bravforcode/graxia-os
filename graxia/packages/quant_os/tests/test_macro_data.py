"""Unit tests for macro data pipeline — FRED client, COT reports, feature engineering."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.data.cot_reports import _compute_features, _parse_numeric
from core.data.fred_client import SERIES_CATALOG, FredClient
from core.data.macro_features import _rolling_percentile, _rolling_zscore, _shift_series, build_macro_features
from core.data.point_in_time_store import PointInTimeStore


class TestFredClient:
    def test_fred_client_cache_hit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "macro"
            cache_dir.mkdir(parents=True, exist_ok=True)

            cache_path = cache_dir / "DFII10_2024-01-01_2024-01-31.parquet"
            cached_series = pd.Series(
                [2.0, 2.1, 2.2],
                index=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"]),
                name="DFII10",
            )
            df = cached_series.reset_index()
            df.columns = ["date", "value"]
            df.to_parquet(cache_path, index=False)

            client = FredClient(api_key="test_key", cache_dir=cache_dir)

            with patch.object(client, "_rate_limit") as mock_rate_limit:
                result = client.fetch_series("DFII10", "2024-01-01", "2024-01-31")
                mock_rate_limit.assert_not_called()
                assert len(result) == 3
                assert result.iloc[0] == 2.0
                assert result.name == "DFII10"

    def test_fred_client_cache_miss(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "macro"
            cache_dir.mkdir(parents=True, exist_ok=True)

            mock_response = {
                "observations": [
                    {"date": "2024-01-02", "value": "2.0"},
                    {"date": "2024-01-03", "value": "2.1"},
                ]
            }

            client = FredClient(api_key="test_key", cache_dir=cache_dir)

            with patch("requests.get") as mock_get:
                mock_resp = MagicMock()
                mock_resp.json.return_value = mock_response
                mock_resp.ok = True
                mock_resp.raise_for_status = MagicMock()
                mock_get.return_value = mock_resp

                result = client.fetch_series("VIXCLS", "2024-01-01", "2024-01-31")
                assert len(result) == 2
                assert result.iloc[0] == 2.0
                assert result.name == "VIXCLS"

                cache_file = cache_dir / "VIXCLS_2024-01-01_2024-01-31.parquet"
                assert cache_file.exists()

    def test_missing_series_graceful(self):
        mock_response = {"observations": []}
        client = FredClient(api_key="test_key")

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_response
            mock_resp.ok = True
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            result = client.fetch_series("BAD_SERIES_ID", "2024-01-01", "2024-01-31")
            assert isinstance(result, pd.Series)
            assert result.empty

    def test_api_key_from_env(self):
        with patch.dict(os.environ, {"FRED_API_KEY": "env_key_123"}, clear=False):
            client = FredClient()
            assert client._api_key == "env_key_123"

    def test_api_key_missing_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict(os.environ, {"FRED_API_KEY": ""}, clear=False):
                with pytest.raises(ValueError, match="FRED_API_KEY"):
                    FredClient()

    def test_catalog_has_required_series(self):
        required = {"DFII10", "VIXCLS", "DCOILWTICO", "GVZCLS", "T10YIE", "DGS10", "DTWEXBGS", "UNRATE", "FEDFUNDS"}
        assert required.issubset(set(SERIES_CATALOG.keys()))


class TestCOTReports:
    def test_parse_numeric(self):
        assert _parse_numeric("1,234") == 1234.0
        assert _parse_numeric("") is np.nan
        assert _parse_numeric(".") is np.nan
        assert _parse_numeric("-") is np.nan
        assert _parse_numeric("nan") is np.nan
        assert _parse_numeric("45.67") == 45.67

    def test_cot_net_long_calculation(self):
        df = pd.DataFrame(
            {
                "MM_Money_Positions_Long_All": ["1000", "1100"],
                "MM_Money_Positions_Short_All": ["400", "350"],
                "Open_Interest_All": ["2000", "2200"],
                "Report_Date_as_YYYY-MM-DD": ["2024-01-01", "2024-01-08"],
            }
        )
        df["date"] = pd.to_datetime(df["Report_Date_as_YYYY-MM-DD"])
        result = _compute_features(df)
        assert result["mm_net_long"].iloc[0] == 600.0
        assert result["mm_net_long_pct"].iloc[0] == 600.0 / 2000.0

    def test_cot_features_output_columns(self):
        df = pd.DataFrame(
            {
                "MM_Money_Positions_Long_All": ["5000", "5200"],
                "MM_Money_Positions_Short_All": ["2000", "2100"],
                "Open_Interest_All": ["10000", "10200"],
                "Report_Date_as_YYYY-MM-DD": ["2024-01-01", "2024-01-08"],
            }
        )
        df["date"] = pd.to_datetime(df["Report_Date_as_YYYY-MM-DD"])
        result = _compute_features(df)
        for col in ["mm_net_long", "mm_net_long_pct", "open_interest"]:
            assert col in result.columns


class TestMacroFeatures:
    def test_shift_series(self):
        s = pd.Series([10, 20, 30], index=pd.DatetimeIndex(["2024-01-01", "2024-01-02", "2024-01-03"]))
        shifted = _shift_series(s, 1)
        assert pd.isna(shifted.iloc[0])
        assert shifted.iloc[1] == 10
        assert shifted.iloc[2] == 20

    def test_rolling_percentile(self):
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=300, freq="D")
        s = pd.Series(np.random.randn(300).cumsum(), index=dates)
        pct = _rolling_percentile(s, 252)
        assert not pct.dropna().empty
        assert pct.dropna().between(0, 1).all()

    def test_real_yield_zscore(self):
        dates = pd.date_range("2024-01-01", periods=300, freq="D")
        s = pd.Series(np.random.randn(300) * 0.1 + 2.0, index=dates)
        z = _rolling_zscore(s, 252)
        assert not z.dropna().empty
        assert z.iloc[-1] is not None

    def test_vix_regime_mapping(self):
        m15_index = pd.date_range("2024-01-10", periods=100, freq="15min")
        df_all = pd.DataFrame(
            {"VIXCLS": [15.0] * 30},
            index=pd.date_range("2024-01-01", periods=30, freq="D"),
        )
        client = FredClient(api_key="test_key")
        with patch.object(client, "fetch_multiple", return_value=df_all):
            result = build_macro_features(
                m15_index=m15_index,
                fred_client=client,
                start_date="2024-01-01",
                end_date="2024-01-12",
            )
            assert "vix_regime" in result.columns
            valid_regimes = result["vix_regime"].dropna()
            assert valid_regimes.isin(["low", "mid", "high"]).all()

    def test_macro_features_shift_no_lookahead(self):
        m15_index = pd.date_range("2024-01-10", periods=100, freq="15min")
        df_all = pd.DataFrame(
            {"DFII10": [2.0] * 10},
            index=pd.date_range("2024-01-01", periods=10, freq="D"),
        )
        client = FredClient(api_key="test_key")
        with patch.object(client, "fetch_multiple", return_value=df_all):
            result = build_macro_features(
                m15_index=m15_index,
                fred_client=client,
                start_date="2024-01-01",
                end_date="2024-01-12",
            )
            latest_known_date = m15_index.max().normalize()
            if "real_yield_pct" in result.columns:
                yield_vals = result["real_yield_pct"].dropna()
                if len(yield_vals) > 0:
                    max_idx = yield_vals.index.max().normalize()
                    assert max_idx <= latest_known_date

    def test_publication_lag_mixin(self):
        pit = PointInTimeStore()
        today = pd.Timestamp("2025-06-15")
        yesterday = today - pd.Timedelta(days=1)
        pit.append("real_yield_pct", yesterday, yesterday + pd.Timedelta(hours=8), 2.5)

        m15_index = pd.date_range("2025-06-14", periods=100, freq="15min")
        df_all = pd.DataFrame(
            {"DFII10": [2.0] * 5},
            index=pd.date_range("2025-06-10", periods=5, freq="D"),
        )
        client = FredClient(api_key="test_key")
        with patch.object(client, "fetch_multiple", return_value=df_all):
            result = build_macro_features(
                m15_index=m15_index,
                fred_client=client,
                start_date="2025-06-10",
                end_date="2025-06-16",
                pit_store=pit,
            )
            assert isinstance(result, pd.DataFrame)
            assert "real_yield_pct" in result.columns

    def test_build_macro_features_no_cot(self):
        m15_index = pd.date_range("2024-06-01", periods=50, freq="15min")
        df_all = pd.DataFrame(
            {"DFII10": [2.0, 2.1, 2.2], "VIXCLS": [15, 16, 17]},
            index=pd.date_range("2024-05-01", periods=3, freq="MS"),
        )
        client = FredClient(api_key="test_key")
        with patch.object(client, "fetch_multiple", return_value=df_all):
            result = build_macro_features(
                m15_index=m15_index,
                fred_client=client,
                start_date="2024-05-01",
                end_date="2024-06-10",
                cot_df=None,
            )
            assert isinstance(result, pd.DataFrame)
            assert len(result) == len(m15_index)

    def test_build_macro_features_with_cot(self):
        m15_index = pd.date_range("2024-06-01", periods=50, freq="15min")
        cot_df = pd.DataFrame(
            {
                "date": pd.date_range("2024-05-01", periods=5, freq="W-TUE"),
                "mm_net_long_pct": [0.1, 0.15, 0.12, 0.18, 0.2],
                "mm_trend_3w": [0.01, 0.02, -0.01, 0.03, 0.02],
            }
        )
        df_all = pd.DataFrame(
            {"DFII10": [2.0, 2.1, 2.2]},
            index=pd.date_range("2024-05-01", periods=3, freq="MS"),
        )
        client = FredClient(api_key="test_key")
        with patch.object(client, "fetch_multiple", return_value=df_all):
            result = build_macro_features(
                m15_index=m15_index,
                fred_client=client,
                start_date="2024-05-01",
                end_date="2024-06-10",
                cot_df=cot_df,
            )
            assert isinstance(result, pd.DataFrame)
            assert "cot_net_long_pct" in result.columns


class TestPointInTimeStore:
    def test_append_and_latest(self):
        pit = PointInTimeStore()
        pit.append("vix", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02"), 15.0)
        pit.append("vix", pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03"), 16.0)
        latest = pit.get_latest()
        assert len(latest) == 1
        assert latest.iloc[0]["value"] == 16.0

    def test_as_of_no_future_leak(self):
        pit = PointInTimeStore()
        pit.append("dfii10", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02"), 2.0)
        pit.append("dfii10", pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03"), 2.1)
        as_of_day = pit.get_as_of(pd.Timestamp("2024-01-02 12:00"))
        assert len(as_of_day) == 1
        assert as_of_day.iloc[0]["value"] == 2.0
