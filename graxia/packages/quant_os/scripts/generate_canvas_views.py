#!/usr/bin/env python3
"""Generate Obsidian Canvas files for Quant OS architecture visualization."""
import json, os, sys, io
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

VAULT = Path(os.getenv("OBSIDIAN_VAULT_PATH", r"C:\Users\menum\quant\quant bot"))


def write_canvas(name, canvas_data):
    path = VAULT / "Graph" / f"{name}.canvas"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(canvas_data, indent=2), encoding="utf-8")
    print(f"  Created: {path.name} ({len(canvas_data.get('nodes', []))} nodes, {len(canvas_data.get('edges', []))} edges)")


def make_node(id, type, x, y, w, h, **kwargs):
    n = {"id": id, "type": type, "x": x, "y": y, "width": w, "height": h}
    n.update(kwargs)
    return n


def make_file_node(id, file, x, y, w=260, h=60):
    return make_node(id, "file", x, y, w, h, file=file)


def make_text_node(id, text, x, y, w=260, h=60, color=None):
    n = make_node(id, "text", x, y, w, h, text=text)
    if color:
        n["color"] = color
    return n


def make_group(id, label, x, y, w, h, color=None):
    n = make_node(id, "group", x, y, w, h, label=label)
    if color:
        n["color"] = color
    return n


def make_edge(from_id, to_id, label="", color=None, from_side="right", to_side="left"):
    e = {"id": f"e-{from_id}-{to_id}", "fromNode": from_id, "toNode": to_id,
         "fromSide": from_side, "toSide": to_side}
    if label:
        e["label"] = label
    if color:
        e["color"] = color
    return e


def gen_architecture_canvas():
    """Architecture Overview: All 20 domain folders as nodes with relationships."""
    nodes = []
    edges = []

    # Domain nodes arranged in a grid
    domains = [
        ("arch", "01-Architecture", "01-Architecture/Quant-OS-Architecture.md", "1"),
        ("strat", "02-Strategies", "02-Strategies/Strategy.md", "2"),
        ("risk", "03-Risk", "03-Risk/RiskPolicy.md", "3"),
        ("exec", "04-Execution", "04-Execution/Order.md", "4"),
        ("data", "05-Data", "05-Data/DataPipeline.md", "5"),
        ("val", "06-Validation", "06-Validation/WalkForward.md", "6"),
        ("gov", "07-Governance", "07-Governance/ExperimentRegistry.md", "1"),
        ("mkt", "08-Markets", "08-Markets/EURUSDHypothesis.md", "2"),
        ("live", "09-Live-Readiness", "09-Live-Readiness/ShadowCampaign.md", "3"),
        ("ml", "10-ML", "10-ML/Pipeline.md", "4"),
        ("mon", "11-Monitoring", "11-Monitoring/Alerts.md", "5"),
        ("cost", "12-Cost", "12-Cost/CostModelLabeled.md", "6"),
        ("exp", "13-Expansion", "13-Expansion/ExpansionPlanner.md", "1"),
        ("reg", "14-Regime", "14-Regime/Detector.md", "2"),
        ("evt", "15-Events", "15-Events/EventSchema.md", "3"),
        ("repo", "16-Repo-Intelligence", "16-Repo-Intelligence/SupplyChain.md", "4"),
        ("shadow", "17-Shadow", "17-Shadow/ShadowCampaign.md", "5"),
        ("canary", "18-Canary", "18-Canary/DemoCanaryRunner.md", "6"),
        ("bt", "19-Backtest", "19-Backtest/Engine.md", "1"),
        ("orc", "20-Oracle", "20-Oracle/OracleAdapter.md", "2"),
    ]

    # Title node
    nodes.append(make_text_node("title", "# Quant OS Architecture\n> 20 Domain Modules", 400, -100, 300, 80, "4"))

    # Layout: 5 columns x 4 rows
    col_w = 320
    row_h = 120
    start_x = 0
    start_y = 20

    for i, (did, label, file_path, color) in enumerate(domains):
        col = i % 5
        row = i // 5
        x = start_x + col * col_w
        y = start_y + row * row_h
        nodes.append(make_file_node(did, file_path, x, y))

    # Key relationships
    edges.append(make_edge("arch", "strat", "defines", "1"))
    edges.append(make_edge("arch", "risk", "enforces", "3"))
    edges.append(make_edge("arch", "exec", "orchestrates", "5"))
    edges.append(make_edge("strat", "risk", "pre-trade check", "2"))
    edges.append(make_edge("risk", "exec", "approves order", "4"))
    edges.append(make_edge("exec", "data", "reads market", "6"))
    edges.append(make_edge("strat", "data", "reads OHLCV", "1"))
    edges.append(make_edge("val", "strat", "validates", "3"))
    edges.append(make_edge("val", "bt", "uses backtest", "5"))
    edges.append(make_edge("gov", "val", "governs", "2"))
    edges.append(make_edge("live", "shadow", "shadow tests", "4"))
    edges.append(make_edge("shadow", "canary", "canary deploy", "6"))
    edges.append(make_edge("ml", "strat", "enhances signals", "1"))
    edges.append(make_edge("reg", "risk", "regime overlay", "3"))
    edges.append(make_edge("cost", "exec", "cost model", "5"))
    edges.append(make_edge("mon", "live", "monitors", "2"))
    edges.append(make_edge("evt", "risk", "event gate", "4"))
    edges.append(make_edge("exp", "live", "expansion plan", "6"))
    edges.append(make_edge("orc", "val", "oracle compare", "1"))
    edges.append(make_edge("repo", "arch", "supply chain", "3"))

    write_canvas("Architecture-Overview", {"nodes": nodes, "edges": edges})


