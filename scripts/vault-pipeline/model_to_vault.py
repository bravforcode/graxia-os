"""
model_to_vault.py - Convert trained ML model .pkl files to Obsidian vault notes.

Extracts metadata from quant_os pickle files and generates vault-compatible
markdown with YAML frontmatter for the Model Registry pipeline.

Usage:
    python model_to_vault.py                          # Scan all models
    python model_to_vault.py --model-dir ./ml/models  # Custom model dir
    python model_to_vault.py --output-dir ./vault_out # Custom output dir
    python model_to_vault.py --dry-run                # Preview only
"""

import os
import sys
import pickle
import argparse
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


@dataclass
class ModelMetadata:
    """Extracted model metadata for vault note generation."""

    model_name: str
    version: str
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    oos_accuracy: float = 0.0
    feature_importance: Dict[str, float] = field(default_factory=dict)
    feature_list: List[str] = field(default_factory=list)
    trained_at: str = ""
    model_path: str = ""
    model_type: str = ""
    training_samples: int = 0
    file_hash: str = ""

    def to_frontmatter(self) -> str:
        """Generate YAML frontmatter block."""
        fi_top10 = dict(
            sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True)[
                :10
            ]
        )

        fi_lines = "\n".join(f"  {name}: {val:.4f}" for name, val in fi_top10.items())
        fi_block = (
            f"feature_importance_top10:\n{fi_lines}"
            if fi_lines
            else "feature_importance_top10: []"
        )

        return f"""---
type: ml-model
model_name: "{self.model_name}"
version: "{self.version}"
accuracy: {self.accuracy:.4f}
precision: {self.precision:.4f}
recall: {self.recall:.4f}
f1_score: {self.f1_score:.4f}
oos_accuracy: {self.oos_accuracy:.4f}
trained_date: "{self.trained_at}"
model_type: "{self.model_type}"
training_samples: {self.training_samples}
model_path: "{self.model_path}"
file_hash: "{self.file_hash}"
{fi_block}
feature_count: {len(self.feature_list)}
tags:
  - ml-model
  - {self.model_name}
  - trading
---"""

    def to_markdown(self) -> str:
        """Generate full vault note markdown."""
        frontmatter = self.to_frontmatter()

        fi_top10 = sorted(
            self.feature_importance.items(), key=lambda x: x[1], reverse=True
        )[:10]

        fi_table = "| Rank | Feature | Importance |"
        fi_table += "\n|------|---------|------------|"
        for i, (name, val) in enumerate(fi_top10, 1):
            bar = "█" * int(val * 100) if val > 0 else ""
            fi_table += f"\n| {i} | `{name}` | {val:.4f} {bar} |"

        metrics_section = f"""## Metrics

| Metric | Value |
|--------|-------|
| Accuracy | {self.accuracy:.4f} |
| Precision | {self.precision:.4f} |
| Recall | {self.recall:.4f} |
| F1 Score | {self.f1_score:.4f} |
| OOS Accuracy | {self.oos_accuracy:.4f} |
| Training Samples | {self.training_samples:,} |"""

        feature_section = f"""## Top 10 Feature Importance

{fi_table}"""

        details_section = f"""## Details

- **Model Type:** {self.model_type}
- **Trained:** {self.trained_at}
- **Version:** `{self.version}`
- **Total Features:** {len(self.feature_list)}
- **File Hash:** `{self.file_hash[:12]}...`
- **Source:** `{self.model_path}`"""

        return f"""{frontmatter}

# {self.model_name} — {self.version}

> ML model trained on `{self.model_type}` for `{self.model_name}` signal prediction.

{metrics_section}

{feature_section}

{details_section}
"""


