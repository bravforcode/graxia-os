"""Phase 3B — Run oracles against frozen fixture and compare."""
# ponytail: lazy imports for oracle adapters — they live in isolated environments
from ..repo_intelligence.differential_comparator import compare_signal_ledgers
from .xauusd_liquidity_sweep_fixture import load_xauusd_m15, FROZEN_PARAMS


def run_oracle_comparison():
    """Run R5 (VectorBT) and R6 (Backtesting.py) against frozen fixture."""
    from ..repo_intelligence.adapters.vectorbt_oracle import run_oracle as vbt_run
    from ..repo_intelligence.adapters.backtesting_py_oracle import run_oracle as bt_run
    data, timestamps = load_xauusd_m15()

    contract_spec = {
        "symbol": "XAUUSD",
        "trade_contract_size": 100,
        "trade_tick_size": 0.01,
        "trade_tick_value": 1.0,
        "volume_step": 0.01,
        "volume_min": 0.01,
    }

    results = {}

    # R5: VectorBT
    vbt_result = vbt_run(
        data=data,
        timestamps=timestamps,
        strategy_params=FROZEN_PARAMS,
        contract_spec=contract_spec,
        cost_scenario="base",
    )
    results["R5_vectorbt"] = vbt_result

    # R6: Backtesting.py (needs uppercase columns)
    bt_data = {k.capitalize(): v for k, v in data.items()}
    bt_result = bt_run(
        data=bt_data,
        timestamps=timestamps,
        strategy_params=FROZEN_PARAMS,
        contract_spec=contract_spec,
        cost_scenario="base",
    )
    results["R6_backtesting_py"] = bt_result

    return results


def compare_oracles(canonical_trades, oracle_results):
    """Compare canonical output against oracle outputs."""
    comparisons = {}
    for oracle_name, oracle_result in oracle_results.items():
        oracle_trades = oracle_result.get("trades", [])
        comp = compare_signal_ledgers(
            canonical_trades=canonical_trades,
            oracle_trades=oracle_trades,
            canonical_engine="quant_os",
            oracle_engine=oracle_name,
            allow_pnl_mismatch=True,
        )
        comparisons[oracle_name] = comp
    return comparisons
