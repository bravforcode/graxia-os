"""Single-use fulfillment intent, using the existing migration-021 table."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import re
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.models.delivery_email_event import DeliveryEmailEvent
from app.models.funnel import FunnelOrder, DeliveryAccess

CONTRACT = "fulfillment-email-v1"
WIN_BACK_CONTRACT = "win-back-email-v1"
WIN_BACK_COOLDOWN = timedelta(days=7)


@dataclass(frozen=True)
class DeliveryEmailClaim:
    id: UUID
    organization_id: UUID
    order_id: UUID
    key: str
    acquired: bool
    outcome: str = "unknown"
    provider_reference: str | None = None


@dataclass(frozen=True)
class WinBackEmailClaim:
    id: UUID
    organization_id: UUID
    order_id: UUID
    key: str
    email_digest: str
    acquired: bool
    outcome: str = "unknown"
    provider_reference: str | None = None


class DeliveryEmailAttemptStore:
    def __init__(self, session_factory=None):
        if session_factory is None:
            from app.database import AsyncSessionLocal
            session_factory = AsyncSessionLocal
        self.session_factory = session_factory

    @staticmethod
    def _existing(row, email):
        data = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        ref = data.get("provider_reference")
        outcome = "unknown"
        if (data.get("contract") == CONTRACT and row.provider == "resend"
                and row.customer_email == email):
            if (row.status == "sent" and data.get("outcome") == "sent" and row.sent_at is not None
                    and isinstance(ref, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", ref)):
                outcome = "sent"
            elif row.status == "skipped" and data.get("outcome") == "suppressed":
                outcome = "suppressed"
        return DeliveryEmailClaim(row.id, row.organization_id, row.order_id, row.idempotency_key,
                                  False, outcome, ref if outcome == "sent" else None)

    async def claim(self, organization_id, order_id, customer_email, access_ids):
        if (not isinstance(organization_id, UUID) or not organization_id.int
                or not isinstance(order_id, UUID) or not order_id.int
                or not isinstance(customer_email, str) or not customer_email or len(customer_email) > 255
                or not access_ids or any(not isinstance(item, UUID) or not item.int for item in access_ids)
                or len(set(access_ids)) != len(access_ids)):
            raise ValueError("delivery_attempt_identity_required")
        async with self.session_factory() as db:
            session_id = await db.scalar(select(FunnelOrder.stripe_session_id).where(
                FunnelOrder.id == order_id, FunnelOrder.organization_id == organization_id,
                FunnelOrder.status == "paid", FunnelOrder.customer_email == customer_email,
            ))
            owned_accesses = (await db.scalars(select(DeliveryAccess.id).where(
                DeliveryAccess.id.in_(access_ids), DeliveryAccess.organization_id == organization_id,
                DeliveryAccess.order_id == order_id, DeliveryAccess.status == "active",
            ))).all()
            if set(owned_accesses) != set(access_ids):
                raise ValueError("delivery_attempt_owned_paid_access_required")
            if (not isinstance(session_id, str) or not session_id.strip()
                    or session_id != session_id.strip() or len(session_id) > 255):
                raise ValueError("delivery_attempt_persisted_session_required")
            key = f"funnel_delivery_session:{organization_id}:" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()
            # Any historical intent for this owned order is also non-retryable.
            existing = await db.scalar(select(DeliveryEmailEvent).where(
                DeliveryEmailEvent.organization_id == organization_id,
                DeliveryEmailEvent.order_id == order_id,
                or_(
                    DeliveryEmailEvent.metadata_json["contract"].as_string().is_(None),
                    DeliveryEmailEvent.metadata_json["contract"].as_string() != WIN_BACK_CONTRACT,
                ),
            ).order_by(DeliveryEmailEvent.created_at).limit(1))
            if existing is not None:
                return self._existing(existing, customer_email)
            claim_id = uuid4()
            row = DeliveryEmailEvent(id=claim_id, organization_id=organization_id, order_id=order_id,
                delivery_access_id=access_ids[0],
                customer_email=customer_email, provider="resend", status="pending", idempotency_key=key,
                metadata_json={"contract": CONTRACT, "outcome": "pending"})
            db.add(row)
            try:
                await db.commit()  # Provider must not be called until this succeeds.
            except IntegrityError:
                await db.rollback()
                existing = await db.scalar(select(DeliveryEmailEvent).where(
                    DeliveryEmailEvent.organization_id == organization_id,
                    DeliveryEmailEvent.idempotency_key == key,
                ))
                if existing is None:
                    raise RuntimeError("delivery_attempt_claim_unavailable")
                if existing.order_id != order_id:
                    # The session already belongs to another order's intent. Never
                    # return its receipt or grant a second provider invocation.
                    return DeliveryEmailClaim(claim_id, organization_id, order_id, key, False)
                return self._existing(existing, customer_email)
            return DeliveryEmailClaim(claim_id, organization_id, order_id, key, True)

    async def finish(self, claim, outcome, provider_reference=None):
        if type(claim) is not DeliveryEmailClaim or claim.acquired is not True:
            raise ValueError("delivery_attempt_claim_required")
        if outcome not in {"sent", "suppressed", "unknown"}:
            raise ValueError("delivery_attempt_outcome_invalid")
        if outcome == "sent":
            if not isinstance(provider_reference, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", provider_reference):
                raise ValueError("delivery_attempt_receipt_required")
        elif provider_reference is not None:
            raise ValueError("unaccepted_delivery_attempt_reference")
        data = {"contract": CONTRACT, "outcome": outcome}
        if outcome == "sent":
            data["provider_reference"] = provider_reference
        async with self.session_factory() as db:
            result = await db.execute(update(DeliveryEmailEvent).where(
                DeliveryEmailEvent.id == claim.id,
                DeliveryEmailEvent.organization_id == claim.organization_id,
                DeliveryEmailEvent.order_id == claim.order_id,
                DeliveryEmailEvent.idempotency_key == claim.key,
                DeliveryEmailEvent.status == "pending",
                DeliveryEmailEvent.metadata_json["outcome"].as_string() == "pending",
            ).values(status="sent" if outcome == "sent" else "skipped" if outcome == "suppressed" else "pending",
                     metadata_json=data, sent_at=datetime.now(UTC) if outcome == "sent" else None,
                     error_code="provider_outcome_unknown" if outcome == "unknown" else None,
                     error_message_redacted=None).returning(DeliveryEmailEvent.id))
            if result.scalar_one_or_none() is None:
                raise RuntimeError("delivery_attempt_completion_not_owned")
            await db.commit()  # Uncertain commit is never replayed here.

    @staticmethod
    def _win_back_receipt(row, email_digest):
        data = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        reference = data.get("provider_reference")
        outcome = "unknown"
        if (data.get("contract") == WIN_BACK_CONTRACT
                and data.get("email_digest") == email_digest
                and row.provider == "resend"):
            if (row.status == "skipped" and data.get("outcome") == "suppressed"):
                outcome = "suppressed"
            elif (row.status == "sent" and data.get("outcome") == "sent"
                  and row.sent_at is not None and isinstance(reference, str)
                  and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", reference)):
                outcome = "sent"
        return WinBackEmailClaim(
            row.id, row.organization_id, row.order_id, row.idempotency_key,
            email_digest, False, outcome,
            reference if outcome == "sent" else None,
        )

    async def claim_win_back(
        self, organization_id, order_id, customer_email, now=None, cooldown=WIN_BACK_COOLDOWN
    ):
        """Commit a recipient-scoped intent before a win-back provider call.

        Only accepted receipts start a new cooldown cycle. Pending or malformed
        receipts block retries indefinitely because provider acceptance may be
        ambiguous.
        """
        if (not isinstance(organization_id, UUID) or not organization_id.int
                or not isinstance(order_id, UUID) or not order_id.int
                or not isinstance(customer_email, str) or not customer_email.strip()
                or len(customer_email) > 255
                or not isinstance(cooldown, timedelta) or cooldown <= timedelta(0)):
            raise ValueError("win_back_identity_required")

        normalized_email = customer_email.strip().casefold()
        email_digest = hashlib.sha256(normalized_email.encode("utf-8")).hexdigest()
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise ValueError("win_back_current_time_must_be_aware")
        current = current.astimezone(UTC)

        async with self.session_factory() as db:
            latest = (await db.execute(
                select(FunnelOrder.id, FunnelOrder.paid_at).where(
                    FunnelOrder.organization_id == organization_id,
                    FunnelOrder.status == "paid",
                    FunnelOrder.customer_email.isnot(None),
                    FunnelOrder.paid_at.isnot(None),
                    func.lower(func.trim(FunnelOrder.customer_email)) == normalized_email,
                ).order_by(FunnelOrder.paid_at.desc(), FunnelOrder.id.desc()).limit(1)
            )).one_or_none()
            if latest is None or latest.id != order_id:
                raise ValueError("win_back_latest_paid_order_required")
            paid_at = latest.paid_at
            if paid_at.tzinfo is None:
                paid_at = paid_at.replace(tzinfo=UTC)
            if paid_at.astimezone(UTC) >= current - timedelta(days=30):
                raise ValueError("win_back_order_not_eligible")

            rows = (await db.scalars(select(DeliveryEmailEvent).where(
                DeliveryEmailEvent.organization_id == organization_id,
                DeliveryEmailEvent.provider == "resend",
                DeliveryEmailEvent.idempotency_key.startswith(
                    f"win_back:{organization_id}:{email_digest}:", autoescape=True
                ),
            ))).all()
            receipts = [
                row for row in rows
                if isinstance(row.metadata_json, dict)
                and row.metadata_json.get("contract") == WIN_BACK_CONTRACT
                and row.metadata_json.get("email_digest") == email_digest
            ]

            # Any in-flight, malformed, or failed state is ambiguous and blocks
            # another send; only an explicit accepted receipt can age out.
            accepted = []
            for row in receipts:
                if row.status == "pending":
                    return self._win_back_receipt(row, email_digest)
                receipt = self._win_back_receipt(row, email_digest)
                if receipt.outcome == "sent":
                    accepted.append(row)
                elif row.status != "skipped" or receipt.outcome != "suppressed":
                    return self._win_back_receipt(row, email_digest)

            last_accepted = max(
                accepted,
                key=lambda row: (row.sent_at, str(row.id)),
                default=None,
            )
            if last_accepted is not None:
                last_sent_at = last_accepted.sent_at
                if last_sent_at.tzinfo is None:
                    last_sent_at = last_sent_at.replace(tzinfo=UTC)
                if last_sent_at.astimezone(UTC) >= current - cooldown:
                    return self._win_back_receipt(last_accepted, email_digest)
                cycle = f"receipt:{last_accepted.id}"
            else:
                cycle = f"order:{order_id}"

            key = f"win_back:{organization_id}:{email_digest}:{cycle}"
            claim_id = uuid4()
            row = DeliveryEmailEvent(
                id=claim_id,
                organization_id=organization_id,
                order_id=order_id,
                delivery_access_id=None,
                customer_email=customer_email.strip(),
                provider="resend",
                status="pending",
                idempotency_key=key,
                metadata_json={
                    "contract": WIN_BACK_CONTRACT,
                    "outcome": "pending",
                    "email_digest": email_digest,
                    "cycle": cycle,
                },
            )
            db.add(row)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                existing = await db.scalar(select(DeliveryEmailEvent).where(
                    DeliveryEmailEvent.organization_id == organization_id,
                    DeliveryEmailEvent.idempotency_key == key,
                ))
                if existing is None:
                    raise RuntimeError("win_back_claim_unavailable")
                return self._win_back_receipt(existing, email_digest)
            return WinBackEmailClaim(
                claim_id, organization_id, order_id, key, email_digest, True, "unknown"
            )

    async def finish_win_back(self, claim, outcome, provider_reference=None):
        if type(claim) is not WinBackEmailClaim or claim.acquired is not True:
            raise ValueError("win_back_claim_required")
        if outcome not in {"sent", "suppressed", "unknown"}:
            raise ValueError("win_back_outcome_invalid")
        if outcome == "sent":
            if (not isinstance(provider_reference, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", provider_reference)):
                raise ValueError("win_back_provider_receipt_required")
        elif provider_reference is not None:
            raise ValueError("unaccepted_win_back_reference")

        if outcome == "suppressed":
            async with self.session_factory() as db:
                result = await db.execute(delete(DeliveryEmailEvent).where(
                    DeliveryEmailEvent.id == claim.id,
                    DeliveryEmailEvent.organization_id == claim.organization_id,
                    DeliveryEmailEvent.order_id == claim.order_id,
                    DeliveryEmailEvent.idempotency_key == claim.key,
                    DeliveryEmailEvent.status == "pending",
                    DeliveryEmailEvent.metadata_json["contract"].as_string() == WIN_BACK_CONTRACT,
                    DeliveryEmailEvent.metadata_json["outcome"].as_string() == "pending",
                ).returning(DeliveryEmailEvent.id))
                if result.scalar_one_or_none() is None:
                    raise RuntimeError("win_back_claim_release_not_owned")
                await db.commit()
            return

        metadata = {
            "contract": WIN_BACK_CONTRACT,
            "outcome": "sent" if outcome == "sent" else "unknown",
            "email_digest": claim.email_digest,
            "cycle": ":".join(claim.key.split(":")[-2:]),
        }
        if outcome == "sent":
            metadata["provider_reference"] = provider_reference
        async with self.session_factory() as db:
            result = await db.execute(update(DeliveryEmailEvent).where(
                DeliveryEmailEvent.id == claim.id,
                DeliveryEmailEvent.organization_id == claim.organization_id,
                DeliveryEmailEvent.order_id == claim.order_id,
                DeliveryEmailEvent.idempotency_key == claim.key,
                DeliveryEmailEvent.status == "pending",
                DeliveryEmailEvent.metadata_json["contract"].as_string() == WIN_BACK_CONTRACT,
                DeliveryEmailEvent.metadata_json["outcome"].as_string() == "pending",
            ).values(
                status="sent" if outcome == "sent" else "pending",
                metadata_json=metadata,
                sent_at=datetime.now(UTC) if outcome == "sent" else None,
                error_code="provider_outcome_unknown" if outcome == "unknown" else None,
                error_message_redacted=None,
            ).returning(DeliveryEmailEvent.id))
            if result.scalar_one_or_none() is None:
                raise RuntimeError("win_back_completion_not_owned")
            await db.commit()
