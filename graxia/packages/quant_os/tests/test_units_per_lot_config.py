"""
SUPERSEDED — ContractSpec is now the mandatory source of truth.

These tests verified that position sizers, risk engine, and strategy base
read `units_per_lot` from config as a fallback. That fallback has been
removed per the ContractSpec enforcement change request.

All sizing paths now require an explicit ContractSpec parameter. See:
  tests/test_contract_spec.py
  risk/contract_spec.py

Retained as a no-op to avoid breaking the test runner. Remove this file
once all downstream consumers have migrated to ContractSpec.
"""

import pytest


@pytest.mark.skip(reason="units_per_lot config fallback removed — use ContractSpec")
class TestPositionSizerReadsConfig:
    pass


@pytest.mark.skip(reason="units_per_lot config fallback removed — use ContractSpec")
class TestPositionSizerOverride:
    pass


@pytest.mark.skip(reason="units_per_lot config fallback removed — use ContractSpec")
class TestRiskEngineUsesConfig:
    pass


@pytest.mark.skip(reason="units_per_lot config fallback removed — use ContractSpec")
class TestCalculateCorrectSize:
    pass
