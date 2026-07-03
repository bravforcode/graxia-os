"""Tests for ledger integrity (Phase 3.1A)."""
import sys
import os

# Ensure quant_os is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from execution.ledger_integrity import IntegrityChain, LedgerRecord


def _make_record(**overrides) -> LedgerRecord:
    """Factory for test records."""
    defaults = {
        "trade_id": "T001",
        "order_id": "O001",
        "symbol": "BTC-USD",
        "side": "BUY",
        "entry_price": "50000.00",
        "exit_price": "51000.00",
        "volume": "0.1",
        "pnl": "100.00",
        "fees": "5.00",
        "spread_cost": "2.00",
        "slippage_cost": "1.00",
        "entry_time": "2025-01-01T00:00:00",
        "exit_time": "2025-01-01T01:00:00",
        "close_reason": "signal",
        "strategy_id": "momentum_v1",
        "contract_snapshot_id": "snap_001",
        "risk_policy_version": "v1.0",
        "dataset_manifest_id": "ds_001",
        "cost_scenario": "normal",
        "git_commit": "abc1234",
    }
    defaults.update(overrides)
    return LedgerRecord(**defaults)


def test_chain_verify_clean():
    chain = IntegrityChain()
    for i in range(5):
        chain.append(_make_record(trade_id=f"T{i:03d}"))
    valid, errors = chain.verify()
    assert valid, errors
    assert errors == []


def test_tamper_value_detection():
    chain = IntegrityChain()
    for i in range(3):
        chain.append(_make_record(trade_id=f"T{i:03d}"))
    chain.detect_tamper(1, "pnl", "99999.00")
    valid, errors = chain.verify()
    assert not valid
    assert len(errors) > 0


def test_tamper_reorder_detection():
    chain = IntegrityChain()
    r1 = _make_record(trade_id="T001")
    r2 = _make_record(trade_id="T002")
    chain.append(r1)
    chain.append(r2)
    # Swap records
    chain._records[0], chain._records[1] = chain._records[1], chain._records[0]
    valid, errors = chain.verify()
    assert not valid
    assert len(errors) > 0


def test_tamper_delete_detection():
    chain = IntegrityChain()
    for i in range(3):
        chain.append(_make_record(trade_id=f"T{i:03d}"))
    chain._records.pop(1)
    valid, errors = chain.verify()
    assert not valid
    assert len(errors) > 0


def test_tamper_cost_field_detection():
    chain = IntegrityChain()
    chain.append(_make_record())
    chain.detect_tamper(0, "spread_cost", "9999.00")
    valid, errors = chain.verify()
    assert not valid


def test_tamper_provenance_detection():
    chain = IntegrityChain()
    chain.append(_make_record())
    chain.detect_tamper(0, "strategy_id", "malicious_strategy")
    valid, errors = chain.verify()
    assert not valid


def test_run_seal_deterministic():
    def build_seal():
        c = IntegrityChain()
        for i in range(3):
            c.append(_make_record(trade_id=f"T{i:03d}"))
        return c.compute_run_seal("manifest_hash_abc")

    assert build_seal() == build_seal()


def test_run_seal_changes_on_tamper():
    chain = IntegrityChain()
    for i in range(3):
        chain.append(_make_record(trade_id=f"T{i:03d}"))
    seal_before = chain.compute_run_seal("manifest_hash_abc")
    chain.detect_tamper(1, "pnl", "0.00")
    seal_after = chain.compute_run_seal("manifest_hash_abc")
    assert seal_before != seal_after


def test_export_jsonl():
    chain = IntegrityChain()
    for i in range(3):
        chain.append(_make_record(trade_id=f"T{i:03d}"))
    lines = chain.export_jsonl().strip().split("\n")
    assert len(lines) == 3
    import json
    for line in lines:
        obj = json.loads(line)
        assert "record_hash" in obj
        assert "trade_id" in obj


def test_empty_chain():
    chain = IntegrityChain()
    valid, errors = chain.verify()
    assert valid
    assert errors == []
