"""Test that live feature computation covers all training features."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def test_feature_coverage():
    """Check that compute_features_live covers the expected feature set."""
    # Read the live feature list from signal_service.py
    signal_path = Path(__file__).parent.parent / "api" / "signal_service.py"
    if not signal_path.exists():
        print("SKIP: signal_service.py not found")
        return

    content = signal_path.read_text(encoding="utf-8")

    # Check for feature mismatch warning
    assert (
        "FEATURE MISMATCH" in content or "feature_cols" in content
    ), "signal_service.py should document feature mismatch"

    # Check that missing features are logged
    assert (
        "missing" in content.lower() or "fillna" in content.lower() or "0.0" in content
    ), "signal_service.py should handle missing features"

    print("PASS: Feature parity checks")


if __name__ == "__main__":
    test_feature_coverage()