def load_model_metadata(pkl_path: str) -> Optional[ModelMetadata]:
    """Load and extract metadata from a .pkl model file.

    Handles both formats:
    1. Raw dict with 'model', 'feature_names', 'model_type', 'version'
    2. ModelResult dataclass (if quant_os is importable)
    """
    try:
        with open(pkl_path, "rb") as f:
            data = pickle.load(f)
    except Exception as e:
        print(f"  [WARN] Failed to load {pkl_path}: {e}")
        return None

    filename = os.path.basename(pkl_path)
    file_hash = hashlib.md5(open(pkl_path, "rb").read()).hexdigest()

    # Format 1: Raw dict from MLTrainer.train()
    if isinstance(data, dict):
        model_type = data.get("model_type", "unknown")
        version = data.get("version", extract_version_from_filename(filename))
        feature_names = data.get("feature_names", [])
        model_name = extract_model_name_from_filename(filename)

        # Try to extract accuracy from model if available
        model_obj = data.get("model")
        accuracy = 0.0
        if model_obj and hasattr(model_obj, "get_params"):
            # Can't recover accuracy from a trained model alone
            pass

        return ModelMetadata(
            model_name=model_name,
            version=version,
            accuracy=accuracy,
            feature_list=feature_names,
            trained_at=parse_version_to_date(version),
            model_path=pkl_path,
            model_type=model_type,
            file_hash=file_hash,
        )

    # Format 2: ModelResult dataclass
    if hasattr(data, "model_name") and hasattr(data, "version"):
        return ModelMetadata(
            model_name=data.model_name,
            version=data.version,
            accuracy=getattr(data, "accuracy", 0.0),
            precision=getattr(data, "precision", 0.0),
            recall=getattr(data, "recall", 0.0),
            f1_score=getattr(data, "f1_score", 0.0),
            oos_accuracy=getattr(data, "oos_accuracy", 0.0),
            feature_importance=getattr(data, "feature_importance", {}),
            feature_list=getattr(data, "feature_list", []),
            trained_at=str(getattr(data, "trained_at", "")),
            model_path=getattr(data, "model_path", pkl_path),
            model_type=data.model_name,
            training_samples=getattr(data, "training_samples", 0),
            file_hash=file_hash,
        )

    # Format 3: Raw XGBClassifier / LGBMClassifier / sklearn model
    if hasattr(data, "get_params") and hasattr(data, "predict"):
        model_type = type(data).__name__
        # Try to recover feature names from booster if available
        feature_names = []
        try:
            if hasattr(data, "get_booster"):
                booster = data.get_booster()
                feature_names = booster.feature_names or []
        except Exception:
            pass

        return ModelMetadata(
            model_name=extract_model_name_from_filename(filename),
            version=extract_version_from_filename(filename),
            model_path=pkl_path,
            trained_at=parse_version_to_date(extract_version_from_filename(filename)),
            model_type=model_type,
            feature_list=feature_names,
            file_hash=file_hash,
        )

    # Format 4: Unknown structure — extract what we can
    print(f"  [WARN] Unknown pickle format in {filename}, using filename metadata only")
    return ModelMetadata(
        model_name=extract_model_name_from_filename(filename),
        version=extract_version_from_filename(filename),
        model_path=pkl_path,
        trained_at=parse_version_to_date(extract_version_from_filename(filename)),
        file_hash=file_hash,
    )


def extract_version_from_filename(filename: str) -> str:
    """Extract version timestamp from filename like xgboost_XAUUSD_20260626_160329.pkl"""
    stem = filename.replace(".pkl", "")
    parts = stem.split("_")
    # Last two parts are typically date_time
    if len(parts) >= 2:
        date_part = parts[-2]
        time_part = parts[-1]
        if (
            len(date_part) == 8
            and date_part.isdigit()
            and len(time_part) == 6
            and time_part.isdigit()
        ):
            return f"{date_part}_{time_part}"
        # Fallback: just date as version (e.g. xgboost_live_20260626.pkl)
        if len(time_part) == 8 and time_part.isdigit():
            return time_part
    return stem


def extract_model_name_from_filename(filename: str) -> str:
    """Extract model/symbol name from filename."""
    stem = filename.replace(".pkl", "")
    parts = stem.split("_")
    if len(parts) >= 3:
        # e.g. xgboost_XAUUSD_20260626_160329 -> XAUUSD
        # e.g. xgboost_live_20260626_175431 -> live
        return "_".join(parts[1:-2])
    return parts[0] if parts else "unknown"


def parse_version_to_date(version: str) -> str:
    """Parse version string like 20260626_160329 to readable date."""
    try:
        date_part, time_part = version.split("_")
        return f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
    except (ValueError, IndexError):
        return version


