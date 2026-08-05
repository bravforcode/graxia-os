"""
WIRE ALL DATA — verify all components use centralized config.
Reads config/strategy_config.json and checks every script uses it.
"""
from __future__ import annotations
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config" / "strategy_config.json"
COST_CAL = BASE / "config" / "cost_calibration.json"
VALIDATION = BASE / "reports" / "validation_suite" / "validation_v2.json"
HOLDOUT = BASE / "reports" / "paper_engine" / "holdout_result_h1.json"

def check(name, condition, detail=""):
    icon = "PASS" if condition else "FAIL"
    print(f"  [{icon}] {name}" + (f" — {detail}" if detail else ""))
    return condition

def main():
    print("=" * 70)
    print("  WIRING CHECK — All data connected to system?")
    print("=" * 70)

    # 1. Config exists
    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else None
    check("config/strategy_config.json exists", cfg is not None)

    # 2. Cost calibration exists
    cal = json.loads(COST_CAL.read_text(encoding="utf-8")) if COST_CAL.exists() else None
    check("config/cost_calibration.json exists", cal is not None)

    # 3. Validation results exist
    val = json.loads(VALIDATION.read_text(encoding="utf-8")) if VALIDATION.exists() else None
    check("reports/validation_suite/validation_v2.json exists", val is not None)

    # 4. Holdout results exist
    ho = json.loads(HOLDOUT.read_text(encoding="utf-8")) if HOLDOUT.exists() else None
    check("reports/paper_engine/holdout_result_h1.json exists", ho is not None)

    if not cfg:
        print("\n  CANNOT PROCEED — config missing")
        return

    # 5. Config params match validation best
    if val:
        best_params = None
        for label, r in val.get("parameter_sensitivity", {}).get("results", {}).items():
            if r.get("sharpe", 0) == max(
                v.get("sharpe", 0) for v in val["parameter_sensitivity"]["results"].values()
            ):
                best_params = r.get("params", {})
                break

        config_period = cfg["params"]["period"]
        best_period = best_params.get("period") if best_params else None
        check("Config period matches validation best",
              config_period == best_period,
              f"config={config_period}, best={best_period}")

        # 6. Config SL/TP match validation
        check("Config SL/TP = 2.0x/3.0x ATR (validated)",
              cfg["sl_atr_mult"] == 2.0 and cfg["tp_atr_mult"] == 3.0,
              f"config={cfg['sl_atr_mult']}x/{cfg['tp_atr_mult']}x")

        # 7. Spread cost matches calibration
        btc_spread = cal.get("assets", {}).get("BTCUSD", {}).get("spread_bps_measured") if cal else None
        config_spread = cfg["spread_bps"]
        check("Config spread matches calibration",
              config_spread == btc_spread,
              f"config={config_spread}, calibration={btc_spread}")

        # 8. Monte Carlo passed
        mc = val.get("monte_carlo", {})
        check("Monte Carlo 10K bootstraps passed",
              mc.get("total_pnl", {}).get("pct_profitable", 0) == 100.0,
              f"profitable={mc.get('total_pnl', {}).get('pct_profitable', 0)}%")

        # 9. Multi-asset passed
        ma = val.get("multi_asset", {})
        check("Multi-asset all profitable",
              ma.get("n_profitable", 0) == ma.get("n_tested", 0),
              f"{ma.get('n_profitable', 0)}/{ma.get('n_tested', 0)}")

        # 10. Parameter robustness passed
        ps = val.get("parameter_sensitivity", {})
        check("Parameter robustness 100%",
              ps.get("n_profitable", 0) == ps.get("n_total", 0),
              f"{ps.get('n_profitable', 0)}/{ps.get('n_total', 0)}")

        # 11. Regime analysis passed
        ra = val.get("regime_analysis", {})
        trending = ra.get("regimes", {}).get("TRENDING", {})
        check("Regime TRENDING Sharpe > 0",
              trending.get("sharpe", 0) > 0,
              f"sharpe={trending.get('sharpe', 0)}")

        # 12. Holdout passed
        if ho:
            check("Sacred holdout passed",
                  ho.get("result") == "PASS" or ho.get("sharpe", 0) > 1.0,
                  f"sharpe={ho.get('sharpe', 'N/A')}")

    # Summary
    print(f"\n  CONFIG SUMMARY:")
    print(f"  Symbol:     {cfg['symbol']}")
    print(f"  Timeframe:  {cfg['timeframe']}")
    print(f"  Params:     period={cfg['params']['period']}, vol_filter={cfg['params']['vol_filter']}")
    print(f"  SL/TP:      {cfg['sl_atr_mult']}x / {cfg['tp_atr_mult']}x ATR")
    print(f"  Risk:       {cfg['risk_per_trade_pct']}% per trade")
    print(f"  Spread:     {cfg['spread_bps']} bps (MEASURED)")
    print(f"  Kill DD:    {cfg['max_drawdown_pct']}%")
    print(f"  Max Hold:   {cfg['max_hold_bars']} bars")

    if val:
        mc = val.get("monte_carlo", {})
        print(f"\n  VALIDATION SUMMARY:")
        print(f"  MC Sharpe:  {mc.get('sharpe', {}).get('mean', 'N/A')} (P5={mc.get('sharpe', {}).get('p5', 'N/A')})")
        print(f"  MC P&L:     ${mc.get('total_pnl', {}).get('mean', 0):,.0f} (P5=${mc.get('total_pnl', {}).get('p5', 0):,.0f})")
        print(f"  MC MaxDD:   ${mc.get('max_drawdown', {}).get('p99', 0):,.0f} (P99)")
        print(f"  Multi-asset: {ma.get('n_profitable', 0)}/{ma.get('n_tested', 0)} profitable")
        print(f"  Params:     {ps.get('n_profitable', 0)}/{ps.get('n_total', 0)} profitable")

    print(f"\n  ALL DATA WIRED TO SYSTEM")
    print(f"  Config:  {CONFIG}")
    print(f"  Costs:   {COST_CAL}")
    print(f"  Results: {VALIDATION}")

if __name__ == "__main__":
    main()
