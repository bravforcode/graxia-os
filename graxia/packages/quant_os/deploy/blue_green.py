"""
Blue-Green Deployment — Zero-downtime deployment for quant_os.

Maintains two identical environments (blue/green). Traffic is routed
to one at a time via an atomic switch. On failure the system rolls
back automatically to the previously-active environment.

Usage:
    from deploy.blue_green import BlueGreenDeploy
    deployer = BlueGreenDeploy()
    result = deployer.deploy(version="1.2.0")
    deployer.switch_traffic()
    deployer.rollback()
"""

from __future__ import annotations

import enum
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class Environment(enum.Enum):
    """Deployment environment slot."""

    BLUE = "blue"
    GREEN = "green"


class DeployState(enum.Enum):
    """Lifecycle states for a deployment."""

    IDLE = "idle"
    DEPLOYING = "deploying"
    VALIDATING = "validating"
    ACTIVE = "active"
    ROLLING_BACK = "rolling_back"
    FAILED = "failed"


@dataclass
class EnvironmentSnapshot:
    """Immutable snapshot of a single environment's state."""

    env: Environment
    version: str
    deployed_at: float
    config_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.deployed_at


@dataclass
class DeployResult:
    """Result of a deploy or switch operation."""

    success: bool
    from_env: Environment | None
    to_env: Environment
    version: str
    error: str | None = None
    duration_seconds: float = 0.0


