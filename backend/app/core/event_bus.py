import asyncio
import inspect
import json
import logging
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypeAlias
from uuid import UUID

logger = logging.getLogger(__name__)

EventPayload: TypeAlias = dict[str, Any]
EventHandler: TypeAlias = Callable[[EventPayload], object | Awaitable[object]]
QueuedEvent: TypeAlias = tuple[str, EventPayload, str | None]


class DeliverySuccessReplayError(ValueError):
    """Generic replay cannot authenticate a delivery receipt or tenant."""


def _is_delivery_success_event(event: str) -> bool:
    """Recognize terminal delivery aliases and equivalent success semantics."""
    if not isinstance(event, str):
        return False
    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", event.strip())
    words = re.sub(r"[^A-Za-z0-9]+", "_", separated).casefold().strip("_").split("_")
    if not words:
        return False
    terminal_delivery = {"sent", "delivered"}
    terminal_success = {
        "accepted", "complete", "completed", "success", "successful",
        "succeeded", "submitted",
    }
    delivery_subjects = {
        "application", "bid", "delivery", "email", "invitation", "message",
        "notification", "outreach", "proposal", "submission", "winback",
    }
    compact_subjects = {
        "application", "bid", "delivery", "email", "invitation", "message",
        "notification", "outreach", "proposal", "submission", "winback",
        "jobapplication", "jobsubmission", "winbackmessage",
    }
    compact = "".join(words)
    compact_terminal = any(
        compact.endswith(status)
        and compact[: -len(status)] in compact_subjects
        for status in terminal_delivery | terminal_success
    )
    if words[-1] in terminal_delivery or compact_terminal:
        return True
    return bool(
        words[-1] in terminal_success
        and delivery_subjects.intersection(words[:-1])
    )


def _canonical_organization_id(value: Any) -> str | None:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None
    return str(parsed) if parsed.int else None


def _payload_organization_matches(payload: EventPayload, owner: str) -> bool:
    """Reject payload claims that are malformed or conflict with trusted ownership."""
    if not isinstance(payload, dict):
        return False
    pending = [payload]
    visited: set[int] = set()
    while pending:
        source = pending.pop()
        if id(source) in visited:
            continue
        visited.add(id(source))
        if isinstance(source, dict):
            pending.extend(source.values())
        elif isinstance(source, (list, tuple)):
            pending.extend(source)
        else:
            continue
        if isinstance(source, dict):
            for key in ("organization_id", "org_id"):
                if key not in source or source[key] is None:
                    continue
                if _canonical_organization_id(source[key]) != owner:
                    return False
    return True


def _trusted_auth_organization_id(auth_context: Any) -> str | None:
    """Accept only authenticated persisted context or the fixed local-dev tenant."""
    try:
        from app.auth.context import AuthContext, LOCAL_DEV_ORGANIZATION_ID
    except ImportError:
        return None
    if type(auth_context) is not AuthContext or auth_context.is_authenticated is not True:
        return None
    organization_id = _canonical_organization_id(auth_context.organization_id)
    if organization_id is None:
        return None
    if auth_context.is_staging_or_production:
        if auth_context.is_mock_auth or auth_context.auth_method != "bearer_jwt":
            return None
    elif auth_context.environment in {"local", "development", "test"}:
        if (
            organization_id != str(LOCAL_DEV_ORGANIZATION_ID)
        ):
            return None
    else:
        return None
    return organization_id


def _trusted_event_organization_id(
    payload: EventPayload, auth_context: Any = None
) -> str | None:
    owner = _trusted_auth_organization_id(auth_context)
    if owner is None or not _payload_organization_matches(payload, owner):
        return None
    return owner


