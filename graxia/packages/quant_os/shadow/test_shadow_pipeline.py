"""Tests for shadow pipeline."""
from graxia.packages.quant_os.shadow.shadow_pipeline import ShadowPipeline


def test_pipeline_creates():
    pipeline = ShadowPipeline()
    assert pipeline is not None


def test_pipeline_session():
    pipeline = ShadowPipeline()
    pipeline.start_session("test_session")
    summary = pipeline.get_summary()
    assert summary["signals_generated"] == 0
    assert summary["ledger_valid"]


def test_pipeline_processes_tick():
    pipeline = ShadowPipeline()
    pipeline.start_session("test")
    signal = pipeline.process_tick({"bid": 2350.50, "ask": 2350.80, "symbol": "XAUUSD"})
    assert signal is not None
    assert signal.symbol == "XAUUSD"
    assert len(pipeline.get_signals()) == 1
    assert len(pipeline.get_ledger()) == 1


def test_pipeline_invalid_tick():
    pipeline = ShadowPipeline()
    pipeline.start_session("test")
    signal = pipeline.process_tick({"bid": -1, "ask": 100, "symbol": "XAUUSD"})
    assert signal is None
    assert len(pipeline.get_incidents()) > 0


def test_pipeline_ledger_integrity():
    pipeline = ShadowPipeline()
    pipeline.start_session("test")
    for i in range(5):
        pipeline.process_tick({"bid": 2350 + i, "ask": 2350.3 + i, "symbol": "XAUUSD"})
    assert pipeline.verify_ledger_integrity()
    assert pipeline.seal_ledger()


def test_pipeline_no_order_send():
    """Shadow pipeline must never call order_send."""
    pipeline = ShadowPipeline()
    assert not hasattr(pipeline, 'order_send')
