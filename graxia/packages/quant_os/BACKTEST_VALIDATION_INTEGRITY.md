# BACKTEST_VALIDATION_INTEGRITY.md — Phase 7

## 7.1 — Transaction Cost Model (Final Verification)

- **Costs subtracted in backtest**: `backtest/engine.py:1148` (`pnl -= total_fees`), `backtest/engine.py:1138-1148` (swap cost added/subtracted)
- **Per-trade**: Commission applied on entry (`engine.py:875`) and exit (`engine.py:1133`)
- **Slippage model**: Dynamic spread via `backtest/dynamic_spread_model.py` (session-aware) + static fallback of 0.5 pips
- **Swap costs**: Optional via `_SWAP_COST_AVAILABLE` flag. Default XAUUSD rates hardcoded (`engine.py:1228-1235`)
- **Worst-case scenario test**: NOT performed. No 2× spread stress test exists in backtest pipeline.

**P0 FINDING (from Phase 3)**: Metals commission double-count persists in backtest defaults.

## 7.2 — Fold Construction

- **Walk-forward**: `validation/walk_forward.py:55-74` — expanding window with purge/embargo gaps
- **Embargo**: Default 12 bars (`validation/walk_forward.py:59`)
- **CPCV**: `core/cross_validation.py:86-108` — embargoed purged train/test split
- **Test set isolation**: Walk-forward OOS folds are never touched during IS training — **PASS**

## 7.3 — Order Execution Realism

- **Entry**: Signal bar close → fill at **next bar open** — **PASS** (realistic)
- **Look-at-close, trade-at-open**: NOT present — signal is generated from bar data, execution on next bar. **PASS**

## 7.4 — Position Management in Backtest

- **Max positions**: `backtest/engine.py:862` — `if len(self.positions) >= self.config.max_positions: return`
- **New signal while position open**: Rejected if same symbol (`engine.py:864-865`)
- **Consistent with live**: `core/trading_loop.py:207-208` — kill switch blocks, but no position-count check in TradingLoop itself (enforced by risk layer)

## 7.5 — Performance Degradation Analysis

Walk-forward results show OOS/IS ratio in `backtest/walk_forward.py:257-260`:
```python
if is_sharpe > 0 and oos_sharpe != float("inf"):
    window.wfe = oos_sharpe / is_sharpe
```
WFE (Walk-Forward Efficiency) computed but no systematic degradation threshold enforced. **P2 FINDING**.

## 7.6 — Final Verdict

**INSUFFICIENT EVIDENCE** — no statistically significant, cost-adjusted, out-of-sample edge has been confirmed across all 15 instruments. Only XAUUSD and EURUSD have WF results. The metals commission double-count (Phase 3 P0) means metals results are unreliable.

## 7.9 — Per-Instrument Walk-Forward Coverage Table

| Instrument | Asset Class | WF Run? | OOS Sharpe | Meets Data-Sufficiency? |
|---|---|---|---|---|
| EURUSD | FX | YES | UNVERIFIED (not in current codebase outputs) | YES (D1 confirmed) |
| GBPUSD | FX | NO | N/A | UNVERIFIED |
| USDJPY | FX | NO | N/A | UNVERIFIED |
| USDCAD | FX | NO | N/A | UNVERIFIED |
| USDCHF | FX | NO | N/A | UNVERIFIED |
| AUDUSD | FX | NO | N/A | UNVERIFIED |
| NZDUSD | FX | NO | N/A | UNVERIFIED |
| BTCUSD | Crypto | NO | N/A | UNVERIFIED |
| ETHUSD | Crypto | NO | N/A | UNVERIFIED |
| NAS100 | Indices | NO | N/A | UNVERIFIED |
| US30 | Indices | NO | N/A | UNVERIFIED |
| XAUUSD | Metals | YES | UNVERIFIED | PARTIAL (M1 insufficient) |
| XAGUSD | Metals | NO | N/A | UNVERIFIED |
| XPDUSD | Metals | NO | N/A | UNVERIFIED |
| XPTUSD | Metals | NO | N/A | UNVERIFIED |

**13 of 15 instruments have NO OOS evidence.** Trading or paper-trading these instruments is currently unvalidated.

---

**P0 Findings**: 1 (metals commission double-count — from Phase 3)
**P1 Findings**: 1 (13 instruments with no WF coverage)
**P2 Findings**: 2 (no worst-case cost test, no systematic WFE threshold)
