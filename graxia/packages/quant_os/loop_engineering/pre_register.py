"""
pre_register.py — Pre-registration contract for Loop Engineering (quant_os).

Implements Spec Part 1/2.1/4: a hypothesis MUST be pre-registered with FIXED
GO/REJECT thresholds and (optionally) LOCKED Optuna parameter ranges BEFORE any
prospective data is seen. The dataclass is frozen: thresholds cannot be mutated
mid-run (Spec Part 2.1, Part 5 "ห้ามเปลี่ยน GO/REJECT threshold ระหว่าง loop กำลังรัน").

If Optuna tuning is requested (Spec Part 4), the parameter search space MUST be
declared here, up-front, so the range is locked before results are observed.
This is rule #1 of Spec Part 4 ("Optuna optimize ได้เฉพาะภายใน 1 pre-registered
hypothesis เท่านั้น — parameter range ต้องถูกล็อกไว้ก่อนเห็นผล").
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Pre-registration files MUST live under one of these directories. This prevents
# an agent from "loading" a freshly-written file with looser bounds placed
# elsewhere and satisfying the optimizer's source_path gate while bypassing the
# intent (bounds locked before any backtest, tied to the one committed file).
_ALLOWED_ROOTS = (
    Path(__file__).resolve().parent.parent / "Meta",
    Path(__file__).resolve().parent.parent / "research",
)


def _is_contained(path: Path, root: Path) -> bool:
    """True iff `path` is `root` or lives inside `root` (no `..` escape)."""
    path, root = path.resolve(), root.resolve()
    return path == root or root in path.parents


# Fixed, non-negotiable defaults from the governance history of this project.
# These match the GO criteria used throughout the research program
# (dk_t > 2.0 AND positive_sharpe_count >= 5) and the label-shuffle / min-trades
# gates that prevented p-hacking in prior audits.
DEFAULT_DK_T_THRESHOLD = 2.0
DEFAULT_MIN_POSITIVE_SHARPE = 5
DEFAULT_LABEL_SHUFFLE_ALPHA = 0.05
DEFAULT_MIN_TRADES = 100


@dataclass(frozen=True)
class PreRegistration:
    """Immutable pre-registration. Frozen => no mid-run threshold mutation.

    `optuna_param_ranges` is the LOCKED search space. It must be provided up-front
    (before any backtest) whenever `optuna_max_trials > 0`. The loop's optimizer
    refuses to run otherwise (Spec Part 4, rule #1).
    """

    trial_id: str
    direction: str  # "A" | "B" | "C" — must match the ledger it appends to
    hypothesis: str

    # --- locked configuration (cfg) ---
    symbol: str
    timeframe: str
    strategy_file: str

    # --- locked GO/REJECT thresholds (fixed, cannot change mid-run) ---
    dk_t_threshold: float = DEFAULT_DK_T_THRESHOLD
    min_positive_sharpe_count: int = DEFAULT_MIN_POSITIVE_SHARPE
    label_shuffle_alpha: float = DEFAULT_LABEL_SHUFFLE_ALPHA
    min_trades: int = DEFAULT_MIN_TRADES

    # --- Optuna parameter-range lock (Spec Part 4) ---
    # Mapping of param_name -> [low, high]. MUST be set before run if tuning.
    optuna_param_ranges: dict[str, Any] | None = None
    optuna_max_trials: int = 0  # 0 => no tuning; ranges ignored

    # --- human gates (Spec Part 3, steps 7 & 10) ---
    requires_human_gate_step7: bool = True  # open sacred holdout
    requires_human_gate_step10: bool = True  # paper / live deployment

    # --- provenance ---
    pre_registered_at: str = ""
    source_doc: str = ""  # e.g. Meta/pre_register_loop_template.md
    source_path: str = ""  # resolved path if loaded from committed file; "" if ad-hoc

    def __post_init__(self) -> None:
        if self.optuna_max_trials < 0:
            raise ValueError("optuna_max_trials must be >= 0")
        if self.optuna_max_trials > 0 and self.optuna_param_ranges is None:
            raise ValueError(
                "optuna_param_ranges MUST be locked in pre-registration before any "
                "backtest when optuna_max_trials > 0 (Spec Part 4, rule #1). "
                "Declare the search space up-front."
            )
        if self.optuna_param_ranges is not None:
            for name, rng in self.optuna_param_ranges.items():
                if not (isinstance(rng, (list, tuple)) and len(rng) == 2 and rng[0] <= rng[1]):
                    raise ValueError(
                        f"optuna_param_ranges['{name}'] must be [low, high] with low <= high"
                    )

    @property
    def parameter_space_locked(self) -> bool:
        """True iff tuning is requested AND its range was locked at registration."""
        return self.optuna_max_trials > 0 and self.optuna_param_ranges is not None

    @property
    def uses_tuning(self) -> bool:
        return self.optuna_max_trials > 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        """Persist the (locked) pre-registration as JSON — the machine-readable source of truth."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


def load_pre_registration(path: str | Path) -> PreRegistration:
    """Load + validate a pre-registration from JSON.

    Raises ValueError if the JSON is missing required fields or violates the
    Optuna range-lock rule. Validation runs in __post_init__, so a malformed
    pre-registration fails loud, before any data is touched.
    """
    p = Path(path).resolve()
    if not any(_is_contained(p, r) for r in _ALLOWED_ROOTS):
        raise ValueError(
            f"Pre-registration must live under Meta/ or research/: {p}"
        )
    if not p.exists():
        raise FileNotFoundError(f"Pre-registration not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    required = {"trial_id", "direction", "hypothesis", "symbol", "timeframe", "strategy_file"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Pre-registration missing required fields: {sorted(missing)}")
    data["source_path"] = str(p.resolve())  # stamp the committed file path
    return PreRegistration(**data)