def gen_data_flow_canvas():
    """Data Flow: Signal → RiskCheck → Order → Fill → Position → PortfolioSnapshot."""
    nodes = []
    edges = []

    nodes.append(make_text_node("title", "# Data Flow\n> Signal to Portfolio", 300, -80, 280, 60, "4"))

    # Main flow nodes
    flow = [
        ("signal", "Signal", "05-Data/Signal.md", 0),
        ("risk_check", "RiskCheck", "05-Data/RiskCheck.md", 1),
        ("order", "Order", "04-Execution/Order.md", 2),
        ("fill", "Fill", "05-Data/Fill.md", 3),
        ("position", "Position", "05-Data/Position.md", 4),
        ("snapshot", "PortfolioSnapshot", "05-Data/PortfolioSnapshot.md", 5),
    ]

    for i, (id, label, file_path, idx) in enumerate(flow):
        x = idx * 300
        y = 50
        nodes.append(make_file_node(id, file_path, x, y, 260, 50))

    # Edges
    for i in range(len(flow) - 1):
        edges.append(make_edge(flow[i][0], flow[i+1][0], "", "1" if i % 2 == 0 else "2"))

    # Side inputs
    nodes.append(make_file_node("strategy", "02-Strategies/MTM.md", -100, -100, 220, 50))
    nodes.append(make_file_node("regime", "14-Regime/Detector.md", -100, 0, 220, 50))
    nodes.append(make_file_node("risk_policy", "03-Risk/RiskPolicy.md", 150, -100, 220, 50))
    nodes.append(make_file_node("circuit", "03-Risk/CircuitBreaker.md", 450, -100, 220, 50))
    nodes.append(make_file_node("fill_model", "04-Execution/FillModel.md", 750, -100, 220, 50))
    nodes.append(make_file_node("ledger", "04-Execution/TradeLedger.md", 1050, -100, 220, 50))
    nodes.append(make_file_node("kill", "03-Risk/KillSwitch.md", 1350, -100, 220, 50))

    edges.append(make_edge("strategy", "signal", "generates", "3", "right", "top"))
    edges.append(make_edge("regime", "signal", "filters", "5", "right", "top"))
    edges.append(make_edge("risk_policy", "risk_check", "validates", "2", "right", "top"))
    edges.append(make_edge("circuit", "risk_check", "gates", "4", "right", "top"))
    edges.append(make_edge("fill_model", "fill", "models", "6", "right", "top"))
    edges.append(make_edge("ledger", "fill", "records", "1", "right", "top"))
    edges.append(make_edge("kill", "risk_check", "emergency", "3", "right", "top"))

    # Bottom: output consumers
    nodes.append(make_file_node("bt_engine", "19-Backtest/Engine.md", 0, 200, 220, 50))
    nodes.append(make_file_node("dashboard", "01-Architecture/Dashboard.md", 300, 200, 220, 50))
    nodes.append(make_file_node("monitor", "11-Monitoring/Alerts.md", 600, 200, 220, 50))
    nodes.append(make_file_node("report", "18-Canary/DailyReport.md", 900, 200, 220, 50))

    edges.append(make_edge("snapshot", "bt_engine", "backtest", "5", "bottom", "top"))
    edges.append(make_edge("snapshot", "dashboard", "displays", "2", "bottom", "top"))
    edges.append(make_edge("snapshot", "monitor", "monitors", "4", "bottom", "top"))
    edges.append(make_edge("snapshot", "report", "reports", "6", "bottom", "top"))

    write_canvas("Data-Flow", {"nodes": nodes, "edges": edges})


