"""
Network Builder Agent

Discovers and manages professional contacts, builds network graph,
and generates personalized outreach messages.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from app.agents.base import BaseAgent
from app.core.openclaw import openclaw_client, OpenClawRateLimitError
from app.core.time_utils import business_today
from app.database import AsyncSessionLocal
from app.models.contact import Contact
from app.models.network_interaction import NetworkInteraction
from sqlalchemy import func, select

logger = logging.getLogger(__name__)


class NetworkBuilderAgent(BaseAgent):
    """
    Network Builder Agent - discovers and manages professional contacts.
    
    Features:
    - LinkedIn profile scraping
    - Contact value scoring (0-10)
    - Relationship strength tracking (0.0-1.0)
    - Network graph analysis (bridge nodes, clusters)
    - Personalized outreach generation
    
    Target: 10+ quality contacts/month
    Rate limit: 20 requests/day (via OpenClaw)
    """
    
    name = "network_builder"
    
    async def discover_contacts(
        self,
        search_url: str,
        max_contacts: int = 10
    ) -> dict:
        """
        Discover contacts from LinkedIn search results.
        
        Args:
            search_url: LinkedIn search URL
            max_contacts: Maximum contacts to discover
        
        Returns:
            dict with discovered, new, existing counts
        """
        logger.info(f"NetworkBuilder: discovering contacts from {search_url}")
        
        discovered = 0
        new_contacts = 0
        existing = 0
        
        try:
            # Scrape contacts using OpenClaw
            contacts_data = await openclaw_client.extract_contacts(
                url=search_url,
                platform="linkedin",
                use_cache=True
            )
            
            for contact_data in contacts_data[:max_contacts]:
                discovered += 1
                
                # Check if contact exists
                if await self._contact_exists(contact_data.get("profile_url")):
                    existing += 1
                    continue
                
                # Save new contact
                contact = await self._save_contact(contact_data)
                if contact:
                    new_contacts += 1
                    
                    # Score contact value
                    scored_contact = await self._score_contact(contact)
                    
                    # Emit event
                    await self.bus.emit("contact.discovered", {
                        "contact_id": str(contact.id),
                        "name": contact.name,
                        "title": (scored_contact.role if scored_contact else contact.role),
                        "company": contact.company,
                        "value_score": (
                            float(scored_contact.value_score)
                            if scored_contact and scored_contact.value_score
                            else 0.0
                        ),
                    })
        except OpenClawRateLimitError:
            logger.warning("NetworkBuilder: OpenClaw rate limit reached")
        except Exception as e:
            logger.error(f"NetworkBuilder: discovery failed: {e}")
        
        result = {
            "discovered": discovered,
            "new": new_contacts,
            "existing": existing
        }
        
        await self.log_audit(
            action="network_builder.discover",
            details=result,
            success=True
        )
        
        return result
    
    async def _contact_exists(self, profile_url: Optional[str]) -> bool:
        """Check if contact already exists."""
        if not profile_url:
            return False
        
        try:
            async with AsyncSessionLocal() as db:
                query = select(Contact).where(
                    Contact.linkedin_url == profile_url,
                    Contact.is_deleted.is_(False),
                )
                result = await db.execute(query)
                return result.scalar_one_or_none() is not None
        except Exception:
            return False
    
    async def _save_contact(self, contact_data: dict) -> Optional[Contact]:
        """Save contact to database."""
        try:
            async with AsyncSessionLocal() as db:
                contact = Contact(
                    id=uuid4(),
                    name=contact_data.get("name"),
                    email=contact_data.get("email"),
                    role=contact_data.get("title"),
                    company=contact_data.get("company"),
                    met_at=contact_data.get("location"),
                    linkedin_url=contact_data.get("profile_url"),
                    relationship_strength=1,
                    last_contacted_at=None,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                
                db.add(contact)
                await db.commit()
                await db.refresh(contact)
                
                logger.info(f"Saved contact: {contact.name}")
                return contact
        except Exception as e:
            logger.error(f"Failed to save contact: {e}")
            return None
    
    async def _score_contact(self, contact: Contact) -> Contact:
        """
        Score contact value (0-10).
        
        Scoring factors:
        - Relevance to goals (40%)
        - Influence/reach (30%)
        - Mutual connections (20%)
        - Engagement potential (10%)
        """
        try:
            user_context = self.agent_context
            
            system = """You are a network value analyzer. Score contacts 0-10 based on:
- Relevance (40%): How relevant to user's goals?
- Influence (30%): How influential in their field?
- Connections (20%): Potential for mutual connections?
- Engagement (10%): Likelihood of positive response?

Return JSON: {"score": 8.0, "summary": "High value because...", "outreach_angle": "Mention shared interest in..."}"""
            
            user = f"""User Profile:
{user_context}

Contact:
Name: {contact.name}
Title: {contact.role}
Company: {contact.company}
Location: {contact.met_at}