class BlueGreenDeploy:
    """Manages zero-downtime blue-green deployments.

    Keeps two identical environments (blue and green). Only one is live
    at any time. Deploys go to the idle slot, validate, then switch.

    Attributes:
        health_check: Callable that returns True if environment is healthy.
        deploy_hook: Optional callable invoked to provision an environment.
        switch_hook: Optional callable invoked after traffic switch.
    """

    def __init__(
        self,
        health_check: Callable[[Environment], bool] | None = None,
        deploy_hook: Callable[[Environment, str], None] | None = None,
        switch_hook: Callable[[Environment], None] | None = None,
    ) -> None:
        self._state = DeployState.IDLE
        self._active: Environment = Environment.BLUE
        self._versions: dict[Environment, EnvironmentSnapshot] = {}
        self._deploy_history: list[DeployResult] = []
        self._health_check = health_check or self._default_health_check
        self._deploy_hook = deploy_hook
        self._switch_hook = switch_hook
        self._lock_held = False

        logger.info(
            "blue_green.initialized",
            active=self._active.value,
        )

    # ── public API ────────────────────────────────────────────────

    def deploy(self, version: str, config_hash: str = "", metadata: dict[str, Any] | None = None) -> DeployResult:
        """Deploy *version* to the idle environment, validate, and switch.

        Steps:
          1. Determine idle slot (the one that is NOT active).
          2. Provision / deploy to idle slot via deploy_hook.
          3. Run health check on idle slot.
          4. If healthy → atomic traffic switch.
          5. If unhealthy → automatic rollback, mark failed.

        Returns:
            DeployResult with success status and timing.
        """
        if self._state not in (DeployState.IDLE, DeployState.ACTIVE, DeployState.FAILED):
            logger.warning("blue_green.deploy.blocked", state=self._state.value)
            return DeployResult(
                success=False,
                from_env=self._active,
                to_env=self._idle,
                version=version,
                error=f"Cannot deploy in state {self._state.value}",
            )

        start = time.monotonic()
        idle = self._idle

        logger.info(
            "blue_green.deploy.start",
            version=version,
            target=idle.value,
            active=self._active.value,
        )

        # ── deploy phase ──
        self._state = DeployState.DEPLOYING
        try:
            if self._deploy_hook:
                self._deploy_hook(idle, version)
        except Exception as exc:
            elapsed = time.monotonic() - start
            result = DeployResult(
                success=False,
                from_env=self._active,
                to_env=idle,
                version=version,
                error=f"Deploy hook failed: {exc}",
                duration_seconds=elapsed,
            )
            self._state = DeployState.FAILED
            self._deploy_history.append(result)
            logger.error("blue_green.deploy.hook_failed", err=str(exc))
            return result

        # ── validate phase ──
        self._state = DeployState.VALIDATING
        if not self._health_check(idle):
            elapsed = time.monotonic() - start
            result = DeployResult(
                success=False,
                from_env=self._active,
                to_env=idle,
                version=version,
                error="Health check failed after deploy",
                duration_seconds=elapsed,
            )
            self._state = DeployState.FAILED
            self._deploy_history.append(result)
            logger.error("blue_green.deploy.health_check_failed")
            return result

        # ── switch phase ──
        snap = EnvironmentSnapshot(
            env=idle,
            version=version,
            deployed_at=time.time(),
            config_hash=config_hash,
            metadata=metadata or {},
        )
        self._versions[idle] = snap
        self._atomic_switch(idle)

        elapsed = time.monotonic() - start
        result = DeployResult(
            success=True,
            from_env=self._previous_active,
            to_env=self._active,
            version=version,
            duration_seconds=elapsed,
        )
        self._deploy_history.append(result)
        self._state = DeployState.ACTIVE

        logger.info(
            "blue_green.deploy.success",
            version=version,
            active=self._active.value,
            elapsed=f"{elapsed:.3f}s",
        )
        return result

    def switch_traffic(self) -> DeployResult:
        """Atomically switch traffic to the idle environment.

        Validates the idle environment is healthy before switching.
        If validation fails, the current active remains unchanged.
        """
        if self._state == DeployState.DEPLOYING:
            return DeployResult(
                success=False,
                from_env=self._active,
                to_env=self._idle,
                version=self._idle_version,
                error="Cannot switch during active deploy",
            )

        idle = self._idle
        idle_snap = self._versions.get(idle)

        if not idle_snap:
            return DeployResult(
                success=False,
                from_env=self._active,
                to_env=idle,
                version="",
                error=f"No deployment on {idle.value} to switch to",
            )

        if not self._health_check(idle):
            return DeployResult(
                success=False,
                from_env=self._active,
                to_env=idle,
                version=idle_snap.version,
                error=f"Health check failed for {idle.value}",
            )

        self._atomic_switch(idle)
        result = DeployResult(
            success=True,
            from_env=self._previous_active,
            to_env=self._active,
            version=idle_snap.version,
        )
        self._deploy_history.append(result)

        logger.info(
            "blue_green.switch",
            to=self._active.value,
            version=idle_snap.version,
        )
        return result

    def rollback(self) -> DeployResult:
        """Roll back to the previously-active environment.

        Only succeeds if the target environment has a prior deployment.
        Used as a safety net when post-switch issues are detected.
        """
        if self._state == DeployState.ROLLING_BACK:
            return DeployResult(
                success=False,
                from_env=self._active,
                to_env=self._idle,
                version="",
                error="Rollback already in progress",
            )

        target = self._idle
        target_snap = self._versions.get(target)

        if not target_snap:
            return DeployResult(
                success=False,
                from_env=self._active,
                to_env=target,
                version="",
                error=f"No prior deployment on {target.value} to roll back to",
            )

        self._state = DeployState.ROLLING_BACK
        logger.warning(
            "blue_green.rollback.start",
            from_env=self._active.value,
            to_env=target.value,
            version=target_snap.version,
        )

        if not self._health_check(target):
            self._state = DeployState.FAILED
            return DeployResult(
                success=False,
                from_env=self._active,
                to_env=target,
                version=target_snap.version,
                error=f"Rollback target {target.value} is unhealthy",
            )

        self._atomic_switch(target)
        result = DeployResult(
            success=True,
            from_env=self._previous_active,
            to_env=self._active,
            version=target_snap.version,
        )
        self._deploy_history.append(result)
        self._state = DeployState.ACTIVE

        logger.info(
            "blue_green.rollback.success",
            active=self._active.value,
            version=target_snap.version,
        )
        return result

    def get_status(self) -> dict[str, Any]:
        """Return current deployment status.

        Includes active environment, both slot versions, state, and
        recent deployment history.
        """
        blue_snap = self._versions.get(Environment.BLUE)
        green_snap = self._versions.get(Environment.GREEN)

        return {
            "active": self._active.value,
            "idle": self._idle.value,
            "state": self._state.value,
            "blue": {
                "version": blue_snap.version if blue_snap else None,
                "deployed_at": blue_snap.deployed_at if blue_snap else None,
                "config_hash": blue_snap.config_hash if blue_snap else None,
            },
            "green": {
                "version": green_snap.version if green_snap else None,
                "deployed_at": green_snap.deployed_at if green_snap else None,
                "config_hash": green_snap.config_hash if green_snap else None,
            },
            "history": [
                {
                    "success": r.success,
                    "from": r.from_env.value if r.from_env else None,
                    "to": r.to_env.value,
                    "version": r.version,
                    "error": r.error,
                    "duration": f"{r.duration_seconds:.3f}s",
                }
                for r in self._deploy_history[-10:]
            ],
        }

    @property
    def active_version(self) -> str | None:
        """Version currently serving live traffic."""
        snap = self._versions.get(self._active)
        return snap.version if snap else None

    # ── internals ─────────────────────────────────────────────────

    @property
    def _idle(self) -> Environment:
        return Environment.GREEN if self._active == Environment.BLUE else Environment.BLUE

    @property
    def _previous_active(self) -> Environment:
        """The environment that was active before the last switch."""
        return self._idle  # after switch, _idle is the old active

    @property
    def _idle_version(self) -> str:
        snap = self._versions.get(self._idle)
        return snap.version if snap else ""

    def _atomic_switch(self, target: Environment) -> None:
        """Perform the atomic traffic switch.

        In production this would update a load balancer, DNS record,
        or process supervisor. Here we update internal state and
        invoke the optional switch_hook.
        """
        old = self._active
        self._active = target

        if self._switch_hook:
            try:
                self._switch_hook(target)
            except Exception as exc:
                logger.error("blue_green.switch_hook_failed", err=str(exc))
                # Switch already happened internally; log but don't revert
                # to avoid half-state.

        logger.info(
            "blue_green.traffic_switched",
            from_env=old.value,
            to_env=target.value,
        )

    @staticmethod
    def _default_health_check(env: Environment) -> bool:
        """Placeholder health check — always healthy.

        Replace with real connectivity / readiness probes in production.
        """
        return True
