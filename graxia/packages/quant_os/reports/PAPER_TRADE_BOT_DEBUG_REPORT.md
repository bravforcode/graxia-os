# Paper Trading Bot — Debug Report

**Date:** 2026-07-13
**Status:** Fixed and running

---

## Issues Found

### Issue 1: ModuleNotFoundError (CRITICAL)
**Error:** `ModuleNotFoundError: No module named 'graxia'`

**Root cause:** `paper_trade_bot.py` imported `from graxia.packages.quant_os.core.safe_pickle import safe_load_model` BEFORE setting up `sys.path`. The import happened before the path was configured.

**Fix:** Added `GRAXIA_PARENT` to `sys.path` before the import:
```python
BASE = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = BASE.parent.parent  # graxia/os/graxia
GRAXIA_PARENT = GRAXIA_ROOT.parent  # graxia/os/ (where graxia package lives)
sys.path.insert(0, str(GRAXIA_PARENT))
sys.path.insert(0, str(BASE))
```

### Issue 2: Forbidden Class in Pickle (CRITICAL)
**Error:** `_pickle.UnpicklingError: Forbidden class in pickle: xgboost.sklearn.XGBClassifier`

**Root cause:** `safe_load_model()` uses `RestrictedUnpickler` which only allows numpy + builtins. The xgboost model needs `MLUnpickler`.

**Fix:** Changed import to use `safe_load_ml_model`:
```python
from graxia.packages.quant_os.core.safe_pickle import safe_load_ml_model as safe_load_model
```

### Issue 3: Wrong --symbol Argument
**Error:** `paper_trade_bot.py: error: unrecognized arguments: --symbol XAUUSD`

**Root cause:** The script doesn't accept `--symbol` argument. It uses hardcoded `SYMBOL = "XAUUSD"` at line 41.

**Fix:** Run without `--symbol`:
```bash
python paper_trade_bot.py  # not: python paper_trade_bot.py --symbol XAUUSD
```

## Current Status

- **Spread measurement:** Running (PID 21032) — collecting spread data every 60 seconds
- **Paper trade bot:** Running (PID 34864) — waiting for signals with confidence >= 0.85

## Files Modified

| File | Change |
|------|--------|
| `scripts/paper_trade_bot.py:34-38` | Added GRAXIA_PARENT to sys.path before import |
| `scripts/paper_trade_bot.py:34` | Changed `safe_load_model` → `safe_load_ml_model` |

## Windows Task Scheduler Setup

Created `scripts/setup_task_scheduler.ps1` for automated startup:
- Run as Administrator to create tasks
- Spread measurement: Runs every 60 seconds
- Paper trade bot: Runs at startup, restarts on failure

Created `start_paper_trading.bat` for manual startup:
- Double-click to start both processes
- Runs in background (minimized)

## QuantConnect Integration

Created `reports/QUANTCONNECT_INTEGRATION_GUIDE.md` with:
- 3 integration options (Cloud, LEAN Local, Hybrid)
- REST API examples
- Data pipeline integration
- Cost calibration guide
- Migration checklist

**Recommended:** Use QuantConnect for paper trading validation, keep quant_os for strategy generation.
