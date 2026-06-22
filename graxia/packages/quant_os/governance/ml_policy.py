from enum import Enum
from dataclasses import dataclass
from typing import Optional


class MLUsageType(Enum):
    REGIME_CLASSIFICATION = "regime_classification"
    VOLATILITY_FORECAST = "volatility_forecast"
    ANOMALY_DETECTION = "anomaly_detection"
    PROBABILITY_CALIBRATION = "probability_calibration"
    POST_TRADE_ANALYTICS = "post_trade_analytics"
    PRICE_PREDICTION = "price_prediction"  # FORBIDDEN
    HYPERPARAMETER_SELECTION = "hyperparameter_selection"  # FORBIDDEN


class MLPhase(Enum):
    TRAINING = "training"
    VALIDATION = "validation"
    SHADOW = "shadow"
    DEMO = "demo"
    LIVE = "live"


ALLOWED_ML_USAGES = {
    MLUsageType.REGIME_CLASSIFICATION,
    MLUsageType.VOLATILITY_FORECAST,
    MLUsageType.ANOMALY_DETECTION,
    MLUsageType.PROBABILITY_CALIBRATION,
    MLUsageType.POST_TRADE_ANALYTICS,
}

FORBIDDEN_ML_USAGES = {
    MLUsageType.PRICE_PREDICTION,
    MLUsageType.HYPERPARAMETER_SELECTION,
}


@dataclass
class MLModelRecord:
    model_id: str
    usage_type: MLUsageType
    training_data_hash: str
    feature_schema_hash: str
    model_version: str
    trained_at_utc: str
    training_period_start: str
    training_period_end: str


class MLPolicyGuard:
    """Enforce ML policy: allowed uses, required controls, forbidden patterns."""

    def __init__(self):
        self._models: dict[str, MLModelRecord] = {}

    def check_usage(self, usage: MLUsageType) -> tuple[bool, str]:
        if usage in FORBIDDEN_ML_USAGES:
            return False, f"FORBIDDEN_ML_USAGE:{usage.value}"
        if usage in ALLOWED_ML_USAGES:
            return True, f"ALLOWED:{usage.value}"
        return False, f"UNKNOWN_USAGE:{usage.value}"

    def register_model(self, record: MLModelRecord) -> tuple[bool, str]:
        allowed, reason = self.check_usage(record.usage_type)
        if not allowed:
            return False, reason

        self._models[record.model_id] = record
        return True, "REGISTERED"

    def check_controls(self, model_id: str, phase: MLPhase) -> tuple[bool, list[str]]:
        record = self._models.get(model_id)
        if not record:
            return False, ["MODEL_NOT_REGISTERED"]

        issues = []

        if phase in (MLPhase.SHADOW, MLPhase.DEMO, MLPhase.LIVE):
            if not record.feature_schema_hash:
                issues.append("MISSING_FEATURE_SCHEMA")
            if not record.training_data_hash:
                issues.append("MISSING_TRAINING_DATA_HASH")

        if phase == MLPhase.LIVE:
            issues.append("LIVE_ML_NOT_ALLOWED")

        return len(issues) == 0, issues

    def check_online_training(self, phase: MLPhase) -> tuple[bool, str]:
        if phase in (MLPhase.SHADOW, MLPhase.DEMO, MLPhase.LIVE):
            return False, f"ONLINE_TRAINING_FORBIDDEN:{phase.value}"
        return True, "ALLOWED"

    def check_self_promotion(self, model_id: str, promoted_by: str) -> tuple[bool, str]:
        if model_id == promoted_by:
            return False, "SELF_PROMOTION_FORBIDDEN"
        return True, "ALLOWED"

    def check_scaler_fit(self, fit_period: str, train_period: str) -> tuple[bool, str]:
        if fit_period != train_period:
            return False, f"SCALER_FIT_MISMATCH:fit={fit_period},train={train_period}"
        return True, "SCALER_FIT_CORRECT"

    def list_models(self) -> list[MLModelRecord]:
        return list(self._models.values())
