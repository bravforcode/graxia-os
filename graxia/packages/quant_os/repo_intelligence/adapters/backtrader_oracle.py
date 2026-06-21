"""Backtrader differential oracle adapter. READ-ONLY reference only."""
# ponytail: stub — normalize_output/validate_input interface, no bt import at module level

# Canonical signal schema:
# {"signal_id", "timestamp_utc", "symbol", "side", "entry_price",
#  "stop_loss", "take_profit", "exit_price", "exit_reason",
#  "pnl_gross", "pnl_net", "engine"}


def validate_input(data_manifest: dict, strategy_params: dict) -> bool:
    """Check data format compatibility before running Backtrader.

    Raises NotImplementedError: stub only.
    """
    # ponytail: stub — real impl checks data feed format, timeframe
    raise NotImplementedError("Backtrader validate_input: stub only")


def normalize_output(raw_result: dict) -> list[dict]:
    """Convert Backtrader results to canonical signal format.

    Raises NotImplementedError: stub only.
    """
    # ponytail: stub — real impl maps bt trades/orders to canonical
    raise NotImplementedError("Backtrader normalize_output: stub only")


def get_engine_name() -> str:
    return "backtrader"
