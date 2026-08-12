"""
Rollback Manager — Versioned state snapshots and restoration.

Captures snapshots of the running system before each deployment and
restores from any prior snapshot on failure. Maintains an in-memory
version history with optional persistence.

Usage:
    from deploy.rollback import RollbackManager
    rm = RollbackManager()
    snapshot_id = rm.create_snapshot(version="1.1.0", state={...})
    rm.rollback(snapshot_id)
    rm.get_versions()
"""

from __future__ import annotations

import copy
import enum
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SnapshotStatus(enum.Enum):
    """Lifecycle status of a snapshot."""
    CREATED = "created"
    RESTORED = "restored"
    EXPIRED = "expired"
    DELETED = "deleted"


@dataclass
class Snapshot:
    """Immutable record of a system state at a point in time.

    Attributes:
        id: Unique snapshot identifier.
        version: Semantic version string of the deployment.
        state: Deep-copied system state dict.
        created_at: Unix timestamp of creation.
        status: Current lifecycle status.
        metadata: Arbitrary metadata (config hash, author, etc.).
        size_bytes: Approximate memory footprint of the state dict.
    """
    id: str
    version: str
    state: dict[str, Any]
    created_at: float
    status: SnapshotStatus = SnapshotStatus.CREATED
    metadata: dict[str, Any] = field(default_factory=dict)
    size_bytes: int = 0

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> dict[str, Any]:
        """Serialisable representation (excludes raw state for brevity)."""
        return {
            "id": self.id,
            "version": self.version,
            "status": self.status.value,
            "created_at": self.created_at,
            "age_seconds": round(self.age_seconds, 2),
            "size_bytes": self.size_bytes,
            "metadata": self.metadata,
        }


@dataclass
class RollbackResult:
    """Outcome of a rollback operation."""
    success: bool
    snapshot_id: str
    version: str
    error: str | None = None
    duration_seconds: float = 0.0


