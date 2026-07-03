from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN

# ponytail: deterministic historical sizing, no MT5 dependency


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    trade_contract_size: Decimal
    trade_tick_size: Decimal
    trade_tick_value: Decimal
    volume_step: Decimal
    volume_min: Decimal
    volume_max: Decimal
    stops_level_points: Decimal
    snapshot_hash: str = ""

    def __post_init__(self):
        if not self.snapshot_hash:
            raw = f"{self.symbol}{self.trade_contract_size}{self.trade_tick_size}{self.trade_tick_value}"
            object.__setattr__(self, "snapshot_hash", hashlib.sha256(raw.encode()).hexdigest()[:16])


@dataclass(frozen=True)
class HistoricalAccountSnapshot:
    equity: Decimal
    balance: Decimal
    free_margin: Decimal


@dataclass(frozen=True)
class PositionSizingDecision:
    volume: Decimal
    volume_before_round: Decimal
    risk_amount: Decimal
    risk_budget: Decimal
    loss_at_stop: Decimal
    margin_estimate: Decimal
    rejected: bool
    rejection_reasons: list[str] = field(default_factory=list)
    contract_snapshot_id: str = ""


class HistoricalSizingProviderImpl:
    def size(
        self,
        contract_snapshot: ContractSpec,
        account_snapshot: HistoricalAccountSnapshot,
        entry_price: Decimal,
        stop_loss: Decimal,
        side: str,
        risk_policy: dict,
    ) -> PositionSizingDecision:
        risk_per_trade_bps = risk_policy.get("risk_per_trade_bps", 100)
        rejection_reasons: list[str] = []

        risk_budget = account_snapshot.equity * Decimal(risk_per_trade_bps) / Decimal(10000)

        distance_ticks = abs(entry_price - stop_loss) / contract_snapshot.trade_tick_size
        one_lot_loss = distance_ticks * contract_snapshot.trade_tick_value

        if one_lot_loss == 0:
            return PositionSizingDecision(
                volume=Decimal(0),
                volume_before_round=Decimal(0),
                risk_amount=Decimal(0),
                risk_budget=risk_budget,
                loss_at_stop=Decimal(0),
                margin_estimate=Decimal(0),
                rejected=True,
                rejection_reasons=["stop loss equals entry price"],
                contract_snapshot_id=contract_snapshot.snapshot_hash,
            )

        raw_volume = risk_budget / one_lot_loss

        volume = (raw_volume / contract_snapshot.volume_step).to_integral_value(rounding=ROUND_DOWN) * contract_snapshot.volume_step
        volume = max(volume, Decimal(0))

        loss_at_stop = volume * one_lot_loss
        margin_estimate = volume * contract_snapshot.trade_contract_size * entry_price / Decimal(1000)

        if volume < contract_snapshot.volume_min:
            rejection_reasons.append(
                f"volume {volume} below minimum {contract_snapshot.volume_min}"
            )

        if volume > contract_snapshot.volume_max:
            rejection_reasons.append(
                f"volume {volume} above maximum {contract_snapshot.volume_max}"
            )

        rejected = len(rejection_reasons) > 0

        return PositionSizingDecision(
            volume=volume,
            volume_before_round=raw_volume,
            risk_amount=loss_at_stop,
            risk_budget=risk_budget,
            loss_at_stop=loss_at_stop,
            margin_estimate=margin_estimate,
            rejected=rejected,
            rejection_reasons=rejection_reasons,
            contract_snapshot_id=contract_snapshot.snapshot_hash,
        )
