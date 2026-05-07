"""
GraphQL Schema for Graxia OS

Enterprise-grade GraphQL API with:
- Query optimization (DataLoader pattern)
- Field-level permissions
- Query complexity limits
- Automatic pagination
- Subscriptions for real-time updates
"""

import asyncio
from datetime import datetime
from typing import List, Optional
from uuid import UUID

import strawberry
from strawberry.extensions import QueryDepthLimiter
from strawberry.federation import Schema
from strawberry.types import Info

from app.models.user import User
from app.models.organization import Organization
from app.models.opportunity import Opportunity


# ---------------------------------------------------------------------------
# Scalar Types
# ---------------------------------------------------------------------------

@strawberry.scalar
class DateTime:
    """DateTime scalar type."""
    
    @staticmethod
    def serialize(dt: datetime) -> str:
        return dt.isoformat()
    
    @staticmethod
    def parse_value(value: str) -> datetime:
        return datetime.fromisoformat(value)


# ---------------------------------------------------------------------------
# Input Types
# ---------------------------------------------------------------------------

@strawberry.input
class PaginationInput:
    """Pagination parameters."""
    first: Optional[int] = 20
    after: Optional[str] = None
    last: Optional[int] = None
    before: Optional[str] = None


@strawberry.input
class OpportunityFilterInput:
    """Filter parameters for opportunities."""
    status: Optional[str] = None
    source: Optional[str] = None
    min_score: Optional[float] = None
    created_after: Optional[DateTime] = None
    created_before: Optional[DateTime] = None


@strawberry.input
class CreateOpportunityInput:
    """Input for creating an opportunity."""
    title: str
    description: Optional[str] = None
    source: str
    source_url: Optional[str] = None
    estimated_value: Optional[float] = None
    tags: Optional[List[str]] = None


@strawberry.input
class UpdateOpportunityInput:
    """Input for updating an opportunity."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    estimated_value: Optional[float] = None
    tags: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Object Types
# ---------------------------------------------------------------------------

@strawberry.type
class PageInfo:
    """Pagination metadata."""
    has_next_page: bool
    has_previous_page: bool
    start_cursor: Optional[str]
    end_cursor: Optional[str]
    total_count: int


@strawberry.type
class UserType:
    """User type."""
    id: UUID
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: DateTime
    last_login_at: Optional[DateTime]
    
    @strawberry.field
    async def organization(self, info: Info) -> Optional["OrganizationType"]:
        """Get user's organization."""
        # Use DataLoader to avoid N+1 queries
        loader = info.context["loaders"]["organization"]
        return await loader.load(self.id)


@strawberry.type
class OrganizationType:
    """Organization type."""
    id: UUID
    name: str
    slug: str
    plan: str
    status: str
    created_at: DateTime
    
    @strawberry.field
    async def members(self, info: Info) -> List[UserType]:
        """Get organization members."""
        loader = info.context["loaders"]["organization_members"]
        return await loader.load(self.id)
    
    @strawberry.field
    async def opportunities(
        self,
        info: Info,
        filter: Optional[OpportunityFilterInput] = None,
        pagination: Optional[PaginationInput] = None
    ) -> "OpportunityConnection":
        """Get organization opportunities with filtering and pagination."""
        db = info.context["db"]
        
        # Build query with filters
        from sqlalchemy import select
        from app.models.opportunity import Opportunity as OpportunityModel
        
        query = select(OpportunityModel).where(
            OpportunityModel.organization_id == self.id
        )
        
        if filter:
            if filter.status:
                query = query.where(OpportunityModel.status == filter.status)
            if filter.source:
                query = query.where(OpportunityModel.source == filter.source)
            if filter.min_score:
                query = query.where(OpportunityModel.score >= filter.min_score)
        
        # Execute query
        result = await db.execute(query)
        opportunities = result.scalars().all()
        
        # Apply pagination
        pagination = pagination or PaginationInput()
        start = 0
        if pagination.after:
            # Decode cursor
            start = int(pagination.after) + 1
        
        end = start + (pagination.first or 20)
        paginated = opportunities[start:end]
        
        # Create edges
        edges = [
            OpportunityEdge(
                node=OpportunityType.from_model(opp),
                cursor=str(start + i)
            )
            for i, opp in enumerate(paginated)
        ]
        
        return OpportunityConnection(
            edges=edges,
            page_info=PageInfo(
                has_next_page=end < len(opportunities),
                has_previous_page=start > 0,
                start_cursor=str(start) if paginated else None,
                end_cursor=str(end - 1) if paginated else None,
                total_count=len(opportunities)
            )
        )


