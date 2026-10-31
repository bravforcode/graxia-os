"""Morning briefing delivery remains disabled until tenant-safe delivery exists."""

from app.tasks.celery_app import celery_app
from app.tasks.queues import DEFAULT_QUEUE


def _disabled_result(
    organization_id: str | None,
    telegram_user_id: str | None,
    telegram_chat_id: str | None,
) -> dict[str, str]:
    if not all((organization_id, telegram_user_id, telegram_chat_id)):
        return {
            "status": "disabled",
            "reason": "tenant_and_authorized_recipient_required",
        }
    return {"status": "disabled", "reason": "tenant_scoped_delivery_not_enabled"}


async def send_morning_briefing(
    organization_id: str | None = None,
    telegram_user_id: str | None = None,
    telegram_chat_id: str | None = None,
) -> dict[str, str]:
    """Fail closed; the current briefing generator has no tenant scope."""
    return _disabled_result(organization_id, telegram_user_id, telegram_chat_id)


@celery_app.task(name="tasks.morning_briefing.run", queue=DEFAULT_QUEUE)
def morning_briefing_task(
    organization_id: str | None = None,
    telegram_user_id: str | None = None,
    telegram_chat_id: str | None = None,
) -> dict[str, str]:
    """Keep already-queued invocations registered but prevent all delivery."""
    return _disabled_result(organization_id, telegram_user_id, telegram_chat_id)
