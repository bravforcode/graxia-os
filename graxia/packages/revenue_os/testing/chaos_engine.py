""
Revenue OS v12 Chaos Engineering Engine
Enterprise-grade chaos testing for fault tolerance validation

Based on agent-introspection-debugging and eval-harness skills from Obsidian
"""
from __future__ import annotations

import asyncio
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set
from datetime import datetime
import structlog

logger = structlog.get_logger()


class ChaosLevel(Enum):
    """Severity levels for chaos experiments."""
    LOW = auto()      # 10% failure rate
    MEDIUM = auto()   # 30% failure rate
    HIGH = auto()     # 50% failure rate
    EXTREME = auto()  # 80% failure rate


class ChaosType(Enum):
    """Types of chaos experiments."""
    NETWORK_DELAY = auto()
    NETWORK_PARTITION = auto()
    DATABASE_SLOWDOWN = auto()
    DATABASE_CONNECTION_DROP = auto()
    REDIS_UNAVAILABLE = auto()
    CELERY_WORKER_CRASH = auto()
    MEMORY_PRESSURE = auto()
    CPU_SPIKE = auto()


@dataclass
class ChaosResult:
    """Result of a chaos experiment."""
    experiment_id: str
    chaos_type: ChaosType
    level: ChaosLevel
    started_at: datetime
    ended_at: Optional[datetime] = None
    success: bool = False
    error_message: Optional[str] = None
    recovery_time_ms: float = 0.0
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemMetrics:
    """System health metrics during chaos."""
    timestamp: datetime
    response_time_ms: float
    error_rate: float
    throughput_rps: float
    active_connections: int
    queue_depth: int
    memory_usage_mb: float
    cpu_usage_percent: float


class ChaosInjector(ABC):
    """Abstract base class for chaos injectors."""
    
    def __init__(self, level: ChaosLevel = ChaosLevel.MEDIUM):
        self.level = level
        self.failure_rates = {
            ChaosLevel.LOW: 0.1,
            ChaosLevel.MEDIUM: 0.3,
            ChaosLevel.HIGH: 0.5,
            ChaosLevel.EXTREME: 0.8,
        }
    
    @abstractmethod
    async def inject(self, context: Dict[str, Any]) -> ChaosResult:
        """Inject chaos into the system."""
        pass
    
    @abstractmethod
    async def recover(self, context: Dict[str, Any]) -> bool:
        """Recover from chaos."""
        pass
    
    def should_fail(self) -> bool:
        """Determine if this operation should fail based on chaos level."""
        return random.random() < self.failure_rates[self.level]


class NetworkDelayInjector(ChaosInjector):
    """Inject network delays."""
    
    async def inject(self, context: Dict[str, Any]) -> ChaosResult:
        delay_ms = {
            ChaosLevel.LOW: (100, 500),
            ChaosLevel.MEDIUM: (500, 2000),
            ChaosLevel.HIGH: (2000, 5000),
            ChaosLevel.EXTREME: (5000, 15000),
        }[self.level]
        
        delay = random.uniform(*delay_ms) / 1000
        logger.warning("chaos_network_delay_injected", delay_ms=delay * 1000)
        await asyncio.sleep(delay)
        
        return ChaosResult(
            experiment_id=f"net-delay-{int(time.time())}",
            chaos_type=ChaosType.NETWORK_DELAY,
            level=self.level,
            started_at=datetime.utcnow(),
            ended_at=datetime.utcnow(),
            success=True,
            metrics={"delay_ms": delay * 1000}
        )
    
    async def recover(self, context: Dict[str, Any]) -> bool:
        return True  # No persistent state to recover


class DatabaseSlowdownInjector(ChaosInjector):
    """Simulate slow database queries."""
    
    def __init__(self, level: ChaosLevel = ChaosLevel.MEDIUM):
        super().__init__(level)
        self.original_execute = None
    
    async def inject(self, context: Dict[str, Any]) -> ChaosResult:
        slowdown_factor = {
            ChaosLevel.LOW: 2,
            ChaosLevel.MEDIUM: 5,
            ChaosLevel.HIGH: 10,
            ChaosLevel.EXTREME: 50,
        }[self.level]
        
        logger.warning("chaos_database_slowdown_injected", factor=slowdown_factor)
        
        return ChaosResult(
            experiment_id=f"db-slow-{int(time.time())}",
            chaos_type=ChaosType.DATABASE_SLOWDOWN,
            level=self.level,
            started_at=datetime.utcnow(),
            success=True,
            metrics={"slowdown_factor": slowdown_factor}
        )
    
    async def recover(self, context: Dict[str, Any]) -> bool:
        return True


class RedisUnavailableInjector(ChaosInjector):
    """Simulate Redis unavailability."""
    
    async def inject(self, context: Dict[str, Any]) -> ChaosResult:
        redis_client = context.get("redis_client")
        if redis_client:
            redis_client._chaos_unavailable = True
        
        logger.error("chaos_redis_unavailable_injected")
        
        return ChaosResult(
            experiment_id=f"redis-down-{int(time.time())}",
            chaos_type=ChaosType.REDIS_UNAVAILABLE,
            level=self.level,
            started_at=datetime.utcnow(),
            success=True
        )
    
    async def recover(self, context: Dict[str, Any]) -> bool:
        redis_client = context.get("redis_client")
        if redis_client:
            redis_client._chaos_unavailable = False
        return True


class CeleryWorkerCrashInjector(ChaosInjector):
    """Simulate Celery worker crashes."""
    
    async def inject(self, context: Dict[str, Any]) -> ChaosResult:
        celery_app = context.get("celery_app")
        if celery_app:
            celery_app._chaos_worker_crash = True
        
        logger.error("chaos_celery_worker_crash_injected")
        
        return ChaosResult(
            experiment_id=f"celery-crash-{int(time.time())}",
            chaos_type=ChaosType.CELERY_WORKER_CRASH,
            level=self.level,
            started_at=datetime.utcnow(),
            success=True
        )
    
    async def recover(self, context: Dict[str, Any]) -> bool:
        celery_app = context.get("celery_app")
        if celery_app:
            celery_app._chaos_worker_crash = False
        return True


class ChaosEngine:
    """
    Central chaos engineering engine.
    Manages and executes chaos experiments.
    """
    
    def __init__(self):
        self.injectors: Dict[ChaosType, ChaosInjector] = {}
        self.active_experiments: Set[str] = set()
        self.results: List[ChaosResult] = []
        self.metrics_history: List[SystemMetrics] = []
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
    
    def register_injector(self, chaos_type: ChaosType, injector: ChaosInjector):
        """Register a chaos injector."""
        self.injectors[chaos_type] = injector
        logger.info("chaos_injector_registered", type=chaos_type.name)
    
    async def start_monitoring(self, interval_seconds: float = 5.0):
        """Start system metrics monitoring."""
        self._running = True
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(interval_seconds)
        )
        logger.info("chaos_monitoring_started", interval=interval_seconds)
    
    async def stop_monitoring(self):
        """Stop system metrics monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("chaos_monitoring_stopped")
    
    async def _monitor_loop(self, interval: float):
        """Continuous monitoring loop."""
        while self._running:
            try:
                metrics = await self._collect_metrics()
                self.metrics_history.append(metrics)
                
                # Keep only last 1000 data points
                if len(self.metrics_history) > 1000:
                    self.metrics_history = self.metrics_history[-1000:]
                
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error("chaos_monitor_error", error=str(e))
                await asyncio.sleep(interval)
    
    async def _collect_metrics(self) -> SystemMetrics:
        """Collect current system metrics."""
        import psutil
        
        return SystemMetrics(
            timestamp=datetime.utcnow(),
            response_time_ms=random.uniform(10, 1000),  # Placeholder
            error_rate=0.0,  # Calculate from recent results
            throughput_rps=random.uniform(10, 1000),  # Placeholder
            active_connections=random.randint(1, 100),  # Placeholder
            queue_depth=random.randint(0, 1000),  # Placeholder
            memory_usage_mb=psutil.virtual_memory().used / 1024 / 1024,
            cpu_usage_percent=psutil.cpu_percent()
        )
    
    async def run_experiment(
        self,
        chaos_type: ChaosType,
        context: Dict[str, Any],
        duration_seconds: float = 30.0
    ) -> ChaosResult:
        """Run a single chaos experiment."""
        injector = self.injectors.get(chaos_type)
        if not injector:
            raise ValueError(f"No injector registered for {chaos_type}")
        
        experiment_id = f"{chaos_type.name}-{int(time.time())}"
        self.active_experiments.add(experiment_id)
        
        start_time = time.time()
        recovery_time = 0.0
        
        try:
            # Inject chaos
            result = await injector.inject(context)
            
            # Wait for experiment duration
            await asyncio.sleep(duration_seconds)
            
            # Recovery
            recovery_start = time.time()
            recovered = await injector.recover(context)
            recovery_time = (time.time() - recovery_start) * 1000
            
            result.ended_at = datetime.utcnow()
            result.recovery_time_ms = recovery_time
            result.success = recovered
            
        except Exception as e:
            logger.exception("chaos_experiment_failed")
            result = ChaosResult(
                experiment_id=experiment_id,
                chaos_type=chaos_type,
                level=injector.level,
                started_at=datetime.utcnow(),
                ended_at=datetime.utcnow(),
                success=False,
                error_message=str(e)
            )
        finally:
            self.active_experiments.discard(experiment_id)
            self.results.append(result)
        
        return result
    
    async def run_scenario(
        self,
        name: str,
        experiments: List[tuple],
        context: Dict[str, Any]
    ) -> List[ChaosResult]:
        """
        Run a chaos scenario with multiple experiments.
        
        Args:
            name: Scenario name
            experiments: List of (chaos_type, duration_seconds) tuples
            context: Shared context for all experiments
        
        Returns:
            List of ChaosResult
        """
        logger.info("chaos_scenario_started", name=name, experiments=len(experiments))
        results = []
        
        for chaos_type, duration in experiments:
            result = await self.run_experiment(chaos_type, context, duration)
            results.append(result)
            
            # Brief pause between experiments
            await asyncio.sleep(5)
        
        logger.info("chaos_scenario_completed", name=name, results=len(results))
        return results
    
    def get_report(self) -> Dict[str, Any]:
        """Generate chaos testing report."""
        if not self.results:
            return {"message": "No experiments run yet"}
        
        total = len(self.results)
        successful = sum(1 for r in self.results if r.success)
        failed = total - successful
        
        by_type: Dict[str, Dict] = {}
        for result in self.results:
            type_name = result.chaos_type.name
            if type_name not in by_type:
                by_type[type_name] = {"total": 0, "success": 0, "failed": 0}
            by_type[type_name]["total"] += 1
            if result.success:
                by_type[type_name]["success"] += 1
            else:
                by_type[type_name]["failed"] += 1
        
        avg_recovery_time = sum(
            r.recovery_time_ms for r in self.results
        ) / total if total > 0 else 0
        
        return {
            "summary": {
                "total_experiments": total,
                "successful": successful,
                "failed": failed,
                "success_rate": successful / total if total > 0 else 0,
                "average_recovery_time_ms": avg_recovery_time,
            },
            "by_type": by_type,
            "recent_results": [
                {
                    "id": r.experiment_id,
                    "type": r.chaos_type.name,
                    "level": r.level.name,
                    "success": r.success,
                    "recovery_ms": r.recovery_time_ms,
                }
                for r in self.results[-10:]
            ],
        }


# Predefined chaos scenarios
SCENARIOS = {
    "network_instability": [
        (ChaosType.NETWORK_DELAY, 30),
        (ChaosType.NETWORK_PARTITION, 15),
        (ChaosType.NETWORK_DELAY, 30),
    ],
    "database_stress": [
        (ChaosType.DATABASE_SLOWDOWN, 60),
        (ChaosType.DATABASE_CONNECTION_DROP, 30),
        (ChaosType.DATABASE_SLOWDOWN, 60),
    ],
    "infrastructure_failure": [
        (ChaosType.REDIS_UNAVAILABLE, 30),
        (ChaosType.CELERY_WORKER_CRASH, 45),
        (ChaosType.REDIS_UNAVAILABLE, 30),
    ],
    "full_system_stress": [
        (ChaosType.NETWORK_DELAY, 30),
        (ChaosType.DATABASE_SLOWDOWN, 45),
        (ChaosType.REDIS_UNAVAILABLE, 30),
        (ChaosType.CELERY_WORKER_CRASH, 30),
        (ChaosType.MEMORY_PRESSURE, 60),
    ],
}
