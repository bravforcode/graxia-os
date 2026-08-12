# Researcher State — Cross-Asset Features (XAUUSD)

**Date:** 2026-06-26
**Task:** Research most impactful cross-asset features for XAUUSD M15 models (DXY, 10Y real yield, VIX, WTI).

## Status: COMPLETE

## Deliverable
- `reports/cross_asset_features_xauusd.md` — full research doc with sources, feature formulas, correlations, alignment code, priority ranking.

## Key findings (delta)
- **Priority:** 1) 10Y real yield (DFII10, strongest ~−0.7 to −0.9, regime anchor) → 2) DXY (DX-Y.NYB, intraday co-movement ~−0.4 to −0.6) → 3) VIX (regime gate, episodic) → 4) WTI (weakest, unstable).
- **Data sources verified LIVE 2026-06-26:** FRED DFII10=2.23%, DTWEXBGS=120.40, VIXCLS=18.63, DCOILWTICO=$78.94. Bonus discovered: GVZCLS (gold implied vol), T10YIE (breakeven).
- **Critical lookahead guard:** daily macro must use shift_days=1 (prior day's confirmed value) before ffill into M15 — fail-closed per CONSTITUTION no-lookahead invariant.
- **Multicollinearity warning:** real yield / DXY / VIX share Fed-policy factor — don't dump raw into linear model; orthogonalize or gate.

## Implementation path (for dev agent delegation)
1. Create `data/cross_asset/` dir; fetch via yfinance (DXY 1H/CL=F) + fredapi (DFII10,VIX,WTI,GVZCLS).
2. Store one parquet per asset + manifest.json (SHA256) per `scripts/hash_data_manifests.py` convention.
3. `align_daily_to_m15()` helper with shift_days=1 — see doc §5.4.
4. Feature builder `build_cross_asset_features()` — doc §5.7.
5. Validate: re-run `test_lookahead_regression.py`, `test_mtf_leak.py`; compute rolling IC via block-bootstrap; check VIF.

## Pending / delegation
- Implementation → **developer agent** (build fetcher + feature pipeline + manifest).
- Validation → **auditor agent** (lookahead gate, VIF, deflated Sharpe after feature add).
- Pre-register the feature set + expected signs before measuring IC (matches `Meta/pre_register_b2.md` discipline).

## Files touched
- Wrote: `reports/cross_asset_features_xauusd.md` (new)
- Wrote: `Meta/states/researcher_cross_asset_features.md` (this state)
