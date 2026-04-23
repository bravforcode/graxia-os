
from app.tasks.base import execute_managed_async_task, idempotent_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import DEFAULT_QUEUE


async def run_outreach_email() -> dict[str, object]:
    from app.agents.outreach_agent import outreach_agent

    return await outreach_agent.run()


@celery_app.task(name="tasks.outreach.email", queue=DEFAULT_QUEUE)
@idempotent_task("{task_name}:{date}", lock_ttl=3600)
def outreach_email_task():
    return execute_managed_async_task(
        task_name="outreach_email",
        queue=DEFAULT_QUEUE,
        coroutine_factory=run_outreach_email,
    )

