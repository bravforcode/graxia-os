# config/ — Quant OS Configuration

## Canonical source of truth

**`core/config.py`** — `QuantConfig` dataclass (30+ consumers).

All code should import from here:
```python
from core.config import get_config
cfg = get_config()
print(cfg.mt5_server)
```

The `get_settings` alias also works: `from core.config import get_settings`

## DEPRECATED: `unified_settings.py`

`config/unified_settings.py` (`QuantSettings`) is **deprecated**.
It remains for backward compatibility only and will be removed.
Do NOT add new consumers — use `core.config.get_config()` instead.

## Legacy files (deprecated)

The following files are **backward-compatibility shims** that re-export from `unified_settings` with a `DeprecationWarning`:

| File | Status | Migrates to |
|------|--------|-------------|
| `pixelrag_config.py` | DEPRECATED | `from config.unified_settings import settings` |
| `tv_config.py` | DEPRECATED | `from config.unified_settings import settings` |
| `tv_cdp_config.py` | DEPRECATED | `from config.unified_settings import settings` |
| `telegram_config.py` | DEPRECATED | `from config.unified_settings import settings` |

## Data files (still used)

| File | Used by | Notes |
|------|---------|-------|
| `cost_calibration.json` | `load_cost_calibration()` | Asset-specific cost data |
| `paper_trade_config.json` | `load_paper_trade_config()` | Paper trading defaults |
| `adjusted_verdicts.json` | `load_adjusted_verdicts()` | Risk verdict overrides |
| `broker_profile.schema.json` | `load_broker_profile_template()` | Broker schema |
| `broker_profile.template.yaml` | `load_broker_profile_template()` | Broker defaults |
| `telegram_config.toml` | Telegram shim | Bot token + alerts |
| `.env.example` | dotenv | Environment variable template |

## Migration guide

### For `pixelrag_config.py` consumers:
```python
# OLD (deprecated):
from config.pixelrag_config import PIXELRAG_URL

# NEW:
from config.unified_settings import settings
url = settings.PIXELRAG_URL
```

### For `tv_config.py` consumers:
```python
# OLD (deprecated):
from config.tv_config import TV_MCP_URL

# NEW:
from config.unified_settings import settings
url = settings.TV_MCP_URL
```

### For `tv_cdp_config.py` consumers:
```python
# OLD (deprecated):
from config.tv_cdp_config import TV_CDP_URL

# NEW:
from config.unified_settings import settings
url = settings.TV_CDP_URL
```

## Adding new config

1. Add the field to `core/config.py` `QuantConfig` dataclass with a default value
2. Add env var override in `_validate_from_env`: `os.getenv("FIELD_NAME", self.field_name)`
3. Add validation if needed (`__post_init__` or `_enforce_hard_limits`)
4. Update this README if adding a new data file