def generate_index_note(model_notes: List[Dict[str, str]], output_dir: str) -> str:
    """Generate Index.md listing all model notes."""
    rows = []
    for m in sorted(model_notes, key=lambda x: x["version"], reverse=True):
        quality = _quality_badge(m["accuracy"])
        rows.append(
            f"| [[{m['note_name']}]] | {m['model_name']} | {m['version']} | "
            f"{m['accuracy']:.4f} | {m['f1_score']:.4f} | {quality} |"
        )

    table = "| Note | Model | Version | Accuracy | F1 | Quality |"
    table += "\n|------|-------|---------|----------|-----|---------|"
    table += (
        "\n" + "\n".join(rows) if rows else "\n| - | No models found | - | - | - | - |"
    )

    return f"""---
type: ml-model-index
generated: "{datetime.utcnow().isoformat()}Z"
tags:
  - ml-model
  - registry
  - trading
---

# ML Model Registry

> Auto-generated index of all trained models in the quant_os pipeline.

## Models

{table}

## Pipeline Info

- **Source:** `graxia/packages/quant_os/ml/models/`
- **Pipeline:** `quant_os/ml/pipeline.py`
- **Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC

## Quick Stats

- **Total Models:** {len(model_notes)}
- **Best Accuracy:** {max((m['accuracy'] for m in model_notes), default=0):.4f}
- **Best F1:** {max((m['f1_score'] for m in model_notes), default=0):.4f}
"""


def _quality_badge(accuracy: float) -> str:
    """Return quality badge based on accuracy."""
    if accuracy >= 0.7:
        return "🟢 Excellent"
    elif accuracy >= 0.6:
        return "🟡 Good"
    elif accuracy >= 0.5:
        return "🟠 Fair"
    else:
        return "🔴 Poor"


def main():
    parser = argparse.ArgumentParser(description="Convert ML models to vault notes")
    parser.add_argument(
        "--model-dir",
        default=r"C:\Users\menum\graxia os\graxia\packages\quant_os\ml\models",
        help="Directory containing .pkl model files",
    )
    parser.add_argument(
        "--output-dir",
        default=r"C:\Users\menum\Documents\ObsidianVault\Second Brain\03-resources\trading\models",
        help="Output directory for vault notes",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview only, don't write files"
    )
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    output_dir = Path(args.output_dir)

    if not model_dir.exists():
        print(f"ERROR: Model directory not found: {model_dir}")
        sys.exit(1)

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    pkl_files = sorted(model_dir.glob("*.pkl"))
    if not pkl_files:
        print(f"No .pkl files found in {model_dir}")
        sys.exit(0)

    print(f"Found {len(pkl_files)} model files")
    print(f"Output: {output_dir}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'WRITE'}")
    print("-" * 60)

    model_notes = []
    success = 0
    errors = 0

    for pkl_path in pkl_files:
        filename = pkl_path.name
        print(f"\nProcessing: {filename}")

        metadata = load_model_metadata(str(pkl_path))
        if metadata is None:
            errors += 1
            continue

        note_name = f"{metadata.model_name}_{metadata.version}"
        note_path = output_dir / f"{note_name}.md"

        print(f"  Model: {metadata.model_name} v{metadata.version}")
        print(f"  Accuracy: {metadata.accuracy:.4f} | F1: {metadata.f1_score:.4f}")
        print(f"  Features: {len(metadata.feature_list)}")
        print(f"  Note: {note_path}")

        if not args.dry_run:
            note_content = metadata.to_markdown()
            note_path.write_text(note_content, encoding="utf-8")
            print("  [OK] Written")

        model_notes.append(
            {
                "note_name": note_name,
                "model_name": metadata.model_name,
                "version": metadata.version,
                "accuracy": metadata.accuracy,
                "f1_score": metadata.f1_score,
                "note_path": str(note_path),
            }
        )
        success += 1

    print("\n" + "=" * 60)
    print(f"Processed: {success} | Errors: {errors} | Total: {len(pkl_files)}")

    if model_notes and not args.dry_run:
        index_content = generate_index_note(model_notes, str(output_dir))
        index_path = output_dir / "Index.md"
        index_path.write_text(index_content, encoding="utf-8")
        print(f"[OK] Index written: {index_path}")
    elif model_notes and args.dry_run:
        print("[DRY RUN] Index.md would be generated")
        try:
            print(generate_index_note(model_notes, str(output_dir)))
        except UnicodeEncodeError:
            # Windows console can't render emoji — print safe version
            safe_index = generate_index_note(model_notes, str(output_dir))
            print(safe_index.encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
