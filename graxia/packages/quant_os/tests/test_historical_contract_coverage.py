"""Phase 3.1A — Historical contract and swap coverage tests."""

from datetime import datetime
from decimal import Decimal

from graxia.packages.quant_os.execution.provenance import (
    AssumptionQuality,
    ContractProvenance,
    SwapProvenance,
    create_default_provenance,
)
from graxia.packages.quant_os.execution.swap_model import (
    SwapMode,
    SwapRates,
    calculate_swap,
)


def test_contract_snapshot_has_required_fields():
    """ContractProvenance must have all required fields."""
    prov = ContractProvenance(
        contract_snapshot_id="test_v1",
        contract_valid_from_utc="2024-01-01T00:00:00Z",
        contract_valid_to_utc="2025-12-31T23:59:59Z",
        contract_quality=AssumptionQuality.DOCUMENTED_ASSUMPTION,
        symbol="XAUUSD",
        trade_contract_size=100.0,
        trade_tick_size=0.01,
        trade_tick_value=1.0,
        volume_step=0.01,
        volume_min=0.01,
        stops_level_points=10.0,
    )
    assert prov.contract_snapshot_id == "test_v1"
    assert prov.contract_quality == AssumptionQuality.DOCUMENTED_ASSUMPTION


def test_swap_provenance_has_required_fields():
    """SwapProvenance must have all required fields."""
    prov = SwapProvenance(
        swap_model_id="test_swap_v1",
        swap_quality=AssumptionQuality.ASSUMED,
        rollover_timezone="America/New_York",
        swap_long_daily=-2.83,
        swap_short_daily=0.56,
        rollover_day=2,
    )
    assert prov.swap_quality == AssumptionQuality.ASSUMED
    assert prov.rollover_day == 2


def test_run_provenance_deterministic_hash():
    """Same provenance inputs → same hash."""
    p1 = create_default_provenance("abc123")
    p2 = create_default_provenance("abc123")
    assert p1.provenance_hash() == p2.provenance_hash()


def test_assumption_quality_labels():
    """AssumptionQuality enum has required values."""
    assert AssumptionQuality.OBSERVED.value == "OBSERVED"
    assert AssumptionQuality.DOCUMENTED_ASSUMPTION.value == "DOCUMENTED_ASSUMPTION"
    assert AssumptionQuality.ASSUMED.value == "ASSUMED"


def test_contract_valid_time_range():
    """Contract valid_from must be before valid_to."""
    prov = create_default_provenance()
    assert prov.contract.contract_valid_from_utc < prov.contract.contract_valid_to_utc


def test_swap_sensitivity_no_swap():
    """swap_mode=NONE → is_unknown=True when held overnight."""
    rates = SwapRates(mode=SwapMode.NONE)
    result = calculate_swap(
        entry_time=datetime(2025, 1, 1, 10, 0),
        exit_time=datetime(2025, 1, 2, 10, 0),
        side="BUY",
        volume=Decimal("0.1"),
        swap_rates=rates,
    )
    assert result.is_unknown is True
    assert result.swap_applied == 0


def test_swap_sensitivity_base_swap():
    """Base swap applied correctly."""
    rates = SwapRates(
        swap_long=Decimal("-2.83"),
        swap_short=Decimal("0.56"),
        mode=SwapMode.FIXED,
        rollover_day=2,
    )
    result = calculate_swap(
        entry_time=datetime(2025, 1, 6, 10, 0),  # Monday
        exit_time=datetime(2025, 1, 7, 10, 0),  # Tuesday
        side="BUY",
        volume=Decimal("1.0"),
        swap_rates=rates,
    )
    assert result.is_unknown is False
    assert result.swap_applied != 0


def test_swap_sensitivity_1_5x():
    """1.5× adverse swap applied via volume multiplier."""
    rates = SwapRates(
        swap_long=Decimal("-2.83"),
        swap_short=Decimal("0.56"),
        mode=SwapMode.FIXED,
        rollover_day=2,
    )
    result = calculate_swap(
        entry_time=datetime(2025, 1, 6, 10, 0),
        exit_time=datetime(2025, 1, 7, 10, 0),
        side="BUY",
        volume=Decimal("1.5"),
        swap_rates=rates,
    )
    base = calculate_swap(
        entry_time=datetime(2025, 1, 6, 10, 0),
        exit_time=datetime(2025, 1, 7, 10, 0),
        side="BUY",
        volume=Decimal("1.0"),
        swap_rates=rates,
    )
    assert result.swap_applied == base.swap_applied * Decimal("1.5")


def test_swap_sensitivity_2_0x():
    """2.0× adverse swap applied via volume multiplier."""
    rates = SwapRates(
        swap_long=Decimal("-2.83"),
        swap_short=Decimal("0.56"),
        mode=SwapMode.FIXED,
        rollover_day=2,
    )
    result = calculate_swap(
        entry_time=datetime(2025, 1, 6, 10, 0),
        exit_time=datetime(2025, 1, 7, 10, 0),
        side="BUY",
        volume=Decimal("2.0"),
        swap_rates=rates,
    )
    base = calculate_swap(
        entry_time=datetime(2025, 1, 6, 10, 0),
        exit_time=datetime(2025, 1, 7, 10, 0),
        side="BUY",
        volume=Decimal("1.0"),
        swap_rates=rates,
    )
    assert result.swap_applied == base.swap_applied * Decimal("2.0")


def test_wednesday_3x_rollover():
    """Wednesday rollover = 3× daily rate."""
    rates = SwapRates(
        swap_long=Decimal("-2.83"),
        swap_short=Decimal("0.56"),
        mode=SwapMode.FIXED,
        rollover_day=2,  # Wednesday
    )
    # Mon→Wed: 2 days held, Wed is rollover day
    result = calculate_swap(
        entry_time=datetime(2025, 1, 6, 10, 0),  # Monday
        exit_time=datetime(2025, 1, 8, 10, 0),  # Wednesday
        side="BUY",
        volume=Decimal("1.0"),
        swap_rates=rates,
    )
    # effective = 1 (Tue) + 3 (Wed) = 4
    assert result.swap_applied == Decimal("-2.83") * Decimal("4")