class EventBus:
    def __init__(self, shutdown_timeout: int = 30, max_queue_size: int = 10000) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[QueuedEvent] = asyncio.Queue(maxsize=max_queue_size)
        self._stats: dict[str, int] = defaultdict(int)
        self._organization_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._running = False
        self._failed_events: list[tuple[str, EventPayload, str]] = []  # Dead letter queue
        self._failed_event_organizations: list[str | None] = []
        self._processing_tasks: set[asyncio.Task] = set()  # Track processing tasks
        self._shutdown_timeout: int = shutdown_timeout  # Configurable timeout
        self._max_queue_size: int = max_queue_size  # Maximum queue size for backpressure
        self._queue_full_count: int = 0  # Track how many times queue was full
        self._dropped_events: int = 0  # Track dropped events due to full queue

    def subscribe(self, event: str, handler: EventHandler) -> None:
        if handler in self._handlers[event]:
            logger.debug(
                "EventBus: skipping duplicate subscription %s to '%s'",
                getattr(handler, "__name__", handler.__class__.__name__),
                event,
            )
            return
        self._handlers[event].append(handler)
        logger.debug(
            "EventBus: subscribed %s to '%s'",
            getattr(handler, "__name__", handler.__class__.__name__),
            event,
        )

    async def emit(
        self,
        event: str,
        payload: EventPayload,
        timeout: float | None = 1.0,
        *,
        auth_context: Any = None,
    ) -> bool:
        """
        Queue an ordinary event; terminal delivery names require verified receipt.
        """
        if _is_delivery_success_event(event):
            raise DeliverySuccessReplayError(
                "Terminal delivery events require a persisted verified receipt"
            )
        organization_id = _trusted_event_organization_id(payload, auth_context)
        return await self._enqueue_event(event, payload, timeout, organization_id)

    async def _enqueue_event(
        self,
        event: str,
        payload: EventPayload,
        timeout: float | None,
        organization_id: str | None,
    ) -> bool:
        self._stats[event] += 1
        if organization_id is not None:
            self._organization_stats[organization_id][event] += 1

        try:
            if timeout is None:
                await self._queue.put((event, payload, organization_id))
            else:
                await asyncio.wait_for(
                    self._queue.put((event, payload, organization_id)),
                    timeout=timeout,
                )

            logger.debug(
                "EventBus: emitted '%s' with payload keys=%s (queue_size=%d/%d)",
                event,
                list(payload.keys()),
                self._queue.qsize(),
                self._max_queue_size,
            )
            return True

        except asyncio.TimeoutError:
            self._queue_full_count += 1
            self._dropped_events += 1
            logger.warning(
                "EventBus: queue full, dropped event '%s' (queue_size=%d/%d, total_dropped=%d)",
                event,
                self._queue.qsize(),
                self._max_queue_size,
                self._dropped_events,
            )
            return False

    async def emit_verified_submission_sent(
        self,
        *,
        receipt: Any,
        submission_id: UUID | str,
        organization_id: UUID | str,
        timeout: float | None = 1.0,
    ) -> bool:
        """Emit submission.sent only when receipt fields match a persisted row."""
        from app.core.approval_flow import VerifiedJobApplicationReceipt

        owner = _canonical_organization_id(organization_id)
        persisted_id = _canonical_organization_id(submission_id)
        if (
            owner is None
            or persisted_id is None
            or type(receipt) is not VerifiedJobApplicationReceipt
            or receipt.organization_id != UUID(owner)
            or receipt.opportunity_id is not None
            and not isinstance(receipt.opportunity_id, UUID)
            or not isinstance(receipt.provider, str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", receipt.provider)
            or not isinstance(receipt.external_reference, str)
            or not re.fullmatch(r"[!-~]{1,256}", receipt.external_reference)
            or not isinstance(receipt.sent_at, datetime)
            or receipt.sent_at.utcoffset() is None
        ):
            raise DeliverySuccessReplayError("Verified persisted submission required")

        from app.database import AsyncSessionLocal
        from app.models.submission import Submission

        async with AsyncSessionLocal() as db:
            persisted = await db.get(Submission, UUID(persisted_id))
        try:
            stored_receipt = json.loads(persisted.outcome_notes or "") if persisted else {}
        except (TypeError, ValueError):
            stored_receipt = {}
        if not isinstance(stored_receipt, dict):
            stored_receipt = {}
        persisted_opportunity = (
            _canonical_organization_id(persisted.opportunity_id)
            if persisted is not None and persisted.opportunity_id is not None
            else None
        )
        persisted_sent_at = persisted.sent_at if persisted is not None else None
        if isinstance(persisted_sent_at, datetime):
            persisted_sent_at = (
                persisted_sent_at.replace(tzinfo=UTC)
                if persisted_sent_at.tzinfo is None
                else persisted_sent_at.astimezone(UTC)
            )
        receipt_sent_at = receipt.sent_at.astimezone(UTC)
        receipt_opportunity = (
            _canonical_organization_id(receipt.opportunity_id)
            if receipt.opportunity_id is not None
            else None
        )
        if not (
            persisted is not None
            and persisted.type == "application"
            and persisted.status == "sent"
            and not persisted.is_deleted
            and _canonical_organization_id(persisted.id) == persisted_id
            and _canonical_organization_id(persisted.organization_id) == owner
            and persisted_opportunity == receipt_opportunity
            and receipt.organization_id == UUID(owner)
            and receipt.opportunity_id == (
                UUID(persisted_opportunity) if persisted_opportunity else None
            )
            and persisted_sent_at == receipt_sent_at
            and stored_receipt.get("provider") == receipt.provider
            and stored_receipt.get("external_reference") == receipt.external_reference
        ):
            raise DeliverySuccessReplayError("Verified persisted submission required")

        return await self._enqueue_event(
            "submission.sent",
            {
                "submission_id": persisted_id,
                "opportunity_id": persisted_opportunity,
            },
            timeout,
            owner,
        )
    
    async def emit_domain_event(self, domain_event: Any) -> None:
        """
        Emit a typed Domain Event.
        
        This method accepts a DomainEvent instance and converts it to
        the event bus format for backward compatibility.
        
        Args:
            domain_event: Instance of a DomainEvent class
        """
        from app.core.domain_events import DomainEvent
        
        if not isinstance(domain_event, DomainEvent):
            raise TypeError(f"Expected DomainEvent, got {type(domain_event)}")
        
        event_name = domain_event.event_type()
        if _is_delivery_success_event(event_name):
            raise DeliverySuccessReplayError(
                "Delivery success events require their original trusted producer"
            )
        payload = domain_event.to_dict()
        dispatch_payload = {
            **payload,
            **payload.get("data", {}),
        }

        await self.emit(event_name, dispatch_payload)
        
        logger.debug(
            "EventBus: emitted domain event '%s' of type %s",
            event_name,
            domain_event.__class__.__name__,
        )

    async def _process_event(
        self,
        event: str,
        payload: EventPayload,
        organization_id: str | None = None,
        *,
        auth_context: Any = None,
    ) -> None:
        """Process a single event by calling all registered handlers."""
        handlers = self._handlers.get(event, [])
        if not handlers:
            logger.debug(f"EventBus: no handlers for '{event}'")
            return

        if organization_id is None:
            organization_id = _trusted_event_organization_id(payload, auth_context)
        else:
            organization_id = _canonical_organization_id(organization_id)
            if organization_id is None or not _payload_organization_matches(
                payload, organization_id
            ):
                organization_id = None
        for handler in handlers:
            handler_name = getattr(handler, "__name__", handler.__class__.__name__)
            try:
                result = handler(payload)
                if inspect.isawaitable(result):
                    await result
                logger.debug(f"EventBus: handler {handler_name} completed for '{event}'")
            except Exception as exc:
                logger.error(
                    "EventBus: handler %s failed for '%s': %s",
                    handler_name, event, exc, exc_info=True
                )
                self._failed_events.append((event, payload, str(exc)))
                self._failed_event_organizations.append(organization_id)
                if len(self._failed_events) > 100:
                    self._failed_events.pop(0)
                    self._failed_event_organizations.pop(0)

    async def start_processing(self) -> None:
        """Start processing events from the queue with graceful shutdown support."""
        self._running = True
        self._processing_tasks = set()
        logger.info("EventBus: processing loop started")
        
        while self._running or not self._queue.empty():
            try:
                # If we're stopping and queue is empty, exit immediately
                if not self._running and self._queue.empty():
                    break

                # Wait for an item with a timeout to allow checking self._running
                try:
                    event, payload, organization_id = await asyncio.wait_for(
                        self._queue.get(), timeout=0.5
                    )
                except (asyncio.TimeoutError, TimeoutError):
                    continue
                
                # Create task for processing
                task = asyncio.create_task(
                    self._process_event(event, payload, organization_id)
                )
                self._processing_tasks.add(task)
                task.add_done_callback(self._processing_tasks.discard)
                
                # Mark queue item as done immediately after creating task
                self._queue.task_done()
                
            except RuntimeError as e:
                if "no running event loop" in str(e) or "Event loop is closed" in str(e):
                    logger.debug("EventBus: loop closing, stopping processing")
                    break
                logger.error("EventBus: runtime error: %s", e)
                break
            except Exception as exc:
                logger.error("EventBus: processing loop error: %s", exc, exc_info=True)
                if not self._running:
                    break
        
        # Wait for all processing tasks to complete
        if self._processing_tasks:
            logger.info(f"EventBus: waiting for {len(self._processing_tasks)} tasks to complete")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._processing_tasks, return_exceptions=True),
                    timeout=self._shutdown_timeout
                )
            except (asyncio.TimeoutError, TimeoutError):
                logger.warning(
                    f"EventBus: shutdown timeout ({self._shutdown_timeout}s) exceeded, "
                    f"{len(self._processing_tasks)} tasks still running"
                )
                raise
        
        logger.info("EventBus: processing loop stopped gracefully")

    def stop(self) -> None:
        """Stop processing events (gracefully waits for current tasks)."""
        logger.info("EventBus: stop requested")
        self._running = False
        # Note: Actual waiting happens in start_processing() loop

    def get_event_stats(self) -> dict[str, int]:
        return dict(self._stats)

    def get_event_stats_for_organization(
        self, organization_id: UUID | str | None
    ) -> dict[str, int]:
        """Return counters bound to one authenticated organization."""
        tenant = _canonical_organization_id(organization_id)
        if tenant is None:
            return {}
        return dict(self._organization_stats.get(tenant, {}))
    
    def get_queue_metrics(self) -> dict[str, int]:
        """Get queue metrics for monitoring."""
        return {
            "queue_size": self._queue.qsize(),
            "max_queue_size": self._max_queue_size,
            "queue_full_count": self._queue_full_count,
            "dropped_events": self._dropped_events,
            "queue_utilization_percent": int((self._queue.qsize() / self._max_queue_size) * 100),
        }
    
    def get_failed_events(self) -> list[tuple[str, EventPayload, str]]:
        """Get all failed events for trusted internal health checks."""
        return self._failed_events.copy()

    def get_failed_events_for_organization(
        self, organization_id: UUID | str | None
    ) -> list[tuple[str, EventPayload, str]]:
        """Return only failures tagged for this authenticated tenant."""
        tenant = _canonical_organization_id(organization_id)
        if tenant is None or len(self._failed_event_organizations) != len(self._failed_events):
            return []
        return [
            entry for entry, owner in zip(self._failed_events, self._failed_event_organizations)
            if owner == tenant
        ]

    def remove_failed_event_for_organization(
        self, index: int, organization_id: UUID | str | None
    ) -> bool:
        """Remove a tenant-visible DLQ entry by its scoped index."""
        tenant = _canonical_organization_id(organization_id)
        visible = self.get_failed_events_for_organization(tenant)
        if tenant is None or index < 0 or index >= len(visible):
            return False
        target = visible[index]
        for stored_index, (entry, owner) in enumerate(
            zip(self._failed_events, self._failed_event_organizations)
        ):
            if owner == tenant and entry is target:
                self._failed_events.pop(stored_index)
                self._failed_event_organizations.pop(stored_index)
                return True
        return False

    def clear_failed_events_for_organization(
        self, organization_id: UUID | str | None
    ) -> int:
        """Clear only failures tagged for this authenticated tenant."""
        tenant = _canonical_organization_id(organization_id)
        if tenant is None or len(self._failed_event_organizations) != len(self._failed_events):
            return 0
        indexes = [
            index for index, owner in enumerate(self._failed_event_organizations)
            if owner == tenant
        ]
        for index in reversed(indexes):
            self._failed_events.pop(index)
            self._failed_event_organizations.pop(index)
        return len(indexes)
    
    async def replay_event(
        self,
        event: str,
        payload: EventPayload,
        *,
        auth_context: Any = None,
    ) -> None:
        """Replay ordinary events; delivery success requires its original trusted producer."""
        # DLQ payloads (including receipt-shaped fields) are not persisted provider proof.
        if _is_delivery_success_event(event):
            raise DeliverySuccessReplayError("Delivery success events cannot be replayed")
        if auth_context is None:
            await self.emit(event, payload)
        else:
            await self.emit(event, payload, auth_context=auth_context)

    def reset(self) -> None:
        """
        Clear in-memory handlers and counters. Intended for deterministic tests.
        
        SECURITY: This method should NEVER be called in production as it will:
        - Clear all event handlers (breaking event processing)
        - Clear event statistics (losing monitoring data)
        - Clear failed events queue (losing error tracking)
        - Reset the event queue (dropping pending events)
        
        Raises:
            RuntimeError: If called in production environment
        """
        # Production guard: Prevent accidental reset in production
        try:
            from app.config import settings
            if settings.APP_ENV.lower() == "production":
                raise RuntimeError(
                    "EventBus.reset() cannot be called in production environment. "
                    "This method is intended for testing only and will clear all "
                    "event handlers, statistics, and pending events."
                )
        except ImportError:
            # If settings not available, allow reset (e.g., during testing)
            pass
        
        logger.warning(
            "EventBus.reset() called - clearing all handlers, stats, and queue. "
            "This should only happen in tests!"
        )
        
        self._handlers = defaultdict(list)
        self._stats = defaultdict(int)
        self._organization_stats = defaultdict(lambda: defaultdict(int))
        self._failed_events = []
        self._failed_event_organizations = []
        self._queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._queue_full_count = 0
        self._dropped_events = 0


def _create_global_event_bus() -> EventBus:
    """Create the global event bus instance with configuration from settings."""
    try:
        from app.config import settings
        return EventBus(
            shutdown_timeout=settings.EVENT_BUS_SHUTDOWN_TIMEOUT,
            max_queue_size=settings.EVENT_BUS_MAX_QUEUE_SIZE,
        )
    except Exception:
        # Fallback to default if settings not available (e.g., during import)
        return EventBus()


event_bus = _create_global_event_bus()