def gen_strategy_flow_canvas():
    """Strategy Flow: Strategy → Signal → Ensemble → RiskGate → Order."""
    nodes = []
    edges = []

    nodes.append(make_text_node("title", "# Strategy Flow\n> Signal Generation to Order Execution", 300, -80, 320, 60, "4"))

    # Strategies
    strat_y = 30
    nodes.append(make_file_node("mtm", "02-Strategies/MTM.md", 0, strat_y, 200, 50))
    nodes.append(make_file_node("mrb", "02-Strategies/MRB.md", 250, strat_y, 200, 50))
    nodes.append(make_file_node("mlb", "02-Strategies/MLB.md", 500, strat_y, 200, 50))

    # Signal layer
    sig_y = 140
    nodes.append(make_text_node("signals", "## Signals\nBUY / SELL / NONE", 100, sig_y, 200, 60, "2"))
    nodes.append(make_text_node("ensemble", "## Ensemble\nWeighted Vote\n(mtm:0.4, mrb:0.25, mlb:0.35)", 400, sig_y, 240, 80, "3"))

    # Indicators
    ind_y = 80
    nodes.append(make_file_node("ema", "01-Architecture/Quant-OS-Architecture.md", -250, ind_y, 200, 40))
    nodes.append(make_file_node("rsi", "14-Regime/Detector.md", -250, ind_y + 60, 200, 40))
    nodes.append(make_file_node("adx", "14-Regime/Monitor.md", -250, ind_y + 120, 200, 40))

    # Gates
    gate_y = 280
    nodes.append(make_text_node("regime_gate", "## Regime Gate\nFilter by market regime", 50, gate_y, 220, 60, "5"))
    nodes.append(make_text_node("confidence", "## Confidence Gate\nmin_confidence: 0.60", 350, gate_y, 220, 60, "1"))
    nodes.append(make_text_node("rr_gate", "## R:R Gate\nmin_risk_reward: 1.5", 650, gate_y, 220, 60, "3"))

    # Risk & Order
    risk_y = 400
    nodes.append(make_file_node("risk_check", "03-Risk/PreTradeRisk.md", 100, risk_y, 220, 50))
    nodes.append(make_file_node("circuit", "03-Risk/CircuitBreaker.md", 400, risk_y, 220, 50))
    nodes.append(make_file_node("order", "04-Execution/Order.md", 700, risk_y, 220, 50))

    # Edges: strategies to signals
    edges.append(make_edge("mtm", "signals", "", "1"))
    edges.append(make_edge("mrb", "signals", "", "2"))
    edges.append(make_edge("mlb", "signals", "", "3"))
    edges.append(make_edge("signals", "ensemble", "", "4"))

    # Indicators to strategies
    edges.append(make_edge("ema", "mtm", "EMA 9/20/50/200", "5", "right", "left"))
    edges.append(make_edge("rsi", "mrb", "RSI 14", "6", "right", "left"))
    edges.append(make_edge("adx", "mlb", "ADX 14", "1", "right", "left"))

    # Ensemble to gates
    edges.append(make_edge("ensemble", "regime_gate", "", "2"))
    edges.append(make_edge("ensemble", "confidence", "", "4"))
    edges.append(make_edge("ensemble", "rr_gate", "", "6"))

    # Gates to risk
    edges.append(make_edge("regime_gate", "risk_check", "", "3"))
    edges.append(make_edge("confidence", "risk_check", "", "1"))
    edges.append(make_edge("rr_gate", "risk_check", "", "5"))

    # Risk to order
    edges.append(make_edge("risk_check", "circuit", "", "2"))
    edges.append(make_edge("circuit", "order", "approved", "4"))

    write_canvas("Strategy-Flow", {"nodes": nodes, "edges": edges})


