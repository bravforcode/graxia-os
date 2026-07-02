"""
Model Registry — Versioning, metadata tracking, and model management for ML models.

Stores model metadata as JSON alongside .pkl files in ml/models/.
Provides register, retrieve, compare, and list capabilities with
immutable version IDs and full audit trails.
"""

import json
import os
import pickle
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_MODELS_DIR = Path(__file__).parent / "models"


@dataclass(frozen=True)
class ModelMetadata:
    """Immutable snapshot of a registered model's metadata."""

    version_id: str
    model_name: str
    model_type: str
    symbol: str
    timeframe: str
    feature_list: list[str]
    metrics: dict[str, float]
    training_samples: int
    registered_at: str
    registered_by: str = "auto"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    parent_version: str = ""
    artifact_path: str = ""
    random_seed: int = 42
    feature_list_hash: str = ""
    dataset_manifest_hash: str = ""
    hyperparams: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelComparison:
    """Side-by-side comparison of two model versions."""

    model_a: ModelMetadata
    model_b: ModelMetadata
    metric_delta: dict[str, float]
    winner: str  # version_id of the better model
    comparison_timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


class ModelRegistry:
    """
    Model versioning and metadata tracking.

    Each registered model receives a unique version ID and a JSON metadata
    file alongside its .pkl artifact. The registry provides lookup, listing,
    and comparison operations.

    Args:
        models_dir: Directory where model artifacts and metadata are stored.
    """

    def __init__(self, models_dir: str | Path | None = None) -> None:
        self._models_dir = Path(models_dir) if models_dir else DEFAULT_MODELS_DIR
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._models_dir / "registry_index.json"
        self._index: dict[str, dict[str, Any]] = self._load_index()
        logger.info(
            "model_registry_initialized",
            models_dir=str(self._models_dir),
            registered_count=len(self._index),
        )

    # -- public API -----------------------------------------------------------

    def register_model(
        self,
        model: Any,
        *,
        model_name: str,
        model_type: str,
        symbol: str,
        timeframe: str,
        feature_list: list[str],
        metrics: dict[str, float],
        training_samples: int,
        description: str = "",
        tags: list[str] | None = None,
        parent_version: str = "",
        random_seed: int = 42,
        feature_list_hash: str = "",
        dataset_manifest_hash: str = "",
        hyperparams: dict[str, Any] | None = None,
    ) -> ModelMetadata:
        """
        Register a trained model artifact.

        Saves the .pkl file and a JSON metadata sidecar. Returns the
        created ModelMetadata for downstream reference.

        Args:
            model: Picklable model object (XGBoost, LightGBM, etc.).
            model_name: Human-readable name (e.g. "xgboost_XAUUSD").
            model_type: Algorithm identifier (e.g. "xgboost", "lightgbm").
            symbol: Trading symbol the model was trained on.
            timeframe: Bar timeframe (e.g. "M15", "H1").
            feature_list: Ordered list of feature names used during training.
            metrics: Evaluation metrics (accuracy, f1, precision, recall, etc.).
            training_samples: Number of samples used in training.
            description: Free-text description.
            tags: Optional tags for filtering (e.g. ["live", "production"]).
            parent_version: Version ID this model was trained from (if any).

        Returns:
            ModelMetadata of the newly registered model.
        """
        version_id = self._generate_version_id(model_name)
        timestamp = datetime.now(UTC).isoformat()
        artifact_filename = f"{version_id}.pkl"
        artifact_path = self._models_dir / artifact_filename
        metadata_path = self._models_dir / f"{version_id}.json"

        # Save artifact
        with open(artifact_path, "wb") as f:
            pickle.dump(model, f)

        # Build metadata
        metadata = ModelMetadata(
            version_id=version_id,
            model_name=model_name,
            model_type=model_type,
            symbol=symbol,
            timeframe=timeframe,
            feature_list=feature_list,
            metrics=metrics,
            training_samples=training_samples,
            registered_at=timestamp,
            description=description,
            tags=tags or [],
            parent_version=parent_version,
            artifact_path=str(artifact_path),
            random_seed=random_seed,
            feature_list_hash=feature_list_hash,
            dataset_manifest_hash=dataset_manifest_hash,
            hyperparams=hyperparams or {},
        )

        # Save metadata sidecar
        with open(metadata_path, "w") as f:
            json.dump(asdict(metadata), f, indent=2, default=str)

        # Update index
        self._index[version_id] = asdict(metadata)
        self._save_index()

        logger.info(
            "model_registered",
            version_id=version_id,
            model_name=model_name,
            symbol=symbol,
            metrics=metrics,
        )
        return metadata

    def get_latest_model(
        self,
        *,
        model_name: str | None = None,
        symbol: str | None = None,
        tag: str | None = None,
    ) -> ModelMetadata | None:
        """
        Retrieve the most recently registered model matching optional filters.

        Args:
            model_name: Filter by model name prefix.
            symbol: Filter by trading symbol.
            tag: Filter by tag.

        Returns:
            Latest matching ModelMetadata, or None if no match.
        """
        candidates = self.list_models(
            model_name=model_name, symbol=symbol, tag=tag
        )
        if not candidates:
            logger.warning("no_models_found", model_name=model_name, symbol=symbol)
            return None
        latest = candidates[-1]  # sorted by registration time ascending
        logger.debug(
            "latest_model_retrieved",
            version_id=latest.version_id,
            model_name=latest.model_name,
        )
        return latest

    def get_model(self, version_id: str) -> ModelMetadata | None:
        """
        Retrieve metadata for a specific version.

        Args:
            version_id: The unique version identifier.

        Returns:
            ModelMetadata if found, else None.
        """
        if version_id not in self._index:
            logger.warning("model_not_found", version_id=version_id)
            return None
        return ModelMetadata(**self._index[version_id])

    def load_model(self, version_id: str) -> Any:
        """
        Load the pickled model artifact for a given version.

        Args:
            version_id: The unique version identifier.

        Returns:
            The deserialized model object.

        Raises:
            FileNotFoundError: If the artifact file is missing.
            KeyError: If the version_id is not in the registry.
        """
        if version_id not in self._index:
            raise KeyError(f"Version '{version_id}' not found in registry")
        artifact_path = self._index[version_id]["artifact_path"]
        if not os.path.exists(artifact_path):
            raise FileNotFoundError(f"Artifact missing: {artifact_path}")
        with open(artifact_path, "rb") as f:
            model = pickle.load(f)  # noqa: S301
        logger.debug("model_loaded", version_id=version_id)
        return model

    def compare_models(
        self, version_a: str, version_b: str
    ) -> ModelComparison:
        """
        Compare two registered models by their stored metrics.

        Determines a winner based on F1 score (tie-broken by accuracy).

        Args:
            version_a: First version ID.
            version_b: Second version ID.

        Returns:
            ModelComparison with metric deltas and winner.

        Raises:
            KeyError: If either version is not in the registry.
        """
        meta_a = self.get_model(version_a)
        meta_b = self.get_model(version_b)
        if meta_a is None:
            raise KeyError(f"Version '{version_a}' not found")
        if meta_b is None:
            raise KeyError(f"Version '{version_b}' not found")

        # Compute delta: B minus A
        all_keys = set(meta_a.metrics.keys()) | set(meta_b.metrics.keys())
        delta: dict[str, float] = {}
        for key in all_keys:
            val_a = meta_a.metrics.get(key, 0.0)
            val_b = meta_b.metrics.get(key, 0.0)
            delta[key] = round(val_b - val_a, 6)

        # Winner = higher F1 (tie-break accuracy)
        f1_a = meta_a.metrics.get("f1_score", 0.0)
        f1_b = meta_b.metrics.get("f1_score", 0.0)
        if f1_b > f1_a:
            winner = version_b
        elif f1_b < f1_a:
            winner = version_a
        else:
            acc_a = meta_a.metrics.get("accuracy", 0.0)
            acc_b = meta_b.metrics.get("accuracy", 0.0)
            winner = version_b if acc_b >= acc_a else version_a

        comparison = ModelComparison(
            model_a=meta_a,
            model_b=meta_b,
            metric_delta=delta,
            winner=winner,
        )

        logger.info(
            "models_compared",
            version_a=version_a,
            version_b=version_b,
            winner=winner,
            delta=delta,
        )
        return comparison

    def list_models(
        self,
        *,
        model_name: str | None = None,
        symbol: str | None = None,
        tag: str | None = None,
    ) -> list[ModelMetadata]:
        """
        List all registered models, optionally filtered.

        Results are sorted by registration time (ascending).

        Args:
            model_name: Filter by model name prefix match.
            symbol: Filter by exact symbol match.
            tag: Filter by tag membership.

        Returns:
            List of matching ModelMetadata objects.
        """
        results: list[ModelMetadata] = []
        for meta_dict in self._index.values():
            if model_name and not meta_dict["model_name"].startswith(model_name):
                continue
            if symbol and meta_dict["symbol"] != symbol:
                continue
            if tag and tag not in meta_dict.get("tags", []):
                continue
            results.append(ModelMetadata(**meta_dict))
        results.sort(key=lambda m: m.registered_at)
        return results

    def delete_model(self, version_id: str) -> bool:
        """
        Remove a model from the registry and delete its artifacts.

        Args:
            version_id: The version to delete.

        Returns:
            True if deleted, False if not found.
        """
        if version_id not in self._index:
            return False
        meta = self._index[version_id]
        # Remove artifact
        artifact_path = Path(meta["artifact_path"])
        if artifact_path.exists():
            artifact_path.unlink()
        # Remove metadata sidecar
        metadata_path = self._models_dir / f"{version_id}.json"
        if metadata_path.exists():
            metadata_path.unlink()
        # Remove from index
        del self._index[version_id]
        self._save_index()
        logger.info("model_deleted", version_id=version_id)
        return True

    # -- private helpers ------------------------------------------------------

    def _generate_version_id(self, model_name: str) -> str:
        """Generate a unique version ID: {model_name}_{timestamp}_{short_uuid}."""
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:8]
        return f"{model_name}_{ts}_{short_uuid}"

    def _load_index(self) -> dict[str, dict[str, Any]]:
        """Load the registry index from disk."""
        if not self._index_path.exists():
            return {}
        try:
            with open(self._index_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("registry_index_corrupt", error=str(exc))
            return {}

    def _save_index(self) -> None:
        """Persist the registry index to disk."""
        with open(self._index_path, "w") as f:
            json.dump(self._index, f, indent=2, default=str)