class RollbackManager:
    """Manages versioned snapshots and rollback operations.

    Maintains a history of snapshots. On each deploy the caller
    should create a snapshot; on failure, rollback restores the
    selected snapshot and marks older ones as expired.

    Attributes:
        max_snapshots: Maximum snapshots to retain. Oldest are expired.
        persistence_path: Optional path to persist snapshot metadata.
    """

    def __init__(
        self,
        max_snapshots: int = 50,
        persistence_path: Path | None = None,
    ) -> None:
        self._snapshots: dict[str, Snapshot] = {}
        self._ordered_ids: list[str] = []
        self._max_snapshots = max_snapshots
        self._persistence_path = persistence_path
        self._restore_callback: Any = None

        logger.info("rollback.initialized", max_snapshots=max_snapshots)

    def set_restore_callback(self, callback: Any) -> None:
        """Register a callback invoked on rollback with the restored state.

        The callback signature should be: fn(state: dict[str, Any]) -> None
        """
        self._restore_callback = callback

    def create_snapshot(
        self,
        version: str,
        state: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Capture current system state as a snapshot.

        The state dict is deep-copied to prevent external mutation.
        Returns the snapshot ID.

        Args:
            version: Semantic version of the current deployment.
            state: Mutable state dict to snapshot.
            metadata: Optional extra info (config hash, deployer, etc.).

        Returns:
            Unique snapshot identifier string.
        """
        snapshot_id = str(uuid.uuid4())[:12]
        state_copy = copy.deepcopy(state)
        size = _estimate_size(state_copy)

        snap = Snapshot(
            id=snapshot_id,
            version=version,
            state=state_copy,
            created_at=time.time(),
            metadata=metadata or {},
            size_bytes=size,
        )

        self._snapshots[snapshot_id] = snap
        self._ordered_ids.append(snapshot_id)

        logger.info(
            "snapshot.created",
            id=snapshot_id,
            version=version,
            size_bytes=size,
            total=len(self._snapshots),
        )

        self._expire_oldest_if_needed()
        self._persist_metadata()

        return snapshot_id

    def rollback(self, snapshot_id: str | None = None) -> RollbackResult:
        """Restore the system to a prior snapshot.

        If snapshot_id is None, rolls back to the most recent snapshot.
        After restoration, newer snapshots are marked EXPIRED.

        Args:
            snapshot_id: Specific snapshot to restore. None = latest.

        Returns:
            RollbackResult with success status and restored version.
        """
        start = time.monotonic()

        target_id = snapshot_id or self._latest_snapshot_id()

        if not target_id:
            return RollbackResult(
                success=False,
                snapshot_id="",
                version="",
                error="No snapshots available to restore",
            )

        snap = self._snapshots.get(target_id)
        if not snap:
            return RollbackResult(
                success=False,
                snapshot_id=target_id,
                version="",
                error=f"Snapshot {target_id} not found",
            )

        if snap.status == SnapshotStatus.DELETED:
            return RollbackResult(
                success=False,
                snapshot_id=target_id,
                version=snap.version,
                error=f"Snapshot {target_id} has been deleted",
            )

        logger.warning(
            "rollback.start",
            target=target_id,
            version=snap.version,
        )

        # ── restore state ──
        try:
            restored_state = copy.deepcopy(snap.state)
            if self._restore_callback:
                self._restore_callback(restored_state)
        except Exception as exc:
            elapsed = time.monotonic() - start
            return RollbackResult(
                success=False,
                snapshot_id=target_id,
                version=snap.version,
                error=f"Restore callback failed: {exc}",
                duration_seconds=elapsed,
            )

        # ── mark status ──
        snap.status = SnapshotStatus.RESTORED

        # Expire anything newer than the restored snapshot
        self._expire_after(target_id)

        elapsed = time.monotonic() - start
        result = RollbackResult(
            success=True,
            snapshot_id=target_id,
            version=snap.version,
            duration_seconds=elapsed,
        )

        logger.info(
            "rollback.success",
            version=snap.version,
            elapsed=f"{elapsed:.3f}s",
        )

        self._persist_metadata()
        return result

    def get_versions(self) -> list[dict[str, Any]]:
        """Return ordered version history (newest first).

        Each entry contains snapshot metadata but not the full state dict.
        """
        versions = []
        for sid in reversed(self._ordered_ids):
            snap = self._snapshots.get(sid)
            if snap and snap.status != SnapshotStatus.DELETED:
                versions.append(snap.to_dict())
        return versions

    def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
        """Retrieve a specific snapshot (including state)."""
        return self._snapshots.get(snapshot_id)

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Soft-delete a snapshot. Returns True if found and deleted."""
        snap = self._snapshots.get(snapshot_id)
        if not snap:
            return False
        snap.status = SnapshotStatus.DELETED
        logger.info("snapshot.deleted", id=snapshot_id, version=snap.version)
        self._persist_metadata()
        return True

    @property
    def snapshot_count(self) -> int:
        return sum(
            1 for s in self._snapshots.values()
            if s.status not in (SnapshotStatus.DELETED, SnapshotStatus.EXPIRED)
        )

    # ── internals ─────────────────────────────────────────────────

    def _latest_snapshot_id(self) -> str | None:
        """Return the most recent non-deleted snapshot ID."""
        for sid in reversed(self._ordered_ids):
            snap = self._snapshots.get(sid)
            if snap and snap.status not in (SnapshotStatus.DELETED, SnapshotStatus.EXPIRED):
                return sid
        return None

    def _expire_oldest_if_needed(self) -> None:
        """Expire the oldest snapshots when over the retention limit."""
        active = [
            sid for sid in self._ordered_ids
            if self._snapshots[sid].status == SnapshotStatus.CREATED
        ]
        while len(active) > self._max_snapshots:
            old_id = active.pop(0)
            old_snap = self._snapshots[old_id]
            old_snap.status = SnapshotStatus.EXPIRED
            logger.debug("snapshot.expired", id=old_id, version=old_snap.version)

    def _expire_after(self, kept_id: str) -> None:
        """Expire all snapshots created after *kept_id*."""
        keep_idx = None
        for i, sid in enumerate(self._ordered_ids):
            if sid == kept_id:
                keep_idx = i
                break

        if keep_idx is None:
            return

        for sid in self._ordered_ids[keep_idx + 1:]:
            snap = self._snapshots.get(sid)
            if snap and snap.status == SnapshotStatus.CREATED:
                snap.status = SnapshotStatus.EXPIRED
                logger.debug("snapshot.expired_after_rollback", id=sid, version=snap.version)

    def _persist_metadata(self) -> None:
        """Persist snapshot metadata to disk if a path is configured."""
        if not self._persistence_path:
            return

        try:
            import json
            self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
            data = [s.to_dict() for s in self._snapshots.values()]
            self._persistence_path.write_text(json.dumps(data, indent=2))
        except Exception as exc:
            logger.error("rollback.persist_failed", err=str(exc))


def _estimate_size(obj: Any, depth: int = 0) -> int:
    """Rough byte-size estimate for a nested dict/list structure."""
    if depth > 10:
        return 0
    if isinstance(obj, dict):
        return sum(len(str(k)) + _estimate_size(v, depth + 1) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return sum(_estimate_size(item, depth + 1) for item in obj)
    if isinstance(obj, str):
        return len(obj.encode("utf-8"))
    if isinstance(obj, (int, float, bool)):
        return 8
    return len(str(obj).encode("utf-8"))