def gen_validation_canvas():
    """Validation Pipeline: Backtest → WalkForward → DeflatedSharpe → Verdict."""
    nodes = []
    edges = []

    nodes.append(make_text_node("title", "# Validation Pipeline\n> From Hypothesis to Promotion", 300, -80, 320, 60, "4"))

    # Pipeline stages
    stages = [
        ("hypothesis", "Hypothesis\nmarkets/eurusd/hypothesis.py", 0, "2"),
        ("backtest", "Backtest\nbacktest/engine.py", 300, "3"),
        ("walkfwd", "Walk-Forward\nvalidation/walk_forward.py", 600, "5"),
        ("deflated", "Deflated Sharpe\nvalidation/deflated_sharpe.py", 900, "1"),
        ("verdict", "Phase Verdict\nvalidation/phase_5_verdict.py", 1200, "4"),
        ("review", "Promotion Review\nvalidation/promotion_review.py", 1500, "6"),
    ]

    for i, (id, label, x, color) in enumerate(stages):
        nodes.append(make_file_node(id, label.split("\n")[1], x, 50, 240, 50))
        nodes.append(make_text_node(f"{id}_label", f"## {label.split(chr(10))[0]}", x, -20, 240, 60, color))

    # Edges
    for i in range(len(stages) - 1):
        edges.append(make_edge(stages[i][0], stages[i+1][0], stages[i+1][1].split("\n")[0], "1" if i % 2 == 0 else "3"))

    # Supporting modules
    sup_y = 180
    nodes.append(make_file_node("params", "01-Architecture/Quant-OS-Architecture.md", 150, sup_y, 220, 40))
    nodes.append(make_file_node("dataset", "05-Data/DataPipeline.md", 450, sup_y, 220, 40))
    nodes.append(make_file_node("cost", "12-Cost/CostModelLabeled.md", 750, sup_y, 220, 40))
    nodes.append(make_file_node("regime", "14-Regime/Detector.md", 1050, sup_y, 220, 40))
    nodes.append(make_file_node("evidence", "06-Validation/EvidencePack.md", 1350, sup_y, 220, 40))

    edges.append(make_edge("params", "backtest", "config", "2", "top", "bottom"))
    edges.append(make_edge("dataset", "backtest", "data", "4", "top", "bottom"))
    edges.append(make_edge("cost", "walkfwd", "cost model", "6", "top", "bottom"))
    edges.append(make_edge("regime", "walkfwd", "regime filter", "1", "top", "bottom"))
    edges.append(make_edge("evidence", "review", "evidence", "3", "top", "bottom"))

    # Verdict outcomes
    out_y = 300
    nodes.append(make_text_node("pass", "PASS_TO_NEXT_PHASE", 300, out_y, 200, 40, "4"))
    nodes.append(make_text_node("cond", "CONDITIONAL_PASS", 600, out_y, 200, 40, "2"))
    nodes.append(make_text_node("nogo", "NO_GO", 900, out_y, 200, 40, "3"))
    nodes.append(make_text_node("archive", "ARCHIVE_NO_EDGE", 1200, out_y, 200, 40, "6"))

    edges.append(make_edge("verdict", "pass", "", "4", "bottom", "top"))
    edges.append(make_edge("verdict", "cond", "", "2", "bottom", "top"))
    edges.append(make_edge("verdict", "nogo", "", "3", "bottom", "top"))
    edges.append(make_edge("verdict", "archive", "", "6", "bottom", "top"))

    write_canvas("Validation-Pipeline", {"nodes": nodes, "edges": edges})


