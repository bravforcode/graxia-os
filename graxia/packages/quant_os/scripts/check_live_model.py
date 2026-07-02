"""Check what features the live model expects."""
import pickle
from pathlib import Path

model_path = Path("ml/models/xgboost_live_20260626.pkl")
with open(model_path, "rb") as f:
    raw = pickle.load(f)

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
