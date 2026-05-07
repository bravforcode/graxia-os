"""
Contact Command and Query Handlers
"""
import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.core.result import Result, err, ok
from app.cqrs.commands import CreateContactCommand
from app.cqrs.handlers import CommandHandler, QueryHandler
from app.cqrs.queries import GetContactQuery, ListContactsQuery
from app.core.unit_of_work import AsyncUnitOfWork
from app.models.contact import Contact
from app.repositories.contact_repository import ContactRepository

logger = logging.getLogger(__name__)


# Command Handlers
class CreateContactHandler(CommandHandler[CreateContactCommand, Contact]):
    """Handler for creating contacts."""
    
    async def handle(self, command: CreateContactCommand) -> Result[Contact, Exception]:
        """Create new contact."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = ContactRepository(session)
                
                # Create contact
                contact = Contact(
                    id=uuid4(),
                    name=command.name,
                    email=command.email,
                    company=command.company,
                    role=command.role,
                    linkedin_url=command.linkedin_url,
                    twitter_handle=command.twitter_handle,
                    notes=command.notes,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                
                # Save
                contact = await repo.add(contact)

                
                # Emit event
                from app.core.event_bus import event_bus
                await event_bus.emit("contact.created", {
                    "contact_id": str(contact.id),
                    "name": contact.name,
                    "email": contact.email,
                })
                
                logger.info(f"Created contact: {contact.id}")
                return ok(contact)
                
        except Exception as e:
            logger.error(f"Failed to create contact: {e}")
            return err(e)


# Query Handlers
class GetContactHandler(QueryHandler[GetContactQuery, Contact]):
    """Handler for getting contact by ID."""
    
    async def handle(self, query: GetContactQuery) -> Result[Contact, Exception]:
        """Get contact."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = ContactRepository(session)
                contact = await repo.get_by_id(query.contact_id)
                
                if not contact:
                    return err(ValueError(f"Contact not found: {query.contact_id}"))
                
                return ok(contact)
                
        except Exception as e:
            logger.error(f"Failed to get contact: {e}")
            return err(e)


class ListContactsHandler(QueryHandler[ListContactsQuery, list]):
    """Handler for listing contacts."""
    
    async def handle(self, query: ListContactsQuery) -> Result[list, Exception]:
        """List contacts."""
        try:
            async with AsyncUnitOfWork() as uow:
                session = uow.session
                repo = ContactRepository(session)
                
                # Get contacts
                contacts = await repo.get_all(query.skip, query.limit)
                
                return ok(contacts)
                
        except Exception as e:
            logger.error(f"Failed to list contacts: {e}")
            return err(e)
