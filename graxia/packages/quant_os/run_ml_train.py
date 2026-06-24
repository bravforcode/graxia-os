"""
ML Training Script - Train and evaluate ML models for signal prediction

Usage:
    cd "graxia os" directory
    python graxia/packages/quant_os/run_ml_train.py
"""

import sys
import os
import json
from datetime import datetime, timezone

# Add graxia os root to path (current working directory when run from graxia os)
sys.path.insert(0, os.getcwd())

from graxia.packages.quant_os.backtest.data_loader import generate_sample_data
from graxia.packages.quant_os.ml.pipeline import FeatureEngineer, MLTrainer, DriftDetector


def main():
    print("Quant OS - ML Training Pipeline")
    print("=" * 60)
    
    # Step 1: Load real data — FAIL-LOUD if not available
    print("\nSTEP 1: Loading real data...")
    
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    csv_path = os.path.join(data_dir, "EURUSD=X.csv")
    
    if not os.path.exists(csv_path):
        raise RuntimeError(
            f"\n{'='*60}\n"
            f"ML TRAINING REQUIRES REAL DATA\n"
            f"{'='*60}\n"
            f"No data file found at: {csv_path}\n\n"
            f"ML models trained on synthetic data are USELESS for live trading.\n\n"
            f"FIX:\n"
            f"  1. Run: python run_backtest.py (downloads real data first)\n"
            f"  2. Or manually place EURUSD=X.csv in the data/ folder\n"
            f"{'='*60}"
        )
    
    from graxia.packages.quant_os.backtest.data_loader import load_yahoo_csv
    data, timestamps = load_yahoo_csv("EURUSD=X", data_dir)
    print(f"Loaded {len(data['close'])} bars of REAL data")
    
    # Step 2: Generate features
    print("\nSTEP 2: Generating features...")
    engineer = FeatureEngineer()
    feature_set = engineer.generate_features(data, timestamps)
    print(f"Generated {len(feature_set.features)} samples with {len(feature_set.feature_names)} features")
    print(f"Feature names: {feature_set.feature_names[:10]}...")
    
    # Step 3: Train XGBoost model
    print("\nSTEP 3: Training XGBoost model...")
    trainer = MLTrainer(model_dir=os.path.join(os.path.dirname(__file__), "ml", "models"))
    result = trainer.train(feature_set, model_type="xgboost", test_ratio=0.2)
    
    print(f"Model: {result.model_name}")
    print(f"Version: {result.version}")
    print(f"Accuracy: {result.accuracy:.2%}")
    print(f"Precision: {result.precision:.2%}")
    print(f"Recall: {result.recall:.2%}")
    print(f"F1 Score: {result.f1_score:.2%}")
    print(f"Training samples: {result.training_samples}")
    print(f"Model saved to: {result.model_path}")
    
    # Step 4: Walk-forward training
    print("\nSTEP 4: Walk-forward validation...")
    wf_results = trainer.train_walk_forward(feature_set, model_type="xgboost", n_windows=3)
    
    print(f"Walk-forward windows: {len(wf_results)}")
    for i, wf in enumerate(wf_results):
        print(f"  Window {i+1}: IS Acc={wf.accuracy:.2%}, OOS Acc={wf.oos_accuracy:.2%}")
    
    # Step 5: Feature importance
    print("\nSTEP 5: Top 10 Feature Importance:")
    sorted_features = sorted(result.feature_importance.items(), key=lambda x: x[1], reverse=True)
    for name, imp in sorted_features[:10]:
        print(f"  {name}: {imp:.4f}")
    
    # Step 6: Test drift detection
    print("\nSTEP 6: Testing drift detection...")
    detector = DriftDetector(window_size=50, threshold=0.10)
    
    # Simulate predictions
    import numpy as np
    np.random.seed(42)
    for _ in range(100):
        predicted = np.random.choice([0, 1, 2], p=[0.6, 0.2, 0.2])
        actual = np.random.choice([0, 1, 2], p=[0.6, 0.2, 0.2])
        detector.record(predicted, actual)
    
    drift_status = detector.check_drift()
    print(f"Drift detected: {drift_status['drifted']}")
    print(f"Recent accuracy: {drift_status['recent_accuracy']:.2%}")
    print(f"Recommendation: {drift_status['recommendation']}")
    
    # Save results
    output_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, "ml_training_results.json")
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": {
                "name": result.model_name,
                "version": result.version,
                "accuracy": result.accuracy,
                "precision": result.precision,
                "recall": result.recall,
                "f1_score": result.f1_score,
                "oos_accuracy": result.oos_accuracy,
                "training_samples": result.training_samples,
                "model_path": result.model_path,
            },
            "walk_forward": [
                {
                    "window": i+1,
                    "is_accuracy": wf.accuracy,
                    "oos_accuracy": wf.oos_accuracy,
                }
                for i, wf in enumerate(wf_results)
            ],
            "top_features": [
                {"name": name, "importance": imp}
                for name, imp in sorted_features[:10]
            ],
            "drift_status": drift_status,
        }, f, indent=2, default=str)
    
    print(f"\n{'=' * 60}")
    print(f"Results saved to: {output_file}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
