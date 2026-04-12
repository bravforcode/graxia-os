"""
Authorization System

Role-Based Access Control (RBAC) for API endpoints.
"""
from enum import Enum
from typing import List, Optional
from fastapi import HTTPException


class Role(str, Enum):
    """User roles."""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class Permission(str, Enum):
    """System permissions."""
    # Opportunities
    READ_OPPORTUNITIES = "read:opportunities"
    WRITE_OPPORTUNITIES = "write:opportunities"
    DELETE_OPPORTUNITIES = "delete:opportunities"
    
    # Jobs
    READ_JOBS = "read:jobs"
    WRITE_JOBS = "write:jobs"
    DELETE_JOBS = "delete:jobs"
    
    # Contacts
    READ_CONTACTS = "read:contacts"
    WRITE_CONTACTS = "write:contacts"
    DELETE_CONTACTS = "delete:contacts"
    
    # Email
    READ_EMAIL = "read:email"
    WRITE_EMAIL = "write:email"
    DELETE_EMAIL = "delete:email"
    
    # Tasks
    READ_TASKS = "read:tasks"
    WRITE_TASKS = "write:tasks"
    DELETE_TASKS = "delete:tasks"
    
    # Drafts
    READ_DRAFTS = "read:drafts"
    WRITE_DRAFTS = "write:drafts"
    DELETE_DRAFTS = "delete:drafts"
    
    # System
    READ_SYSTEM = "read:system"
    WRITE_SYSTEM = "write:system"
    MANAGE_USERS = "manage:users"
    
    # Costs
    READ_COSTS = "read:costs"
    WRITE_COSTS = "write:costs"


# Role to permissions mapping
ROLE_PERMISSIONS = {
    Role.ADMIN: [
        # Full access to everything
        Permission.READ_OPPORTUNITIES,
        Permission.WRITE_OPPORTUNITIES,
        Permission.DELETE_OPPORTUNITIES,
        Permission.READ_JOBS,
        Permission.WRITE_JOBS,
        Permission.DELETE_JOBS,
        Permission.READ_CONTACTS,
        Permission.WRITE_CONTACTS,
        Permission.DELETE_CONTACTS,
        Permission.READ_EMAIL,
        Permission.WRITE_EMAIL,
        Permission.DELETE_EMAIL,
        Permission.READ_TASKS,
        Permission.WRITE_TASKS,
        Permission.DELETE_TASKS,
        Permission.READ_DRAFTS,
        Permission.WRITE_DRAFTS,
        Permission.DELETE_DRAFTS,
        Permission.READ_SYSTEM,
        Permission.WRITE_SYSTEM,
        Permission.MANAGE_USERS,
        Permission.READ_COSTS,
        Permission.WRITE_COSTS,
    ],
    Role.USER: [
        # Read and write, but no delete
        Permission.READ_OPPORTUNITIES,
        Permission.WRITE_OPPORTUNITIES,
        Permission.READ_JOBS,
        Permission.WRITE_JOBS,
        Permission.READ_CONTACTS,
        Permission.WRITE_CONTACTS,
        Permission.READ_EMAIL,
        Permission.WRITE_EMAIL,
        Permission.READ_TASKS,
        Permission.WRITE_TASKS,
        Permission.READ_DRAFTS,
        Permission.WRITE_DRAFTS,
        Permission.READ_SYSTEM,
        Permission.READ_COSTS,
    ],
    Role.VIEWER: [
        # Read-only access
        Permission.READ_OPPORTUNITIES,
        Permission.READ_JOBS,
        Permission.READ_CONTACTS,
        Permission.READ_EMAIL,
        Permission.READ_TASKS,
        Permission.READ_DRAFTS,
        Permission.READ_SYSTEM,
        Permission.READ_COSTS,
    ],
}


def get_role_permissions(role: Role) -> List[Permission]:
    """Get all permissions for a role."""
    return ROLE_PERMISSIONS.get(role, [])


def has_permission(user_role: str, required_permission: Permission) -> bool:
    """Check if user role has required permission."""
    try:
        role = Role(user_role)
    except ValueError:
        return False
    
    permissions = get_role_permissions(role)
    return required_permission in permissions


def require_permission(required_permission: Permission):
    """Decorator to require specific permission."""
    def permission_checker(current_user: dict) -> dict:
        user_role = current_user.get("role", "viewer")
        
        if not has_permission(user_role, required_permission):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required: {required_permission.value}"
            )
        
        return current_user
    
    return permission_checker


def check_resource_ownership(
    current_user: dict,
    resource_owner_id: Optional[str] = None
) -> bool:
    """Check if user owns the resource or is admin."""
    user_role = current_user.get("role", "viewer")
    user_id = current_user.get("id")
    
    # Admins can access everything
    if user_role == Role.ADMIN:
        return True
    
    # Check ownership
    if resource_owner_id and user_id == resource_owner_id:
        return True
    
    return False


def require_ownership_or_admin(resource_owner_id: Optional[str] = None):
    """Decorator to require resource ownership or admin role."""
    def ownership_checker(current_user: dict) -> dict:
        if not check_resource_ownership(current_user, resource_owner_id):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to access this resource"
            )
        
        return current_user
    
    return ownership_checker
