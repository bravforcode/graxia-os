"""Phase BE-P8 integration tests — shadow campaign."""
from graxia.packages.quant_os.shadow.shadow_pipeline import ShadowPipeline
from graxia.packages.quant_os.shadow.shadow_telemetry import ShadowTelemetry
from graxia.packages.quant_os.shadow.shadow_pass_criteria import ShadowPassCriteria
from graxia.packages.quant_os.shadow.shadow_campaign import ShadowCampaign, CampaignConfig


def test_pipeline_full_session():
    pipeline = ShadowPipeline()
    pipeline.start_session("test_session")
    for i in range(10):
        pipeline.process_tick({"bid": 2350 + i, "ask": 2350.3 + i, "symbol": "XAUUSD"})
    assert len(pipeline.get_signals()) == 10
    assert len(pipeline.get_ledger()) == 10
    assert pipeline.verify_ledger_integrity()
    assert pipeline.seal_ledger()
    summary = pipeline.get_summary()
    assert summary["ledger_valid"]


def test_telemetry_full():
    t = ShadowTelemetry()
    t.start()
    t.record_signal()
    t.record_spread(0.30)
    t.record_latency(15.0)
    t.record_hypothetical_pnl(2.5)
    m = t.get_metrics()
    assert m.signal_count == 1
    assert m.hypothetical_pnl == 2.5


def test_pass_criteria_all_pass():
    c = ShadowPassCriteria()
    metrics = {
        "order_count": 0, "stale_feed_count": 0, "event_bypass_count": 0,
        "has_contract_snapshot": True, "ledger_sealed": True,
        "critical_exception_count": 0, "heartbeat_count": 10,
        "unresolved_incidents": 0,
    }
    c.evaluate(metrics)
    assert c.all_passed()


def test_campaign_lifecycle():
    config = CampaignConfig(symbol="XAUUSD", strategy_id="test")
    campaign = ShadowCampaign(config)
    campaign.start()
    assert campaign.is_active()
    campaign.record_signal()
    campaign.stop()
    assert not campaign.is_active()
    assert campaign.get_summary()["signal_count"] == 1


def test_shadow_no_order_send():
    """Shadow must never call order_send."""
    pipeline = ShadowPipeline()
    pipeline.start_session("test")
    for i in range(5):
        signal = pipeline.process_tick({"bid": 2350 + i, "ask": 2350.3 + i, "symbol": "XAUUSD"})
        assert signal is not None
    assert not hasattr(pipeline, 'order_send')
