# tests/test_screening_registry.py
import json

import pytest

from research.screening_registry import (
    ScreeningLogError,
    config_hash,
    load_configs,
    register_config,
    update_config_status,
)

PARAMS = {"lookback": 20, "entry": "close_cross"}


def test_config_hash_deterministic():
    a = config_hash("donchian", "BTCUSD", "H1", PARAMS, ("2018-01-01", "2026-07-01"))
    b = config_hash("donchian", "BTCUSD", "H1", PARAMS, ("2018-01-01", "2026-07-01"))
    assert a == b


def test_config_hash_differs_on_data_range():
    a = config_hash("donchian", "BTCUSD", "H1", PARAMS, ("2018-01-01", "2026-07-01"))
    b = config_hash("donchian", "BTCUSD", "H1", PARAMS, ("2019-01-01", "2026-07-01"))
    assert a != b  # A6: data_range change = distinct config


def test_config_hash_normalizes_inputs():
    # review finding #6: case/space variants must hash identically (N consistency)
    a = config_hash("Donchian Breakout", "btcusd", "h1", PARAMS, ("2018-01-01", "2026-07-01"))
    b = config_hash("donchian_breakout", "BTCUSD", "H1", PARAMS, ("2018-01-01", "2026-07-01"))
    assert a == b


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


def test_load_configs_fails_closed_on_corrupt_log(tmp_path):
    # review finding #1: corrupt ledger must NOT be silently reset (N undercount)
    log = tmp_path / "screening_log_i.json"
    log.write_text("{broken json", encoding="utf-8")
    with pytest.raises(ScreeningLogError):
        load_configs(str(log))


def test_register_config_fails_closed_on_corrupt_log(tmp_path):
    # review finding #1: registration must not overwrite a corrupt ledger
    log = tmp_path / "screening_log_i.json"
    log.write_text("{broken json", encoding="utf-8")
    with pytest.raises(ScreeningLogError):
        register_config(
            str(log),
            mechanism="donchian",
            symbol="BTCUSD",
            timeframe="H1",
            params=PARAMS,
            data_range=("2018-01-01", "2026-07-01"),
        )
    # file untouched
    assert log.read_text(encoding="utf-8") == "{broken json"


def test_update_config_status_transitions(tmp_path):
    # review finding #2: status API for pending -> done/VOID
    log = tmp_path / "screening_log_i.json"
    log.write_text(json.dumps({"schema_version": "1.0", "direction": "I", "configs": [], "count": 0}), encoding="utf-8")
    e = register_config(
        str(log),
        mechanism="donchian",
        symbol="BTCUSD",
        timeframe="H1",
        params=PARAMS,
        data_range=("2018-01-01", "2026-07-01"),
    )
    updated = update_config_status(str(log), e["config_id"], "VOID")
    assert updated["status"] == "VOID"
    data = json.loads(log.read_text(encoding="utf-8"))
    assert data["configs"][0]["status"] == "VOID"
    assert "status_updated_at" in data["configs"][0]


def test_update_config_status_unknown_id_raises(tmp_path):
    log = tmp_path / "screening_log_i.json"
    log.write_text(json.dumps({"schema_version": "1.0", "direction": "I", "configs": [], "count": 0}), encoding="utf-8")
    with pytest.raises(KeyError):
        update_config_status(str(log), "nope", "done")
