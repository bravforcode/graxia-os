"""
GraphQL Router for FastAPI

Integrates Strawberry GraphQL with FastAPI application.
"""

from fastapi import Depends, Request
from strawberry.fastapi import GraphQLRouter

from app.api.graphql.schema import schema
from app.api.graphql.loaders import Loaders
from app.database import get_db
from app.middleware.auth import get_current_user_optional


async def get_context(request: Request, db=Depends(get_db), user=Depends(get_current_user_optional)):
    """Create GraphQL context with database, user, and loaders."""
    loaders = Loaders(db)
    
    return {
        "request": request,
        "db": db,
        "user": user,
        "loaders": {
            "user": loaders.user,
            "organization": loaders.organization,
            "organization_members": loaders.organization_members,
            "opportunity": loaders.opportunity,
        }
    }


# Create GraphQL router
graphql_router = GraphQLRouter(
    schema,
    context_getter=get_context,
    graphql_ide="apollo-sandbox",  # or "graphiql"
)
