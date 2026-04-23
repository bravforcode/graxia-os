
from app.tasks.base import execute_managed_async_task, idempotent_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import DEFAULT_QUEUE


async def run_leadgen() -> dict[str, object]:
    from app.agents.lead_list_builder import lead_list_builder_agent

    return await lead_list_builder_agent.run()


@celery_app.task(name="tasks.leadgen.run", queue=DEFAULT_QUEUE)
@idempotent_task("{task_name}:{date}", lock_ttl=3600)
def leadgen_task():
    return execute_managed_async_task(
        task_name="leadgen",
        queue=DEFAULT_QUEUE,
        coroutine_factory=run_leadgen,
    )

