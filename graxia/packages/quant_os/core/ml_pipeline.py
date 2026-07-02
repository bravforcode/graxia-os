"""ML Pipeline from Jesse pattern - gather, train, deploy"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class MLDataPoint:
    """Single ML training data point"""

    timestamp: float
    features: dict[str, float]
    label: float | None = None
    label_name: str = ""


class MLPipeline:
    """
    ML Pipeline: gather → train → deploy

    Usage:
        pipeline = MLPipeline()

        # During backtest - gather data
        pipeline.gather_start()
        pipeline.record_features({"rsi": 65.0, "atr": 0.5})
        # ... later ...
        pipeline.record_label("direction", 1.0)
        pipeline.gather_end()

        # Export for training
        pipeline.export_csv("training_data.csv")

        # Train (external)
        # pipeline.train_model("model.pkl")

        # During live trading - deploy
        prediction = pipeline.predict("model.pkl", {"rsi": 65.0, "atr": 0.5})
    """

    def __init__(self):
        self._data_points: list[MLDataPoint] = []
        self._current_point: MLDataPoint | None = None
        self._model = None
        self._scaler = None
        self._feature_names: list[str] = []

    def gather_start(self):
        """Start gathering ML data"""
        self._current_point = MLDataPoint(timestamp=datetime.utcnow().timestamp(), features={})

    def record_features(self, features: dict[str, float]):
        """Record features for current data point"""
        if self._current_point is None:
            self.gather_start()
        self._current_point.features.update(features)

    def record_label(self, name: str, value: float):
        """Record label (outcome) and save data point"""
        if self._current_point is not None:
            self._current_point.label = value
            self._current_point.label_name = name
            self._data_points.append(self._current_point)
            self._current_point = None

    def gather_end(self):
        """End gathering, discard incomplete point"""
        self._current_point = None

    def export_csv(self, filepath: str):
        """Export gathered data to CSV"""
        if not self._data_points:
            return

        # Get all feature names
        all_features = set()
        for dp in self._data_points:
            all_features.update(dp.features.keys())
        self._feature_names = sorted(all_features)

        with open(filepath, "w") as f:
            # Header
            header = ["timestamp", "label_name", "label"] + self._feature_names
            f.write(",".join(header) + "\n")

            # Rows
            for dp in self._data_points:
                row = [
                    str(dp.timestamp),
                    dp.label_name,
                    str(dp.label or ""),
                ]
                for feat in self._feature_names:
                    row.append(str(dp.features.get(feat, "")))
                f.write(",".join(row) + "\n")

    def import_csv(self, filepath: str):
        """Import training data from CSV"""
        self._data_points = []
        with open(filepath) as f:
            lines = f.readlines()

        if len(lines) < 2:
            return

        header = lines[0].strip().split(",")
        feat_start = header.index("label") + 1
        self._feature_names = header[feat_start:]

        for line in lines[1:]:
            parts = line.strip().split(",")
            if len(parts) < feat_start + 1:
                continue

            features = {}
            for i, feat in enumerate(self._feature_names):
                if feat_start + i < len(parts) and parts[feat_start + i]:
                    features[feat] = float(parts[feat_start + i])

            dp = MLDataPoint(
                timestamp=float(parts[0]),
                features=features,
                label=float(parts[2]) if parts[2] else None,
                label_name=parts[1],
            )
            self._data_points.append(dp)

    def prepare_training_data(self, test_ratio: float = 0.2):
        """Prepare data for training with chronological train/test split"""
        sorted_data = sorted(self._data_points, key=lambda p: p.timestamp)

        X = []
        y = []
        for dp in sorted_data:
            if dp.label is not None:
                X.append([dp.features.get(f, 0) for f in self._feature_names])
                y.append(dp.label)

        split_idx = int(len(X) * (1 - test_ratio))
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        return X_train, X_test, y_train, y_test

    def fit_scaler(self, X):
        """Fit StandardScaler on training data and store state.

        CRITICAL: Call ONLY on training data. Fitting on test data = data leakage.
        """
        from sklearn.preprocessing import StandardScaler

        self._scaler = StandardScaler()
        self._scaler.fit(X)
        return self._scaler

    def transform(self, X):
        """Transform data using fitted scaler"""
        if self._scaler is None:
            return X
        return self._scaler.transform(X)

    def prepare_and_scale(self, test_ratio: float = 0.2):
        """
        Prepare training data with proper chronological split AND scaling.

        CRITICAL: Scaler is fit ONLY on training data, then applied to both.
        This prevents data leakage from test set into training.
        """
        X_train, X_test, y_train, y_test = self.prepare_training_data(test_ratio)

        # Fit scaler on TRAINING data only
        self.fit_scaler(X_train)

        # Transform both train and test with the SAME scaler
        X_train_scaled = self.transform(X_train)
        X_test_scaled = self.transform(X_test)

        return X_train_scaled, X_test_scaled, y_train, y_test

    @property
    def data_count(self) -> int:
        return len(self._data_points)

    @property
    def feature_names(self) -> list[str]:
        return self._feature_names
