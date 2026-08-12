"""
ml_tracking/mlflow_tracker.py — MLflow Experiment Tracking
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import mlflow
import mlflow.sklearn
from config import PROJECT_ROOT


class MLTracker:
    """MLflow experiment tracking for trading models"""

    def __init__(self, experiment_name: str = "quant_os_trading"):
        self.experiment_name = experiment_name
        mlflow.set_tracking_uri(f"file://{PROJECT_ROOT}/data_pipeline/mlruns")
        mlflow.set_experiment(experiment_name)

    def log_backtest(self, strategy_name: str, symbol: str, metrics: dict):
        """Log backtest results"""
        with mlflow.start_run(run_name=f"{strategy_name}_{symbol}_{datetime.now():%Y%m%d}"):
            mlflow.log_param("strategy", strategy_name)
            mlflow.log_param("symbol", symbol)
            mlflow.log_param("timestamp", datetime.now().isoformat())

            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    mlflow.log_metric(key, value)

            print(f"  MLflow: Logged {strategy_name}/{symbol}")

    def log_model(self, model, model_name: str, metrics: dict = None):
        """Log a trained model"""
        with mlflow.start_run(run_name=f"model_{model_name}_{datetime.now():%Y%m%d}"):
            mlflow.log_param("model_name", model_name)
            mlflow.sklearn.log_model(model, model_name)
            if metrics:
                for key, value in metrics.items():
                    if isinstance(value, (int, float)):
                        mlflow.log_metric(key, value)
            print(f"  MLflow: Logged model {model_name}")

    def log_pipeline_run(self, results: dict):
        """Log a pipeline execution"""
        with mlflow.start_run(run_name=f"pipeline_{datetime.now():%Y%m%d_%H%M}"):
            mlflow.log_param("pipeline_run", datetime.now().isoformat())
            for key, value in results.items():
                if isinstance(value, (int, float)):
                    mlflow.log_metric(f"pipeline_{key}", value)
            print("  MLflow: Logged pipeline run")

    def get_experiment_runs(self) -> list:
        """Get all runs for the experiment"""
        experiment = mlflow.get_experiment_by_name(self.experiment_name)
        if experiment:
            return mlflow.search_runs(experiment_ids=[experiment.experiment_id])
        return []