Score this contact."""
            
            result = await self.llm.complete_json(
                system=system,
                user=user,
                task_class="classification",
                complexity=3
            )
            
            # Update contact with score
            async with AsyncSessionLocal() as db:
                query = select(Contact).where(Contact.id == contact.id)
                result_obj = await db.execute(query)
                contact_obj = result_obj.scalar_one_or_none()
                
                if contact_obj:
                    raw_score = float(result.get("score", 5.0))
                    contact_obj.value_score = max(1, min(10, round(raw_score)))
                    contact_obj.notes = result.get("summary")
                    
                    await db.commit()
                    await db.refresh(contact_obj)
                    
                    logger.info(f"Scored contact {contact.name}: {contact_obj.value_score}/10")
                    return contact_obj
        except Exception as e:
            logger.error(f"Contact scoring failed: {e}")
        return contact
    
    async def generate_outreach(
        self,
        contact_id: str,
        context: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate personalized outreach message.
        
        Args:
            contact_id: Contact UUID
            context: Additional context for outreach
        
        Returns:
            Personalized message or None
        """
        try:
            contact_uuid = UUID(contact_id)
            async with AsyncSessionLocal() as db:
                query = select(Contact).where(
                    Contact.id == contact_uuid,
                    Contact.is_deleted.is_(False),
                )
                result = await db.execute(query)
                contact = result.scalar_one_or_none()
                
                if not contact:
                    return None
                
                user_context = self.agent_context
                
                system = """You are a professional networking expert. Write personalized LinkedIn connection requests or messages.

Rules:
- Keep it under 300 characters for connection requests
- Be genuine and specific
- Mention shared interests or mutual value
- No generic templates
- Professional but warm tone"""
                
                user_msg = f"""User Profile:
{user_context}

Contact:
Name: {contact.name}
Title: {contact.role}
Company: {contact.company}
Notes: {contact.notes or 'None'}

Context: {context or 'General networking'}

Write a personalized outreach message."""
                
                message = await self.llm.complete(
                    system=system,
                    user=user_msg,
                    task_class="generation",
                    complexity=4,
                    max_tokens=300
                )
                
                # Log interaction
                if message:
                    await self._log_interaction(
                        contact_id=contact.id,
                        interaction_type="outreach_generated",
                        notes=f"Generated outreach message: {message[:100]}..."
                    )
                
                return message
        except ValueError:
            logger.error("Outreach generation failed: invalid contact id")
            return None
        except Exception as e:
            logger.error(f"Outreach generation failed: {e}")
            return None
    
    async def _log_interaction(
        self,
        contact_id: UUID,
        interaction_type: str,
        notes: Optional[str] = None
    ) -> None:
        """Log network interaction."""
        try:
            async with AsyncSessionLocal() as db:
                interaction = NetworkInteraction(
                    id=uuid4(),
                    contact_id=contact_id,
                    interaction_type=interaction_type,
                    interaction_at=datetime.now(timezone.utc),
                    notes=notes,
                    created_at=datetime.now(timezone.utc)
                )
                
                db.add(interaction)
                
                # Update contact's last interaction
                query = select(Contact).where(Contact.id == contact_id)
                result = await db.execute(query)
                contact = result.scalar_one_or_none()
                
                if contact:
                    contact.last_contacted_at = business_today()
                    current = int(contact.relationship_strength or 1)
                    contact.relationship_strength = min(5, current + 1)
                
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to log interaction: {e}")
    
    async def get_top_contacts(
        self,
        limit: int = 10,
        min_score: float = 7.0
    ) -> list[Contact]:
        """Get top-valued contacts."""
        try:
            async with AsyncSessionLocal() as db:
                query = (
                    select(Contact)
                    .where(Contact.value_score >= min_score)
                    .where(Contact.is_deleted.is_(False))
                    .order_by(Contact.value_score.desc())
                    .limit(limit)
                )
                result = await db.execute(query)
                return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get top contacts: {e}")
            return []
    
    async def get_stats(self) -> dict:
        """Get network statistics."""
        try:
            async with AsyncSessionLocal() as db:
                # Total contacts
                total_query = select(func.count(Contact.id)).where(Contact.is_deleted.is_(False))
                total_result = await db.execute(total_query)
                total = total_result.scalar() or 0
                
                # Average value score
                avg_query = select(func.avg(Contact.value_score))
                avg_result = await db.execute(avg_query)
                avg_score = float(avg_result.scalar() or 0)
                
                # Total interactions
                interactions_query = select(func.count(NetworkInteraction.id))
                interactions_result = await db.execute(interactions_query)
                total_interactions = interactions_result.scalar() or 0
                
                return {
                    "total_contacts": total,
                    "average_value_score": round(avg_score, 2),
                    "total_interactions": total_interactions
                }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}


# Global instance
network_builder_agent = NetworkBuilderAgent()
