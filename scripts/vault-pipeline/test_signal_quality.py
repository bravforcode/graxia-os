"""Test signal quality pipeline with synthetic sample data"""

from signal_quality import (
    classify_trade,
    calculate_accuracy_metrics,
    generate_vault_note,
)
from signals_to_vault import (
    classify as sv_classify,
    compute_classification_metrics,
    compute_confidence_bands,
)


def make_trade(direction, entry, exit_p, conf, strategy="mtm"):
    """Build a CSV row dict simulating a trade"""
    pnl = 0.0
    if exit_p and entry:
        if direction == "long":
            pnl = (exit_p - entry) * 0.01
        else:
            pnl = (entry - exit_p) * 0.01
    return {
        "timestamp": "2026-06-25 10:00:00",
        "direction": direction,
        "entry_price": str(entry),
        "exit_price": str(exit_p) if exit_p else "",
        "exit_reason": "take_profit" if pnl > 0 else "stop_loss" if pnl < 0 else "",
        "stop_filled_at": "",
        "intended_stop": "",
        "slippage": "0.0",
        "pnl_gross": str(pnl) if exit_p else "",
        "pnl_net": str(pnl) if exit_p else "",
        "event_flag": "",
        "notes": f"Open conf={conf:.2f} strategy={strategy} ticket=12345",
    }


def test_classification():
    """Test trade classification logic"""
    row = make_trade("long", 4060.0, 4065.0, 0.88)
    t = classify_trade(row)
    assert t["direction"] == "long"
    assert t["confidence"] == 0.88
    assert t["outcome"] == "win"

    row = make_trade("short", 4070.0, 4075.0, 0.72)
    t = classify_trade(row)
    assert t["direction"] == "short"
    assert t["outcome"] == "loss"

    row = make_trade("long", 4060.0, None, 0.91)
    t = classify_trade(row)
    assert t["outcome"] == "pending"
    print("PASS: classification")


def test_accuracy_metrics():
    """Test accuracy calculation"""
    trades = [
        classify_trade(make_trade("long", 100, 105, 0.9, "mtm")),  # long 100→105 = win
        classify_trade(make_trade("short", 100, 95, 0.8, "mrb")),  # short 100→95 = win
        classify_trade(make_trade("long", 100, 95, 0.7, "mtm")),  # long 100→95 = loss
        classify_trade(
            make_trade("short", 100, 105, 0.6, "mlb")
        ),  # short 100→105 = loss
    ]
    m = calculate_accuracy_metrics(trades)
    assert m["total"] == 4
    assert m["wins"] == 2
    assert m["losses"] == 2
    assert m["accuracy"] == 0.5
    print("PASS: accuracy metrics")


def test_strategy_metrics():
    """Test per-strategy precision/recall/F1"""
    trades = [
        sv_classify(make_trade("long", 100, 105, 0.9, "mtm")),  # win
        sv_classify(make_trade("long", 100, 95, 0.85, "mtm")),  # loss
        sv_classify(make_trade("short", 100, 95, 0.7, "mrb")),  # win
        sv_classify(make_trade("long", 100, 102, 0.6, "mrb")),  # win
    ]
    sm = compute_classification_metrics(trades)
    assert "mtm" in sm
    assert sm["mtm"]["total_signals"] == 2
    assert sm["mtm"]["wins"] == 1
    assert sm["mtm"]["precision"] == 0.5
    assert sm["mrb"]["total_signals"] == 2
    assert sm["mrb"]["wins"] == 2
    assert sm["mrb"]["precision"] == 1.0
    print("PASS: strategy metrics")


def test_confidence_bands():
    """Test confidence band analysis"""
    trades = [
        sv_classify(make_trade("long", 100, 105, 0.95, "mtm")),
        sv_classify(make_trade("long", 100, 105, 0.92, "mtm")),
        sv_classify(make_trade("long", 100, 95, 0.85, "mtm")),
        sv_classify(make_trade("long", 100, 95, 0.55, "mrb")),
    ]
    bands = compute_confidence_bands(trades)
    high = [b for b in bands if "0.90" in b["band"]][0]
    assert high["count"] == 2
    assert high["precision"] == 1.0
    med = [b for b in bands if "0.80" in b["band"]][0]
    assert med["count"] == 1
    assert med["precision"] == 0.0
    print("PASS: confidence bands")


def test_vault_note_generation():
    """Test full vault note output"""
    trades = [
        classify_trade(make_trade("long", 4060, 4065, 0.88, "mtm")),
        classify_trade(make_trade("short", 4070, 4075, 0.72, "mrb")),
        classify_trade(make_trade("long", 4060, 4055, 0.91, "mtm")),
        classify_trade(make_trade("short", 4070, 4065, 0.65, "mlb")),
    ]
    md = generate_vault_note("2026-06-25", trades, {"config": "B2", "symbol": "XAUUSD"})
    assert "type: signal-quality" in md
    assert "date: 2026-06-25" in md
    assert "overall_accuracy" in md
    assert "Precision / Recall" not in md  # That's in the other script
    assert "## Trade Log" in md
    assert "Signal Quality Report" in md
    print("PASS: vault note generation")


if __name__ == "__main__":
    test_classification()
    test_accuracy_metrics()
    test_strategy_metrics()
    test_confidence_bands()
    test_vault_note_generation()
    print("\nAll tests passed.")
