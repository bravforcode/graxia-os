
from app.tasks.base import execute_managed_async_task, idempotent_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import BACKGROUND_QUEUE


async def sync_contacts_to_crm() -> dict[str, object]:
    from sqlalchemy import desc, select

    from app.database import AsyncSessionLocal
    from app.integrations.hubspot import hubspot_client
    from app.integrations.salesforce import salesforce_client
    from app.models.contact import Contact

    hubspot = 0
    salesforce = 0

    async with AsyncSessionLocal() as db:
        contacts = list(
            (
                await db.execute(
                    select(Contact)
                    .where(Contact.is_deleted.is_(False))
                    .where(Contact.email.is_not(None))
                    .where(Contact.email != "")
                    .order_by(desc(Contact.value_score), Contact.created_at.desc())
                    .limit(200)
                )
            )
            .scalars()
            .all()
        )

    for contact in contacts:
        email = (contact.email or "").strip().lower()
        if not email:
            continue
        props = {
            "firstname": (contact.name or "").split(" ")[0],
            "lastname": " ".join((contact.name or "").split(" ")[1:]) or (contact.company or ""),
            "company": contact.company or "",
            "jobtitle": contact.role or "",
        }
        try:
            if await hubspot_client.upsert_contact(email=email, properties=props):
                hubspot += 1
        except Exception:
            pass
        try:
            fields = {
                "Company": contact.company or "Unknown",
                "LastName": contact.name or "Unknown",
                "Title": contact.role or "",
            }
            if await salesforce_client.upsert_lead(email=email, fields=fields):
                salesforce += 1
        except Exception:
            pass

    return {"hubspot": hubspot, "salesforce": salesforce}


@celery_app.task(name="tasks.crm.sync", queue=BACKGROUND_QUEUE)
@idempotent_task("{task_name}:{date}", lock_ttl=7200)
def crm_sync_task():
    return execute_managed_async_task(
        task_name="crm_sync",
        queue=BACKGROUND_QUEUE,
        coroutine_factory=sync_contacts_to_crm,
    )

