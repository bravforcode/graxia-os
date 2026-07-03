"""
Drift Monitor — Real-time prediction accuracy and feature distribution drift detection.

Tracks prediction outcomes over configurable windows, detects accuracy degradation,
monitors feature distribution shifts via PSI, and emits alerts when thresholds are breached.
"""

import json
import math
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_STATE_DIR = Path(__file__).parent / ".drift_state"


@dataclass(frozen=True)
class PredictionRecord:
    """A single prediction with its outcome."""

    timestamp: str
    model_version: str
    symbol: str
    predicted_label: int
    actual_label: int | None  # None if outcome is not yet known
    confidence: float
    feature_snapshot: dict[str, float] = field(default_factory=dict)


@dataclass
class DriftAlert:
    """Alert emitted when drift is detected."""

    alert_type: str  # "accuracy_drop", "feature_drift", "stale_model"
    severity: str  # "info", "warning", "critical"
    model_version: str
    symbol: str
    message: str
    metric_name: str
    current_value: float
    threshold: float
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class DriftReport:
    """Summary of drift status at a point in time."""

    model_version: str
    symbol: str
    total_predictions: int
    accuracy_window: float
    accuracy_trend: str  # "improving", "stable", "degrading"
    feature_drift_scores: dict[str, float]  # PSI per feature
    alerts: list[DriftAlert]
    report_time: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DriftMonitor:
    """
    Real-time drift detection for ML model predictions.

    Maintains a rolling window of predictions and outcomes, computes accuracy
    metrics, tracks feature distribution shifts using Population Stability Index
    (PSI), and emits alerts when predefined thresholds are breached.

    Args:
        window_size: Number of recent predictions to consider for accuracy.
        accuracy_threshold: Minimum acceptable accuracy (0.0–1.0).
        psi_threshold: Maximum acceptable PSI for any single feature.
        stale_hours: Hours without new predictions before a staleness alert.
        state_dir: Directory for persisting monitor state across restarts.
    """

    def __init__(
        self,
        window_size: int = 200,
        accuracy_threshold: float = 0.45,
        psi_threshold: float = 0.25,
        stale_hours: float = 4.0,
        state_dir: str | Path | None = None,
    ) -> None:
        self._window_size = window_size
        self._accuracy_threshold = accuracy_threshold
        self._psi_threshold = psi_threshold
        self._stale_hours = stale_hours
        self._state_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
        self._state_dir.mkdir(parents=True, exist_ok=True)

        # Rolling windows keyed by (model_version, symbol)
        self._predictions: dict[str, deque[PredictionRecord]] = {}
        self._feature_baselines: dict[str, dict[str, dict[str, float]]] = {}
        self._alerts: list[DriftAlert] = []
        self._last_prediction_time: dict[str, str] = {}

        self._load_state()
        logger.info(
            "drift_monitor_initialized",
            window_size=window_size,
            accuracy_threshold=accuracy_threshold,
            psi_threshold=psi_threshold,
        )

    # -- public API -----------------------------------------------------------

    def record_prediction(
        self,
        *,
        model_version: str,
        symbol: str,
        predicted_label: int,
        actual_label: int | None = None,
        confidence: float = 0.0,
        feature_snapshot: dict[str, float] | None = None,
    ) -> DriftAlert | None:
        """
        Record a prediction and optionally its outcome.

        When actual_label is provided, the monitor checks for accuracy drift.
        When feature_snapshot is provided, it updates feature baselines.

        Args:
            model_version: Version ID of the model that made the prediction.
            symbol: Trading symbol.
            predicted_label: The model's prediction.
            actual_label: The true label (None if outcome unknown).
            confidence: Prediction confidence score.
            feature_snapshot: Feature values at prediction time.

        Returns:
            DriftAlert if drift was detected, else None.
        """
        key = self._key(model_version, symbol)
        record = PredictionRecord(
            timestamp=datetime.now(UTC).isoformat(),
            model_version=model_version,
            symbol=symbol,
            predicted_label=predicted_label,
            actual_label=actual_label,
            confidence=confidence,
            feature_snapshot=feature_snapshot or {},
        )

        # Append to rolling window
        if key not in self._predictions:
            self._predictions[key] = deque(maxlen=self._window_size)
        self._predictions[key].append(record)
        self._last_prediction_time[key] = record.timestamp

        # Update feature baselines
        if feature_snapshot:
            self._update_feature_baseline(key, feature_snapshot)

        # Check for drift if we have an outcome
        alert = None
        if actual_label is not None:
            alert = self._check_accuracy_drift(key)

        self._save_state()
        return alert

    def check_drift(
        self,
        model_version: str,
        symbol: str,
    ) -> DriftReport:
        """
        Run a full drift check for a model/symbol combination.

        Evaluates accuracy over the current window, computes feature PSI
        scores, and returns a comprehensive report.

        Args:
            model_version: Model version to check.
            symbol: Trading symbol.

        Returns:
            DriftReport with current status and any active alerts.
        """
        key = self._key(model_version, symbol)
        window = self._predictions.get(key, deque())

        # Accuracy metrics
        resolved = [r for r in window if r.actual_label is not None]
        if resolved:
            correct = sum(1 for r in resolved if r.predicted_label == r.actual_label)
            accuracy = correct / len(resolved)
            trend = self._compute_accuracy_trend(resolved)
        else:
            accuracy = 0.0
            trend = "stable"

        # Feature drift
        psi_scores = self._compute_feature_psi(key)

        # Collect active alerts
        active_alerts = [a for a in self._alerts if a.model_version == model_version and a.symbol == symbol]

        # Check staleness
        stale_alert = self._check_staleness(model_version, symbol)
        if stale_alert:
            active_alerts.append(stale_alert)

        return DriftReport(
            model_version=model_version,
            symbol=symbol,
            total_predictions=len(window),
            accuracy_window=round(accuracy, 4),
            accuracy_trend=trend,
            feature_drift_scores=psi_scores,
            alerts=active_alerts,
        )

    def get_drift_stats(
        self,
        model_version: str | None = None,
        symbol: str | None = None,
    ) -> list[DriftReport]:
        """
        Get drift statistics across all or filtered model/symbol combinations.

        Args:
            model_version: Optional filter by model version.
            symbol: Optional filter by symbol.

        Returns:
            List of DriftReport objects.
        """
        keys = set(self._predictions.keys())
        if model_version and symbol:
            keys = {self._key(model_version, symbol)} & keys
        elif model_version:
            keys = {k for k in keys if k.startswith(model_version)}
        elif symbol:
            keys = {k for k in keys if k.endswith(f"|{symbol}")}

        reports: list[DriftReport] = []
        for key in sorted(keys):
            parts = key.split("|", 1)
            if len(parts) == 2:
                mv, sym = parts
                reports.append(self.check_drift(mv, sym))
        return reports

    def set_feature_baseline(
        self,
        model_version: str,
        symbol: str,
        feature_name: str,
        baseline_stats: dict[str, float],
    ) -> None:
        """
        Manually set the baseline distribution for a feature.

        Useful for bootstrapping baselines from training data statistics.

        Args:
            model_version: Model version.
            symbol: Trading symbol.
            feature_name: Feature to set baseline for.
            baseline_stats: Dict with keys like mean, std, p25, p50, p75.
        """
        key = self._key(model_version, symbol)
        if key not in self._feature_baselines:
            self._feature_baselines[key] = {}
        self._feature_baselines[key][feature_name] = baseline_stats
        self._save_state()
        logger.info(
            "feature_baseline_set",
            model_version=model_version,
            symbol=symbol,
            feature=feature_name,
        )

    def get_alerts(
        self,
        *,
        severity: str | None = None,
        model_version: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[DriftAlert]:
        """
        Retrieve recent alerts with optional filtering.

        Args:
            severity: Filter by severity level.
            model_version: Filter by model version.
            symbol: Filter by symbol.
            limit: Maximum number of alerts to return.

        Returns:
            List of matching DriftAlert objects, most recent first.
        """
        filtered = self._alerts
        if severity:
            filtered = [a for a in filtered if a.severity == severity]
        if model_version:
            filtered = [a for a in filtered if a.model_version == model_version]
        if symbol:
            filtered = [a for a in filtered if a.symbol == symbol]
        return sorted(filtered, key=lambda a: a.timestamp, reverse=True)[:limit]

    # -- private helpers ------------------------------------------------------

    def _key(self, model_version: str, symbol: str) -> str:
        return f"{model_version}|{symbol}"

    def _check_accuracy_drift(self, key: str) -> DriftAlert | None:
        """Check if accuracy has dropped below threshold."""
        window = self._predictions.get(key, deque())
        resolved = [r for r in window if r.actual_label is not None]

        if len(resolved) < 10:
            return None

        correct = sum(1 for r in resolved if r.predicted_label == r.actual_label)
        accuracy = correct / len(resolved)

        if accuracy < self._accuracy_threshold:
            parts = key.split("|", 1)
            mv, sym = parts[0], parts[1] if len(parts) > 1 else "unknown"
            severity = "critical" if accuracy < self._accuracy_threshold * 0.8 else "warning"
            alert = DriftAlert(
                alert_type="accuracy_drop",
                severity=severity,
                model_version=mv,
                symbol=sym,
                message=(
                    f"Accuracy {accuracy:.2%} below threshold "
                    f"{self._accuracy_threshold:.2%} over {len(resolved)} samples"
                ),
                metric_name="accuracy",
                current_value=round(accuracy, 4),
                threshold=self._accuracy_threshold,
            )
            self._alerts.append(alert)
            logger.warning(
                "accuracy_drift_detected",
                model_version=mv,
                symbol=sym,
                accuracy=accuracy,
                threshold=self._accuracy_threshold,
            )
            return alert
        return None

    def _check_staleness(self, model_version: str, symbol: str) -> DriftAlert | None:
        """Check if predictions have stopped flowing."""
        key = self._key(model_version, symbol)
        last_ts = self._last_prediction_time.get(key)
        if not last_ts:
            return None
        try:
            last = datetime.fromisoformat(last_ts)
            elapsed = datetime.now(UTC) - last
            if elapsed.total_seconds() / 3600 > self._stale_hours:
                return DriftAlert(
                    alert_type="stale_model",
                    severity="warning",
                    model_version=model_version,
                    symbol=symbol,
                    message=(
                        f"No predictions for {elapsed.total_seconds() / 3600:.1f}h "
                        f"(threshold: {self._stale_hours}h)"
                    ),
                    metric_name="prediction_staleness_hours",
                    current_value=round(elapsed.total_seconds() / 3600, 2),
                    threshold=self._stale_hours,
                )
        except (ValueError, TypeError):
            pass
        return None

    def _compute_accuracy_trend(self, resolved: list[PredictionRecord], split: int = 50) -> str:
        """Compare accuracy of recent vs older predictions."""
        if len(resolved) < split * 2:
            return "stable"
        recent = resolved[-split:]
        older = resolved[-split * 2 : -split]

        acc_recent = sum(1 for r in recent if r.predicted_label == r.actual_label) / len(recent)
        acc_older = sum(1 for r in older if r.predicted_label == r.actual_label) / len(older)

        diff = acc_recent - acc_older
        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "degrading"
        return "stable"

    def _update_feature_baseline(self, key: str, features: dict[str, float]) -> None:
        """Incrementally update feature distribution baselines."""
        if key not in self._feature_baselines:
            self._feature_baselines[key] = {}

        for fname, fval in features.items():
            if fname not in self._feature_baselines[key]:
                self._feature_baselines[key][fname] = {
                    "sum": 0.0,
                    "sum_sq": 0.0,
                    "count": 0.0,
                    "min": float("inf"),
                    "max": float("-inf"),
                }
            stats = self._feature_baselines[key][fname]
            stats["sum"] += fval
            stats["sum_sq"] += fval**2
            stats["count"] += 1
            stats["min"] = min(stats["min"], fval)
            stats["max"] = max(stats["max"], fval)

    def _compute_feature_psi(self, key: str) -> dict[str, float]:
        """
        Compute Population Stability Index (PSI) for each tracked feature.

        PSI measures how much a feature's distribution has shifted from baseline.
        PSI < 0.1: no significant change
        PSI 0.1–0.25: moderate change
        PSI > 0.25: significant change
        """
        baselines = self._feature_baselines.get(key, {})
        window = self._predictions.get(key, deque())

        if not baselines or not window:
            return {}

        psi_scores: dict[str, float] = {}
        for fname, baseline in baselines.items():
            count = baseline.get("count", 0)
            if count < 2:
                continue

            b_mean = baseline["sum"] / count
            b_std = math.sqrt(max(baseline["sum_sq"] / count - b_mean**2, 1e-10))

            # Gather current window values for this feature
            current_vals = [r.feature_snapshot[fname] for r in window if fname in r.feature_snapshot]
            if len(current_vals) < 5:
                continue

            c_mean = sum(current_vals) / len(current_vals)
            c_std = math.sqrt(sum((v - c_mean) ** 2 for v in current_vals) / len(current_vals))
            c_std = max(c_std, 1e-10)

            # PSI via bin-based approach
            psi = self._calculate_psi(
                baseline_mean=b_mean,
                baseline_std=b_std,
                current_mean=c_mean,
                current_std=c_std,
                n_bins=10,
            )
            psi_scores[fname] = round(psi, 6)

            if psi > self._psi_threshold:
                parts = key.split("|", 1)
                mv, sym = parts[0], parts[1] if len(parts) > 1 else "unknown"
                severity = "critical" if psi > self._psi_threshold * 1.5 else "warning"
                alert = DriftAlert(
                    alert_type="feature_drift",
                    severity=severity,
                    model_version=mv,
                    symbol=sym,
                    message=f"Feature '{fname}' PSI={psi:.4f} exceeds threshold {self._psi_threshold}",
                    metric_name=f"psi_{fname}",
                    current_value=round(psi, 6),
                    threshold=self._psi_threshold,
                )
                self._alerts.append(alert)
                logger.warning(
                    "feature_drift_detected",
                    model_version=mv,
                    symbol=sym,
                    feature=fname,
                    psi=psi,
                )

        return psi_scores

    @staticmethod
    def _calculate_psi(
        *,
        baseline_mean: float,
        baseline_std: float,
        current_mean: float,
        current_std: float,
        n_bins: int = 10,
    ) -> float:
        """
        Compute PSI between two normal distributions approximated by bins.

        Uses baseline mean/std to define bins, then computes the divergence
        between the baseline and current distributions.
        """
        # Define bin edges from baseline distribution
        lo = baseline_mean - 3 * baseline_std
        hi = baseline_mean + 3 * baseline_std
        edges = [lo + (hi - lo) * i / n_bins for i in range(n_bins + 1)]

        def _normal_cdf(x: float, mu: float, sigma: float) -> float:
            """Approximate normal CDF using error function."""
            return 0.5 * (1 + math.erf((x - mu) / (sigma * math.sqrt(2))))

        def _bin_probs(mu: float, sigma: float) -> list[float]:
            probs = []
            for i in range(n_bins):
                p = _normal_cdf(edges[i + 1], mu, sigma) - _normal_cdf(edges[i], mu, sigma)
                probs.append(max(p, 1e-10))
            return probs

        baseline_probs = _bin_probs(baseline_mean, baseline_std)
        current_probs = _bin_probs(current_mean, current_std)

        psi = 0.0
        for bp, cp in zip(baseline_probs, current_probs, strict=False):
            psi += (cp - bp) * math.log(cp / bp)
        return psi

    # -- state persistence ----------------------------------------------------

    def _save_state(self) -> None:
        """Persist monitor state to disk."""
        # Save predictions to DuckDB for persistence across restarts
        try:
            import duckdb

            db_path = os.getenv("DUCKDB_PATH", "data/market_data.duckdb")
            con = duckdb.connect(db_path, read_only=False)
            con.execute("""
                CREATE TABLE IF NOT EXISTS drift_predictions (
                    key VARCHAR,
                    timestamp VARCHAR,
                    model_version VARCHAR,
                    symbol VARCHAR,
                    predicted_label INTEGER,
                    actual_label INTEGER,
                    confidence DOUBLE
                )
            """)
            # Clear old predictions and insert current window
            for key, window in self._predictions.items():
                parts = key.split("|", 1)
                mv, sym = parts[0], parts[1] if len(parts) > 1 else "unknown"
                for r in window:
                    con.execute(
                        "INSERT INTO drift_predictions VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [key, r.timestamp, r.model_version, r.symbol, r.predicted_label, r.actual_label, r.confidence],
                    )
            con.close()
        except Exception as e:
            logger.warning("drift_state_persist_failed", error=str(e))

        # Also save lightweight JSON for quick reload
        state = {
            "last_prediction_time": self._last_prediction_time,
            "alerts_count": len(self._alerts),
            "saved_at": datetime.now(UTC).isoformat(),
        }
        state_path = self._state_dir / "drift_monitor_state.json"
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

    def _load_state(self) -> None:
        """Load monitor state from disk."""
        state_path = self._state_dir / "drift_monitor_state.json"
        if not state_path.exists():
            return
        try:
            with open(state_path) as f:
                state = json.load(f)
            self._last_prediction_time = state.get("last_prediction_time", {})
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("drift_state_load_failed", error=str(exc))
