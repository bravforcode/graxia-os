"""Backtrader differential oracle adapter. READ-ONLY reference only."""
# ponytail: lazy bt import, no module-level dep

import uuid

# Canonical signal schema:
# {"signal_id", "timestamp_utc", "symbol", "side", "entry_price",
#  "stop_loss", "take_profit", "exit_price", "exit_reason",
#  "pnl_gross", "pnl_net", "engine"}

_REQUIRED_OHLCV = {"open", "high", "low", "close", "volume"}
_VALID_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}


def validate_input(data_manifest: dict, strategy_params: dict) -> bool:
    """Check data format compatibility before running Backtrader.

    Returns True if valid, raises ValueError otherwise.
    """
    # ponytail: validate presence + timeframe, skip deep schema
    if not isinstance(data_manifest, dict):
        raise ValueError("data_manifest must be a dict")

    columns = data_manifest.get("columns")
    if not columns or not isinstance(columns, (list, set)):
        raise ValueError("data_manifest must have 'columns' as list/set")
    missing = _REQUIRED_OHLCV - set(columns)
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    timeframe = data_manifest.get("timeframe")
    if not timeframe:
        raise ValueError("data_manifest must specify 'timeframe'")
    if timeframe not in _VALID_TIMEFRAMES:
        raise ValueError(f"unsupported timeframe: {timeframe}")

    if not isinstance(strategy_params, dict):
        raise ValueError("strategy_params must be a dict")

    return True


def normalize_output(raw_result: dict) -> list[dict]:
    """Convert Backtrader results to canonical signal format.

    Expects raw_result to have either 'trades' (list of dicts) or
    'analyzers' output from a bt.Cerebro run.
    """
    if not isinstance(raw_result, dict):
        raise ValueError("raw_result must be a dict")

    trades = raw_result.get("trades", [])
    signals = []

    for t in trades:
        signal = {
            "signal_id": t.get("signal_id", str(uuid.uuid4())),
            "timestamp_utc": t.get("exit_timestamp", t.get("timestamp_utc", "")),
            "symbol": t.get("symbol", ""),
            "side": t.get("side", ""),
            "entry_price": float(t.get("entry_price", 0.0)),
            "stop_loss": float(t.get("stop_loss", 0.0)),
            "take_profit": float(t.get("take_profit", 0.0)),
            "exit_price": float(t.get("exit_price", 0.0)),
            "exit_reason": t.get("exit_reason", ""),
            "pnl_gross": float(t.get("pnl_gross", 0.0)),
            "pnl_net": float(t.get("pnl_net", t.get("pnl_gross", 0.0))),
            "engine": "backtrader",
        }
        signals.append(signal)

    return signals


def get_engine_name() -> str:
    return "backtrader"


def run_oracle(
    data: dict,
    timestamps: list,
    strategy_params: dict,
    contract_spec: dict,
    cost_scenario: str = "base",
) -> dict:
    """Run Backtrader oracle.

    data: dict with keys like 'open', 'high', 'low', 'close', 'volume' (each a list)
    timestamps: list of datetime-like strings/datetime objects
    strategy_params: strategy config (entry_threshold, exit_threshold, etc.)
    contract_spec: contract metadata (symbol, exchange, etc.)
    cost_scenario: cost model selector (base, aggressive, etc.)
    """
    closes = data.get("close", [])
    if not closes:
        return {"engine": "backtrader", "trades": [], "metadata": {"data_rows": 0}}

    try:
        import backtrader as bt
    except ImportError:
        return {"error": "backtrader not installed", "engine": "backtrader"}

    opens = data.get("open", closes)
    highs = data.get("high", closes)
    lows = data.get("low", closes)
    volumes = data.get("volume", [0.0] * len(closes))

    class _Feed(bt.feeds.PandasData):
        """Auto-map column indices from our OHLCV dict."""

        params = (
            ("datetime", None),
            ("open", 0),
            ("high", 1),
            ("low", 2),
            ("close", 3),
            ("volume", 4),
            ("openinterest", -1),
        )

    import pandas as pd

    df = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )
    if timestamps:
        df.index = pd.to_datetime(timestamps)

    data_feed = _Feed(dataname=df)

    cerebro = bt.Cerebro()
    cerebro.adddata(data_feed)

    initial_cash = strategy_params.get("initial_cash", 10000.0)
    cerebro.broker.setcash(initial_cash)

    # ponytail: use a trivial trend-following strategy if none specified
    strategy_cls_name = strategy_params.get("strategy_class")

    class _DefaultStrategy(bt.Strategy):
        params = (
            ("entry_threshold", strategy_params.get("entry_threshold", 0.01)),
            ("exit_threshold", strategy_params.get("exit_threshold", -0.01)),
        )

        def __init__(self):
            self.dataclose = self.datas[0].close
            self.position_entry = None
            self.side = None

        def next(self):
            if not self.position:
                if len(self.dataclose) < 2:
                    return
                pct_change = (self.dataclose[0] - self.dataclose[-1]) / self.dataclose[-1]
                if pct_change > self.p.entry_threshold:
                    self.buy()
                    self.position_entry = self.dataclose[0]
                    self.side = "long"
                elif pct_change < -self.p.entry_threshold:
                    self.sell()
                    self.position_entry = self.dataclose[0]
                    self.side = "short"
            else:
                if self.side == "long":
                    pct = (self.dataclose[0] - self.position_entry) / self.position_entry
                    if pct < self.p.exit_threshold:
                        self.close()
                elif self.side == "short":
                    pct = (self.position_entry - self.dataclose[0]) / self.position_entry
                    if pct < self.p.exit_threshold:
                        self.close()

    cerebro.addstrategy(_DefaultStrategy)

    try:
        results = cerebro.run()
    except Exception as e:
        return {"error": str(e), "engine": "backtrader", "trades": []}

    # Extract trades from strategy — ponytail: scan broker positions
    strategy_result = results[0] if results else None
    trades = []

    if strategy_result and hasattr(strategy_result, "_tradespending"):
        for t in strategy_result._tradespending:
            trades.append(
                {
                    "signal_id": str(uuid.uuid4()),
                    "timestamp_utc": "",
                    "symbol": contract_spec.get("symbol", ""),
                    "side": "long" if t.size > 0 else "short",
                    "entry_price": float(t.price),
                    "stop_loss": 0.0,
                    "take_profit": 0.0,
                    "exit_price": 0.0,
                    "exit_reason": "strategy_exit",
                    "pnl_gross": float(t.pnl),
                    "pnl_net": float(t.pnl),
                }
            )

    final_value = cerebro.broker.getvalue()
    return {
        "engine": "backtrader",
        "trades": trades,
        "metadata": {
            "data_rows": len(closes),
            "initial_cash": initial_cash,
            "final_value": final_value,
            "cost_scenario": cost_scenario,
        },
    }