def gen_live_readiness_canvas():
    """Live Readiness: Shadow → Canary → MicroLive → LimitedLive → ControlledLive."""
    nodes = []
    edges = []

    nodes.append(make_text_node("title", "# Live Readiness Pipeline\n> From Shadow to Full Live", 300, -80, 320, 60, "4"))

    # Pipeline stages
    stages = [
        ("validated", "Validated Strategy", "06-Validation/PhaseVerdict.md", 0, "4"),
        ("shadow", "Shadow Trading", "17-Shadow/ShadowCampaign.md", 1, "5"),
        ("canary", "Canary Deployment", "18-Canary/DemoCanaryRunner.md", 2, "1"),
        ("micro", "Micro Live", "09-Live-Readiness/MicroLivePolicy.md", 3, "2"),
        ("limited", "Limited Live", "03-Risk/RiskPolicy.md", 4, "3"),
        ("controlled", "Controlled Live", "03-Risk/RiskPolicy.md", 5, "6"),
    ]

    for i, (id, label, file_path, idx, color) in enumerate(stages):
        x = idx * 300
        y = 50
        nodes.append(make_file_node(id, file_path, x, y, 250, 50))
        nodes.append(make_text_node(f"{id}_lbl", f"## {label}", x, -20, 250, 50, color))

    for i in range(len(stages) - 1):
        edges.append(make_edge(stages[i][0], stages[i+1][0], stages[i+1][1], "1" if i % 2 == 0 else "3"))

    # Supporting modules per stage
    sup_y = 180
    nodes.append(make_file_node("backtest", "19-Backtest/Engine.md", 0, sup_y, 220, 40))
    nodes.append(make_file_node("tick_src", "17-Shadow/CanonicalTickSource.md", 300, sup_y, 220, 40))
    nodes.append(make_file_node("broker_val", "18-Canary/BrokerValidator.md", 600, sup_y, 220, 40))
    nodes.append(make_file_node("preflight", "09-Live-Readiness/LivePreflight.md", 900, sup_y, 220, 40))
    nodes.append(make_file_node("reconcile", "04-Execution/TradeLedger.md", 1200, sup_y, 220, 40))
    nodes.append(make_file_node("kill", "03-Risk/KillSwitch.md", 1500, sup_y, 220, 40))

    edges.append(make_edge("backtest", "shadow", "data", "2", "top", "bottom"))
    edges.append(make_edge("tick_src", "shadow", "tick feed", "4", "top", "bottom"))
    edges.append(make_edge("broker_val", "canary", "broker check", "6", "top", "bottom"))
    edges.append(make_edge("preflight", "micro", "preflight", "1", "top", "bottom"))
    edges.append(make_edge("reconcile", "limited", "reconcile", "3", "top", "bottom"))
    edges.append(make_edge("kill", "controlled", "kill switch", "5", "top", "bottom"))

    # Risk controls
    risk_y = 300
    nodes.append(make_text_node("max_risk", "## Risk Limits\n- Micro: 0.5% per trade\n- Limited: 1.0%\n- Controlled: 2.0%", 150, risk_y, 240, 80, "3"))
    nodes.append(make_text_node("daily_loss", "## Daily Loss Limits\n- Micro: 1.5%\n- Limited: 2.0%\n- Controlled: 3.0%", 500, risk_y, 240, 80, "5"))
    nodes.append(make_text_node("position", "## Position Limits\n- Micro: $1,000\n- Limited: $5,000\n- Controlled: Unlimited", 850, risk_y, 240, 80, "1"))

    edges.append(make_edge("micro", "max_risk", "", "2", "bottom", "top"))
    edges.append(make_edge("limited", "daily_loss", "", "4", "bottom", "top"))
    edges.append(make_edge("controlled", "position", "", "6", "bottom", "top"))

    write_canvas("Live-Readiness", {"nodes": nodes, "edges": edges})


if __name__ == "__main__":
    print("[CANVAS] Generating Obsidian Canvas views...")
    gen_architecture_canvas()
    gen_data_flow_canvas()
    gen_strategy_flow_canvas()
    gen_validation_canvas()
    gen_live_readiness_canvas()
    print("[CANVAS] Done! 5 canvas files created in Graph/")
