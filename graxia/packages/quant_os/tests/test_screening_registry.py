# tests/test_screening_registry.py
import json

from research.screening_registry import config_hash, load_configs, register_config

PARAMS = {"lookback": 20, "entry": "close_cross"}


def test_config_hash_deterministic():
    a = config_hash("donchian", "BTCUSD", "H1", PARAMS, ("2018-01-01", "2026-07-01"))
    b = config_hash("donchian", "BTCUSD", "H1", PARAMS, ("2018-01-01", "2026-07-01"))
    assert a == b


def test_config_hash_differs_on_data_range():
    a = config_hash("donchian", "BTCUSD", "H1", PARAMS, ("2018-01-01", "2026-07-01"))
    b = config_hash("donchian", "BTCUSD", "H1", PARAMS, ("2019-01-01", "2026-07-01"))
    assert a != b  # A6: data_range change = distinct config


def test_register_config_dedups_by_hash(tmp_path):
    log = tmp_path / "screening_log_i.json"
    log.write_text(json.dumps({"schema_version": "1.0", "direction": "I", "configs": [], "count": 0}), encoding="utf-8")
    e1 = register_config(
        str(log),
        mechanism="donchian",
        symbol="BTCUSD",
        timeframe="H1",
        params=PARAMS,
        data_range=("2018-01-01", "2026-07-01"),
    )
    e2 = register_config(
        str(log),
        mechanism="donchian",
        symbol="BTCUSD",
        timeframe="H1",
        params=PARAMS,
        data_range=("2018-01-01", "2026-07-01"),
    )
    data = json.loads(log.read_text(encoding="utf-8"))
    assert e1["config_id"] == e2["config_id"]
    assert data["count"] == 1  # duplicate hash NOT double-counted


def test_register_config_counts_distinct(tmp_path):
    log = tmp_path / "screening_log_i.json"
    log.write_text(json.dumps({"schema_version": "1.0", "direction": "I", "configs": [], "count": 0}), encoding="utf-8")
    register_config(
        str(log),
        mechanism="donchian",
        symbol="BTCUSD",
        timeframe="H1",
        params=PARAMS,
        data_range=("2018-01-01", "2026-07-01"),
    )
    register_config(
        str(log),
        mechanism="rsi_mr",
        symbol="EURUSD",
        timeframe="M15",
        params={"period": 14},
        data_range=("2015-01-01", "2026-07-01"),
    )
    data = json.loads(log.read_text(encoding="utf-8"))
    assert data["count"] == 2
    assert len(load_configs(str(log))) == 2