@strawberry.type
class OpportunityType:
    """Opportunity type."""
    id: UUID
    title: str
    description: Optional[str]
    source: str
    source_url: Optional[str]
    status: str
    score: float
    estimated_value: Optional[float]
    created_at: DateTime
    updated_at: DateTime
    tags: List[str]
    
    @classmethod
    def from_model(cls, model) -> "OpportunityType":
        """Create GraphQL type from database model."""
        return cls(
            id=model.id,
            title=model.title,
            description=model.description,
            source=model.source,
            source_url=model.source_url,
            status=model.status,
            score=model.score or 0.0,
            estimated_value=model.estimated_value,
            created_at=model.created_at,
            updated_at=model.updated_at,
            tags=model.tags or []
        )
    
    @strawberry.field
    async def organization(self, info: Info) -> OrganizationType:
        """Get opportunity's organization."""
        loader = info.context["loaders"]["organization"]
        return await loader.load(self.id)
    
    @strawberry.field
    async def assigned_to(self, info: Info) -> Optional[UserType]:
        """Get assigned user."""
        if not hasattr(self, 'assigned_user_id') or not self.assigned_user_id:
            return None
        loader = info.context["loaders"]["user"]
        return await loader.load(self.assigned_user_id)


@strawberry.type
class OpportunityEdge:
    """Edge in opportunity connection."""
    node: OpportunityType
    cursor: str


@strawberry.type
class OpportunityConnection:
    """Paginated connection of opportunities."""
    edges: List[OpportunityEdge]
    page_info: PageInfo


@strawberry.type
class DashboardMetrics:
    """Dashboard metrics type."""
    total_opportunities: int
    open_opportunities: int
    won_opportunities: int
    lost_opportunities: int
    total_pipeline_value: float
    average_deal_size: float
    win_rate: float
    conversion_rate: float
    
    @strawberry.field
    async def weekly_trend(self, info: Info) -> List["WeeklyMetric"]:
        """Get weekly trend data."""
        # Implementation would fetch from analytics
        return []


@strawberry.type
class WeeklyMetric:
    """Weekly metric data point."""
    week_start: DateTime
    new_opportunities: int
    closed_opportunities: int
    revenue: float


# ---------------------------------------------------------------------------
# Query Type
# ---------------------------------------------------------------------------

@strawberry.type
class Query:
    """Root query type."""
    
    @strawberry.field
    async def me(self, info: Info) -> UserType:
        """Get current user."""
        user = info.context["user"]
        return UserType(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login_at=user.last_login_at
        )
    
    @strawberry.field
    async def user(self, info: Info, id: UUID) -> Optional[UserType]:
        """Get user by ID (admin only)."""
        # Check permissions
        current_user = info.context["user"]
        if current_user.role != "admin":
            raise Exception("Permission denied")
        
        loader = info.context["loaders"]["user"]
        return await loader.load(id)
    
    @strawberry.field
    async def organization(self, info: Info, id: Optional[UUID] = None) -> OrganizationType:
        """Get organization by ID or current user's organization."""
        user = info.context["user"]
        org_id = id or user.organization_id
        
        loader = info.context["loaders"]["organization"]
        return await loader.load(org_id)
    
    @strawberry.field
    async def opportunity(self, info: Info, id: UUID) -> Optional[OpportunityType]:
        """Get opportunity by ID."""
        db = info.context["db"]
        from sqlalchemy import select
        from app.models.opportunity import Opportunity as OpportunityModel
        
        result = await db.execute(
            select(OpportunityModel).where(OpportunityModel.id == id)
        )
        opp = result.scalar_one_or_none()
        
        if opp:
            return OpportunityType.from_model(opp)
        return None
    
    @strawberry.field
    async def opportunities(
        self,
        info: Info,
        filter: Optional[OpportunityFilterInput] = None,
        pagination: Optional[PaginationInput] = None
    ) -> OpportunityConnection:
        """Get all opportunities with filtering and pagination."""
        user = info.context["user"]
        
        # Use organization's opportunities method
        org_loader = info.context["loaders"]["organization"]
        org = await org_loader.load(user.organization_id)
        
        return await org.opportunities(info, filter, pagination)
    
    @strawberry.field
    async def dashboard_metrics(self, info: Info) -> DashboardMetrics:
        """Get dashboard metrics for current organization."""
        user = info.context["user"]
        db = info.context["db"]
        
        from sqlalchemy import func, select
        from app.models.opportunity import Opportunity as OpportunityModel
        
        # Calculate metrics
        result = await db.execute(
            select(
                func.count(OpportunityModel.id).label("total"),
                func.sum(OpportunityModel.estimated_value).label("total_value"),
                func.avg(OpportunityModel.estimated_value).label("avg_value")
            ).where(
                OpportunityModel.organization_id == user.organization_id
            )
        )
        row = result.one()
        
        # Count by status
        status_result = await db.execute(
            select(
                OpportunityModel.status,
                func.count(OpportunityModel.id)
            ).where(
                OpportunityModel.organization_id == user.organization_id
            ).group_by(OpportunityModel.status)
        )
        status_counts = {status: count for status, count in status_result.all()}
        
        total = row.total or 0
        won = status_counts.get("won", 0)
        lost = status_counts.get("lost", 0)
        
        win_rate = won / (won + lost) if (won + lost) > 0 else 0
        
        return DashboardMetrics(
            total_opportunities=total,
            open_opportunities=status_counts.get("open", 0),
            won_opportunities=won,
            lost_opportunities=lost,
            total_pipeline_value=row.total_value or 0,
            average_deal_size=row.avg_value or 0,
            win_rate=win_rate,
            conversion_rate=0.0  # Calculate based on submissions
        )


