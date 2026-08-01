"""
loop_engineering — Safe Self-Improving Agent Loop for quant_os.

Implements the Loop Engineering spec: Loop A (research) and Loop B (operational)
as SEPARATE entry points, with HARD human-review gates (steps 7 & 10), a
3-layer verification (DK-test + label-shuffle + min-trades), zombie-hypothesis
guards, provenance timestamp checks, and a working-ledger that writes in the same
round as the run while canonical ledgers require explicit human sign-off.

Design is fail-closed and governance-compliant (CONTRIBUTING.md line 108).
"""

from .gates import GateState, HumanDecision, human_gate_step7, human_gate_step10
from .ledger import (
    STATUS_APPROVED_FOR_PAPER,
    STATUS_CANDIDATE,
    STATUS_HOLDOUT_FAIL,
    STATUS_HOLDOUT_PASS,
    STATUS_REJECTED,
    STATUS_UNTESTED,
    HumanSignOffRequiredError,
    LedgerEntry,
    SacredHoldout,
    StoppingRule,
    WorkingLedger,
)
from .loop_a import LoopAResult, run_research_loop
from .loop_b import OperationalAlert, PerformanceSample, run_operational_loop
from .pre_register import (
    DEFAULT_DK_T_THRESHOLD,
    DEFAULT_LABEL_SHUFFLE_ALPHA,
    DEFAULT_MIN_POSITIVE_SHARPE,
    DEFAULT_MIN_TRADES,
    PreRegistration,
    load_pre_registration,
)
from .registry import (
    ProvenanceCheck,
    check_provenance,
    is_zombie,
    load_hypothesis_registry,
)
from .validation import (
    ValidationAdapters,
    VerificationResult,
    VerificationThresholds,
    build_default_adapters,
    verify_three_layer,
)

__all__ = [
    "PreRegistration",
    "load_pre_registration",
    "DEFAULT_DK_T_THRESHOLD",
    "DEFAULT_MIN_POSITIVE_SHARPE",
    "DEFAULT_LABEL_SHUFFLE_ALPHA",
    "DEFAULT_MIN_TRADES",
    "WorkingLedger",
    "LedgerEntry",
    "StoppingRule",
    "SacredHoldout",
    "HumanSignOffRequiredError",
    "STATUS_REJECTED",
    "STATUS_CANDIDATE",
    "STATUS_UNTESTED",
    "STATUS_HOLDOUT_PASS",
    "STATUS_HOLDOUT_FAIL",
    "STATUS_APPROVED_FOR_PAPER",
    "load_hypothesis_registry",
    "is_zombie",
    "check_provenance",
    "ProvenanceCheck",
    "VerificationThresholds",
    "VerificationResult",
    "verify_three_layer",
    "ValidationAdapters",
    "build_default_adapters",
    "GateState",
    "HumanDecision",
    "human_gate_step7",
    "human_gate_step10",
    "LoopAResult",
    "run_research_loop",
    "PerformanceSample",
    "OperationalAlert",
    "run_operational_loop",
]
