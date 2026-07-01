import sys
from pathlib import Path
_QUANT_OS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_QUANT_OS))
print(f"QUANT_OS path: {_QUANT_OS}")
print(f"sys.path[0:5]: {sys.path[:5]}")

from quant_os.core.schemas import XAUUSD_M15_SCHEMA
print("SUCCESS")
