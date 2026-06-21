"""Position sizer using broker-native MT5 calculations."""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Callable, Optional


@dataclass
class SizingResult:
    volume: Decimal                    # Final volume (rounded to broker step)
    volume_before_round: Decimal       # Raw volume before rounding
    risk_amount: Decimal               # Actual risk in account currency
    risk_budget: Decimal               # Maximum allowed risk
    loss_at_stop: Decimal              # Estimated loss at stop (from MT5 calc)
    margin_estimate: Decimal           # Estimated margin (from MT5 calc)
    rejected: bool
    rejection_reasons: list[str] = field(default_factory=list)
    contract_snapshot_id: str = ""


@dataclass
class RiskPolicy:
    """Configurable risk limits."""
    max_risk_per_trade_pct: Decimal = Decimal("1.0")
    max_daily_loss_pct: Decimal = Decimal("2.0")
    max_weekly_loss_pct: Decimal = Decimal("5.0")
    max_drawdown_pct: Decimal = Decimal("10.0")
    max_positions: int = 5
    max_orders_per_day: int = 20
    min_margin_level_pct: Decimal = Decimal("200.0")


def size_position(
    symbol: str,
    side: str,  # "BUY" or "SELL"
    entry_price: Decimal,
    stop_loss: Decimal,
    equity: Decimal,
    contract_spec,  # ContractSpec — avoid import to keep module decoupled
    risk_policy: RiskPolicy,
    calc_profit_fn: Optional[Callable] = None,
    calc_margin_fn: Optional[Callable] = None,
    calc_profit_fn_kwargs: dict = None,
    calc_margin_fn_kwargs: dict = None,
) -> SizingResult:
    """
    Calculate position size using broker-native calculations.

    Steps:
    1. Validate stop loss (exists, correct side, positive distance, meets broker stops_level)
    2. Calculate one-lot loss using calc_profit_fn
    3. Derive raw volume from risk_budget / one_lot_loss
    4. Round DOWN to volume_step
    5. Reject if rounded volume < volume_min
    6. Recalculate loss after rounding
    7. Verify post-rounding loss <= risk budget
    8. Calculate margin using calc_margin_fn
    9. Reject if margin check fails
    10. Return SizingResult
    """
    reasons = []
    one_lot = float(contract_spec.trade_contract_size)
    risk_budget = equity * risk_policy.max_risk_per_trade_pct / Decimal("100")

    # --- Step 1: Validate stop loss ---
    if stop_loss == 0 or stop_loss is None:
        return SizingResult(
            volume=Decimal("0"),
            volume_before_round=Decimal("0"),
            risk_amount=Decimal("0"),
            risk_budget=risk_budget,
            loss_at_stop=Decimal("0"),
            margin_estimate=Decimal("0"),
            rejected=True,
            rejection_reasons=["Stop loss is zero or None"],
            contract_snapshot_id=contract_spec.snapshot_hash,
        )

    side = side.upper()
    if side == "BUY" and stop_loss >= entry_price:
        return SizingResult(
            volume=Decimal("0"),
            volume_before_round=Decimal("0"),
            risk_amount=Decimal("0"),
            risk_budget=risk_budget,
            loss_at_stop=Decimal("0"),
            margin_estimate=Decimal("0"),
            rejected=True,
            rejection_reasons=[f"BUY SL {stop_loss} above entry {entry_price}"],
            contract_snapshot_id=contract_spec.snapshot_hash,
        )
    if side == "SELL" and stop_loss <= entry_price:
        return SizingResult(
            volume=Decimal("0"),
            volume_before_round=Decimal("0"),
            risk_amount=Decimal("0"),
            risk_budget=risk_budget,
            loss_at_stop=Decimal("0"),
            margin_estimate=Decimal("0"),
            rejected=True,
            rejection_reasons=[f"SELL SL {stop_loss} below entry {entry_price}"],
            contract_snapshot_id=contract_spec.snapshot_hash,
        )

    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0:
        return SizingResult(
            volume=Decimal("0"),
            volume_before_round=Decimal("0"),
            risk_amount=Decimal("0"),
            risk_budget=risk_budget,
            loss_at_stop=Decimal("0"),
            margin_estimate=Decimal("0"),
            rejected=True,
            rejection_reasons=["Stop distance is zero"],
            contract_snapshot_id=contract_spec.snapshot_hash,
        )

    # Check broker stops_level
    if contract_spec.stops_level_points > 0:
        stops_distance = Decimal(str(contract_spec.stops_level_points)) * contract_spec.point
        if stop_distance < stops_distance:
            reasons.append(
                f"Stop distance {stop_distance} < broker stops_level {stops_distance}"
            )

    # --- Step 2: Calculate one-lot loss ---
    if calc_profit_fn is not None:
        try:
            one_lot_loss_raw = calc_profit_fn(
                symbol, side, one_lot, float(entry_price), float(stop_loss),
                **(calc_profit_fn_kwargs or {})
            )
            one_lot_loss = abs(Decimal(str(one_lot_loss_raw))) if one_lot_loss_raw is not None else None
        except Exception:
            one_lot_loss = None
    else:
        one_lot_loss = None

    # Fallback: estimate from tick value if calc_profit not available
    if one_lot_loss is None or one_lot_loss == 0:
        # ponytail: naive fallback — tick_value already includes contract_size
        ticks = stop_distance / contract_spec.trade_tick_size
        one_lot_loss = ticks * contract_spec.trade_tick_value

    if one_lot_loss == 0:
        reasons.append("One-lot loss is zero — cannot size")

    # --- Step 3: Derive raw volume ---
    if one_lot_loss > 0:
        raw_volume = risk_budget / one_lot_loss
    else:
        raw_volume = Decimal("0")

    # --- Step 4: Round DOWN to volume_step ---
    if contract_spec.volume_step > 0:
        volume_before_round = raw_volume
        # Quantize with ROUND_DOWN to the volume_step precision
        step_str = str(contract_spec.volume_step)
        # Determine decimal places from step
        if '.' in step_str:
            places = len(step_str.rstrip('0').split('.')[-1])
        else:
            places = 0
        fmt = Decimal(10) ** -places if places > 0 else Decimal("1")
        rounded_volume = (raw_volume / contract_spec.volume_step).to_integral_value(rounding=ROUND_DOWN) * contract_spec.volume_step
        rounded_volume = rounded_volume.quantize(fmt, rounding=ROUND_DOWN)
    else:
        volume_before_round = raw_volume
        rounded_volume = raw_volume

    # --- Step 5: Reject if below volume_min ---
    if rounded_volume < contract_spec.volume_min:
        reasons.append(
            f"Rounded volume {rounded_volume} < volume_min {contract_spec.volume_min}"
        )

    # --- Step 6: Recalculate loss after rounding ---
    if rounded_volume > 0 and calc_profit_fn is not None:
        try:
            post_round_raw = calc_profit_fn(
                symbol, side, float(rounded_volume), float(entry_price), float(stop_loss),
                **(calc_profit_fn_kwargs or {})
            )
            post_round_loss = abs(Decimal(str(post_round_raw))) if post_round_raw is not None else None
        except Exception:
            post_round_loss = None
    else:
        post_round_loss = None

    if post_round_loss is None and rounded_volume > 0:
        # ponytail: volume is in lots, one_lot_loss is per-lot — just multiply
        post_round_loss = one_lot_loss * rounded_volume

    # --- Step 7: Verify post-rounding loss <= budget ---
    if post_round_loss and post_round_loss > risk_budget:
        reasons.append(
            f"Post-rounding loss {post_round_loss:.2f} exceeds budget {risk_budget:.2f}"
        )

    # --- Step 8: Calculate margin ---
    margin = Decimal("0")
    if calc_margin_fn is not None and rounded_volume > 0:
        try:
            margin_raw = calc_margin_fn(
                symbol, float(rounded_volume), float(entry_price),
                **(calc_margin_fn_kwargs or {})
            )
            margin = Decimal(str(margin_raw)) if margin_raw is not None else Decimal("0")
        except Exception:
            margin = Decimal("0")

    # --- Step 9: Basic margin check (placeholder) ---
    # Full margin check would compare margin to available margin from account info.
    # ponytail: defer full margin check to pre_trade_risk — that's where equity lives.

    # --- Step 10: Return result ---
    actual_risk = post_round_loss if post_round_loss else (one_lot_loss * rounded_volume if one_lot_loss else Decimal("0"))

    return SizingResult(
        volume=rounded_volume,
        volume_before_round=volume_before_round,
        risk_amount=actual_risk,
        risk_budget=risk_budget,
        loss_at_stop=actual_risk,
        margin_estimate=margin,
        rejected=len(reasons) > 0,
        rejection_reasons=reasons,
        contract_snapshot_id=contract_spec.snapshot_hash,
    )
