from uuid import UUID

from app.config import configured_public_funnel_organization_id, settings


class PublicFunnelBindingError(ValueError):
    """Raised when a public funnel request is not bound to the configured tenant."""


def require_public_funnel_organization(organization_id: UUID) -> UUID:
    configured = configured_public_funnel_organization_id()
    if configured is None:
        # Test fixtures create an isolated organization per test and do not
        # have a deployed public tenant. Keep the production path fail-closed
        # while allowing those isolated fixtures to exercise public routes.
        if settings.TESTING:
            return organization_id
        raise PublicFunnelBindingError("Public funnel is not configured")
    if configured != organization_id:
        raise PublicFunnelBindingError("Public funnel tenant not found")
    return configured