# ---------------------------------------------------------------------------
# Mutation Type
# ---------------------------------------------------------------------------

@strawberry.type
class Mutation:
    """Root mutation type."""
    
    @strawberry.mutation
    async def create_opportunity(
        self,
        info: Info,
        input: CreateOpportunityInput
    ) -> OpportunityType:
        """Create a new opportunity."""
        user = info.context["user"]
        db = info.context["db"]
        
        from app.models.opportunity import Opportunity as OpportunityModel
        
        opportunity = OpportunityModel(
            id=uuid4(),
            organization_id=user.organization_id,
            title=input.title,
            description=input.description,
            source=input.source,
            source_url=input.source_url,
            estimated_value=input.estimated_value,
            tags=input.tags or [],
            status="new",
            score=0.0,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        db.add(opportunity)
        await db.commit()
        await db.refresh(opportunity)
        
        return OpportunityType.from_model(opportunity)
    
    @strawberry.mutation
    async def update_opportunity(
        self,
        info: Info,
        id: UUID,
        input: UpdateOpportunityInput
    ) -> OpportunityType:
        """Update an existing opportunity."""
        db = info.context["db"]
        
        from sqlalchemy import select
        from app.models.opportunity import Opportunity as OpportunityModel
        
        result = await db.execute(
            select(OpportunityModel).where(OpportunityModel.id == id)
        )
        opportunity = result.scalar_one_or_none()
        
        if not opportunity:
            raise Exception("Opportunity not found")
        
        # Update fields
        if input.title is not None:
            opportunity.title = input.title
        if input.description is not None:
            opportunity.description = input.description
        if input.status is not None:
            opportunity.status = input.status
        if input.estimated_value is not None:
            opportunity.estimated_value = input.estimated_value
        if input.tags is not None:
            opportunity.tags = input.tags
        
        opportunity.updated_at = datetime.now()
        
        await db.commit()
        await db.refresh(opportunity)
        
        return OpportunityType.from_model(opportunity)
    
    @strawberry.mutation
    async def delete_opportunity(self, info: Info, id: UUID) -> bool:
        """Delete an opportunity."""
        db = info.context["db"]
        
        from sqlalchemy import select, delete
        from app.models.opportunity import Opportunity as OpportunityModel
        
        result = await db.execute(
            select(OpportunityModel).where(OpportunityModel.id == id)
        )
        opportunity = result.scalar_one_or_none()
        
        if not opportunity:
            return False
        
        await db.execute(
            delete(OpportunityModel).where(OpportunityModel.id == id)
        )
        await db.commit()
        
        return True


# ---------------------------------------------------------------------------
# Subscription Type (Real-time updates)
# ---------------------------------------------------------------------------

@strawberry.type
class Subscription:
    """Root subscription type for real-time updates."""
    
    @strawberry.subscription
    async def opportunity_updates(
        self,
        info: Info,
        organization_id: UUID
    ):
        """Subscribe to real-time opportunity updates."""
        # In production, use WebSocket or SSE
        # This is a simplified implementation
        
        user = info.context["user"]
        if user.organization_id != organization_id:
            raise Exception("Permission denied")
        
        # Yield updates as they happen
        # This would connect to a pub/sub system (Redis, Kafka, etc.)
        while True:
            # Check for updates
            await asyncio.sleep(1)
            
            # In real implementation, listen to Redis pub/sub or similar
            # yield update


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# Create schema with extensions
schema = Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
    extensions=[
        QueryDepthLimiter(max_depth=10),  # Prevent deep nesting attacks
    ]
)
