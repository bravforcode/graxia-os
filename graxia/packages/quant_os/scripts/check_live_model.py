"""Check what features the live model expects."""
from graxia.packages.quant_os.core.safe_pickle import safe_load_model
from pathlib import Path

model_path = Path("ml/models/xgboost_live_20260626.pkl")
raw = safe_load_model(model_path)

if isinstance(raw, dict):
    model = raw.get("model", raw)
    features = raw.get("feature_names", [])
    print(f"Model type: {type(model).__name__}")
    print(f"Feature count: {len(features)}")
    print("Features:")
    for i, f in enumerate(features, 1):
        print(f"  {i:2d}. {f}")
else:
    print(f"Model type: {type(raw).__name__}")
    print("No feature_names in pickle")
