"""Tests for shadow telemetry."""
from graxia.packages.quant_os.shadow.shadow_telemetry import ShadowTelemetry


def test_telemetry_creates():
    t = ShadowTelemetry()
    assert t is not None


def test_telemetry_records():
    t = ShadowTelemetry()
    t.start()
    t.record_signal()
    t.record_rejection("low_confidence")
    t.record_spread(0.30)
    t.record_latency(15.0)
    t.record_hypothetical_pnl(2.5)
    t.record_incident()
    m = t.get_metrics()
    assert m.signal_count == 1
    assert m.rejection_count == 1
    assert m.spread_p50 == 0.30
    assert m.decision_latency_ms == 15.0
    assert m.hypothetical_pnl == 2.5


def test_telemetry_spread_stats():
    t = ShadowTelemetry()
    for i in range(100):
        t.record_spread(0.1 + i * 0.01)
    m = t.get_metrics()
    assert m.spread_p50 > 0
    assert m.spread_p90 > m.spread_p50
