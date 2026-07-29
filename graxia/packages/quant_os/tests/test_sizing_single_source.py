"""Single-source sizing: raw-units formula + units->lots boundary conversion.

Guards against the 2-source-of-truth drift (F27 class) and the ~100x oversize
bug documented in reports/live_sizing_units_lots_gap_20260728.md.

Key safety assertion: a 1%-risk XAUUSD signal must size to 0.05 lots (5.0 oz),
NEVER 5.0 lots (500 oz / ~$1.2M on a $10k account = account wipe).
"""

import sys
from pathlib import Path

# Make the graxia package importable when run from the quant_os dir
_GRAXIA_ROOT = Path(__file__).resolve().parents[3]
if str(_GRAXIA_ROOT) not in sys.path:
    sys.path.insert(0, str(_GRAXIA_ROOT))

from graxia.packages.quant_os.core.contract_specs import (  # noqa: E402
    get_spec,
    risk_based_units,
)


def test_risk_based_units_xauusd_raw_units():
    # equity=10000, risk 1%, entry=2400, stop=2380 -> 10000*0.01/20 = 5.0 oz
    qty = risk_based_units(10000.0, 0.01, 2400.0, 2380.0)
    assert abs(qty - 5.0) < 1e-9


def test_risk_based_units_zero_stop_returns_zero():
    assert risk_based_units(10000.0, 0.01, 2400.0, 2400.0) == 0.0
    assert risk_based_units(10000.0, 0.01, 2400.0, None) == 0.0


def test_units_to_lots_boundary_conversion():
    # XAUUSD contract_size = 100 -> 5.0 units => 0.05 lots (SAFETY-CRITICAL)
    spec = get_spec("XAUUSD")
    lots = 5.0 / float(spec.contract_size)
    assert abs(lots - 0.05) < 1e-9
    # NAS100 contract_size = 1 -> 5.0 units => 5.0 lots
    spec_nas = get_spec("NAS100")
    lots_nas = 5.0 / float(spec_nas.contract_size)
    assert abs(lots_nas - 5.0) < 1e-9


def test_missing_spec_returns_none_fail_closed():
    assert get_spec("NONEXISTENT_SYMBOL") is None
