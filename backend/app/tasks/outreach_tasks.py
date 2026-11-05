
from app.tasks.celery_app import celery_app
from app.tasks.queues import DEFAULT_QUEUE


async def run_outreach_email() -> dict[str, object]:
    from app.agents.outreach_agent import outreach_agent

    return await outreach_agent.run()


@celery_app.task(name="tasks.outreach.email", queue=DEFAULT_QUEUE)
def outreach_email_task():
    """Fail closed until a persisted owner context can reach this task."""
    return {"status": "disabled", "reason": "trusted_auth_context_required"}

