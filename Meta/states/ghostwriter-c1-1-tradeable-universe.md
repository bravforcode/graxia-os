# ghostwriter — Task C1.1: tradeable_universe.json contradiction

**Status:** DONE (2026-08-06) — NOT committed (controller commits)

## What was done
Edited `graxia/packages/quant_os/config/tradeable_universe.json` to resolve symbol contradictions under spec §5.2 multi-day sampling bar.

## Changes (all applied via native Edit)
1. EURUSD removed from `excluded` (stays in `measuring`) — real multi-day evidence: FROM_TICKS, n=56,115, window 2026-07-31→08-05, duration_days=4.42, mode mt5_copy_ticks_range_backfill.
2. GBPUSD removed from `measuring` (kept in `excluded`) — single-day evidence: FROM_TICKS, n=214,512, window 24h tick parquet (2026-06-25), duration_days=1, mode tick_parquet. Reason rewritten with evidence pointer to cost_calibration.json + spec §5.2.
3. **EXTRA (found via verify #2 `{}` contract):** BTCUSD + US30 had the SAME pre-existing contradiction.
   - BTCUSD: duration_days=4.4, mode mt5_copy_ticks_range_backfill → **meets bar** → removed from `excluded`, stays in `measuring`.
   - US30: duration_days=1, mode tick_parquet → **fails bar** → removed from `measuring`, kept in `excluded` with corrected single-day reason (was false "no cost calibration data").
4. Fixed trailing comma after EURUSD (last measuring element) after US30 removal.

## Verification (all pass)
- `valid json`
- dupe check → `{}`
- EURUSD measuring: True excluded: False; GBPUSD measuring: False excluded: True
- BTCUSD measuring: True excluded: False; US30 measuring: False excluded: True

## Notes
- python not on PATH; used full path `C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe`.
- Do NOT commit — controller handles.
