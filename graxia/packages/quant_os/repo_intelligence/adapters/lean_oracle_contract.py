"""LEAN oracle contract. Interface only, no implementation."""
# ponytail: stub contract — normalize_output/validate_input interface, no LEAN import at module level

# Canonical signal schema:
# {"signal_id", "timestamp_utc", "symbol", "side", "entry_price",
#  "stop_loss", "take_profit", "exit_price", "exit_reason",
#  "pnl_gross", "pnl_net", "engine"}


def validate_input(data_manifest: dict, strategy_params: dict) -> bool:
    """Check data format compatibility before running LEAN.

    Raises NotImplementedError: stub only.
    """
    # ponytail: stub — real impl checks LEAN data feed format
    raise NotImplementedError("LEAN validate_input: stub only")


def normalize_output(raw_result: dict) -> list[dict]:
    """Convert LEAN results to canonical signal format.

    Raises NotImplementedError: stub only.
    """
    # ponytail: stub — real impl maps LEAN trades to canonical
    raise NotImplementedError("LEAN normalize_output: stub only")


def get_engine_name() -> str:
    return "lean"


# === LEAN-specific contract extensions ===

def get_lean_config_brokerages() -> list[str]:
    """Return list of LEAN brokerage configurations this adapter supports.

    Raises NotImplementedError: stub only.
    """
    raise NotImplementedError("LEAN get_lean_config_brokerages: stub only")


def get_lean_data_feed_types() -> list[str]:
    """Return list of LEAN data feed types this adapter supports.

    Raises NotImplementedError: stub only.
    """
    raise NotImplementedError("LEAN get_lean_data_feed_types: stub only")
