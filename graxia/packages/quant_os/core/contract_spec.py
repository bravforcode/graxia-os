"""Canonical ContractSpec — single source of truth.

Re-exports from ``broker.contract_spec`` which contains the full
immutable contract specification with validation and hash computation.

Usage::

    from core.contract_spec import ContractSpec, compute_snapshot_hash
"""

from ..broker.contract_spec import ContractSpec, compute_snapshot_hash

__all__ = ["ContractSpec", "compute_snapshot_hash"]
