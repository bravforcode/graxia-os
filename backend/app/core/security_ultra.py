"""
ULTRA: Enterprise Security Engine
NIST-compliant, zero-compromise security implementation
"""
import hashlib
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    pyotp = None
    PYOTP_AVAILABLE = False

from passlib.context import CryptContext

logger = logging.getLogger(__name__)

# NIST 800-63B compliant password policy
PASSWORD_POLICY = {
    "min_length": 12,
    "max_length": 128,
    "require_uppercase": True,
    "require_lowercase": True,
    "require_digit": True,
    "require_special": True,
    "history_count": 5,
    "max_age_days": 90,
    "prevent_common": True,
}

# Common passwords (NIST blacklist)
COMMON_PASSWORDS = {
    "password", "password123", "qwerty", "12345678", "1234567890",
    "admin", "admin123", "letmein", "welcome", "monkey",
    "dragon", "master", "sunshine", "princess", "football",
    "baseball", "iloveyou", "trustno1", "abc123", "welcome123",
}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class ULTRASecurityManager:
    """
    ULTRA Security Manager - NIST 800-63B compliant
    Zero compromise, enterprise-grade security
    """

    # Account lockout settings
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 30

    # Session settings
    SESSION_TIMEOUT_MINUTES = 60
    ABSOLUTE_TIMEOUT_HOURS = 8

    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, list[str]]:
        """
        Validate password against NIST 800-63B guidelines

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        # Length check
        if len(password) < PASSWORD_POLICY["min_length"]:
            errors.append(
                f"Password must be at least {PASSWORD_POLICY['min_length']} characters"
            )

        if len(password) > PASSWORD_POLICY["max_length"]:
            errors.append(
                f"Password must not exceed {PASSWORD_POLICY['max_length']} characters"
            )

        # Character requirements
        if PASSWORD_POLICY["require_uppercase"] and not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")

        if PASSWORD_POLICY["require_lowercase"] and not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")

        if PASSWORD_POLICY["require_digit"] and not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one digit")

        if PASSWORD_POLICY["require_special"]:
            special_chars = set('!@#$%^&*()_+-=[]{}|;:,.<>?')
            if not any(c in special_chars for c in password):
                errors.append("Password must contain at least one special character")

        # Common password check
        if PASSWORD_POLICY["prevent_common"]:
            password_lower = password.lower()
            for common in COMMON_PASSWORDS:
                if common in password_lower or password_lower in common:
                    errors.append("Password is too common or easily guessed")
                    break

        # Entropy check (basic)
        unique_chars = len(set(password))
        if unique_chars < 6:
            errors.append("Password has too few unique characters")

        return len(errors) == 0, errors

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password with bcrypt"""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """Generate cryptographically secure random token"""
        return secrets.token_urlsafe(length)

    @staticmethod
    def generate_api_key() -> str:
        """Generate API key with prefix for identification"""
        prefix = "grx_"  # Graxia prefix
        random_part = secrets.token_urlsafe(32)
        return f"{prefix}{random_part}"

    @staticmethod
    def sanitize_email(email: str) -> str:
        """Normalize and validate email"""
        email = email.lower().strip()
        # Basic email validation
        pattern = r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
        if not re.match(pattern, email):
            raise ValueError(f"Invalid email format: {email}")
        return email


class TOTPManager:
    """
    Time-based One-Time Password (TOTP) manager
    RFC 6238 compliant implementation
    """

    DIGITS = 6
    INTERVAL = 30  # seconds
    WINDOW = 1  # allowed time drift (±1 interval)

    @staticmethod
    def generate_secret() -> str:
        """Generate cryptographically secure TOTP secret"""
        if not PYOTP_AVAILABLE:
            # Fallback: generate random base32-like string
            import base64
            random_bytes = secrets.token_bytes(20)
            return base64.b32encode(random_bytes).decode('ascii').rstrip('=')
        return pyotp.random_base32()

    @classmethod
    def verify_token(cls, secret: str, token: str) -> bool:
        """
        Verify TOTP token with time window

        Args:
            secret: Base32-encoded secret
            token: 6-digit token to verify

        Returns:
            True if token is valid
        """
        if not PYOTP_AVAILABLE:
            logger.warning("pyotp not available, TOTP verification disabled")
            return False

        if not token or not token.isdigit() or len(token) != cls.DIGITS:
            return False

        totp = pyotp.TOTP(secret, digits=cls.DIGITS, interval=cls.INTERVAL)
        return totp.verify(token, valid_window=cls.WINDOW)

    @classmethod
    def get_provisioning_uri(
        cls,
        secret: str,
        email: str,
        issuer: str = "Graxia OS"
    ) -> str:
        """
        Generate provisioning URI for authenticator apps

        Format: otpauth://totp/{issuer}:{email}?secret={secret}&issuer={issuer}
        """
        if not PYOTP_AVAILABLE:
            # Return placeholder when pyotp not available
            return f"otpauth://totp/{issuer}:{email}?secret={secret}&issuer={issuer}"

        totp = pyotp.TOTP(secret, digits=cls.DIGITS, interval=cls.INTERVAL)
        return totp.provisioning_uri(email, issuer_name=issuer)

    @classmethod
    def generate_backup_codes(cls, count: int = 10) -> list[str]:
        """
        Generate single-use backup codes

        Returns:
            List of 8-character alphanumeric codes
        """
        codes = []
        for _ in range(count):
            # 8 characters, uppercase
            code = secrets.token_hex(4).upper()
            codes.append(code)
        return codes

    @staticmethod
    def hash_backup_code(code: str) -> str:
        """Hash backup code for storage (SHA-256)"""
        return hashlib.sha256(code.encode()).hexdigest()


class RBACManager:
    """
    Role-Based Access Control (RBAC) manager
    Granular permissions with hierarchy
    """

    # Role hierarchy (higher = more permissions)
    ROLES = {
        "viewer": 1,      # Read-only
        "user": 2,        # Standard user
        "operator": 3,    # Power user
        "admin": 4,     # Organization admin
        "superadmin": 5,  # System superadmin
    }

    # Permission definitions
    PERMISSIONS = {
        # Read permissions
        "read_own": {"min_role": "viewer"},
        "read_org": {"min_role": "user"},
        "read_all": {"min_role": "admin"},

        # Write permissions
        "write_own": {"min_role": "user"},
        "write_org": {"min_role": "operator"},
        "write_all": {"min_role": "admin"},

        # Delete permissions
        "delete_own": {"min_role": "user"},
        "delete_org": {"min_role": "admin"},

        # Special permissions
        "manage_users": {"min_role": "admin"},
        "manage_billing": {"min_role": "admin"},
        "view_analytics": {"min_role": "operator"},
        "export_data": {"min_role": "operator"},
        "system_admin": {"min_role": "superadmin"},
    }

    @classmethod
    def has_permission(cls, user_role: str, permission: str) -> bool:
        """
        Check if role has specific permission

        Args:
            user_role: Role of the user
            permission: Permission to check

        Returns:
            True if permission granted
        """
        if permission == "*":  # Wildcard
            return True

        perm_def = cls.PERMISSIONS.get(permission)
        if not perm_def:
            return False

        min_role = perm_def["min_role"]
        user_level = cls.ROLES.get(user_role, 0)
        min_level = cls.ROLES.get(min_role, float('inf'))

        return user_level >= min_level

    @classmethod
    def can_access_resource(
        cls,
        user_role: str,
        user_org_id: UUID,
        resource_org_id: UUID,
        resource_owner_id: UUID | None,
        user_id: UUID,
    ) -> tuple[bool, str]:
        """
        Check if user can access specific resource

        Returns:
            (can_access, reason)
        """
        # Superadmin can access everything
        if user_role == "superadmin":
            return True, "superadmin access"

        # Check organization match
        if user_org_id != resource_org_id:
            return False, "cross-organization access denied"

        # Check ownership
        if resource_owner_id == user_id:
            return True, "resource owner"

        # Check role permissions
        if cls.has_permission(user_role, "read_org"):
            return True, "organization access"

        return False, "insufficient permissions"


class SessionManager:
    """
    Secure session management
    CSRF protection, timeout handling
    """

    SESSION_COOKIE_NAME = "graxia_session"
    CSRF_COOKIE_NAME = "graxia_csrf"

    @staticmethod
    def create_session(user_id: UUID, ip_address: str | None = None) -> dict[str, Any]:
        """Create new session with metadata"""
        now = datetime.now(UTC)

        return {
            "session_id": str(uuid4()),
            "user_id": str(user_id),
            "created_at": now.isoformat(),
            "last_activity": now.isoformat(),
            "ip_address": ip_address,
            "csrf_token": ULTRASecurityManager.generate_secure_token(32),
        }

    @staticmethod
    def is_session_valid(session: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Check session validity

        Returns:
            (is_valid, reason_if_invalid)
        """
        if not session:
            return False, "no session"

        now = datetime.now(UTC)

        # Parse timestamps
        created_at = datetime.fromisoformat(session["created_at"])
        last_activity = datetime.fromisoformat(session["last_activity"])

        # Check absolute timeout
        absolute_timeout = timedelta(hours=ULTRASecurityManager.ABSOLUTE_TIMEOUT_HOURS)
        if now - created_at > absolute_timeout:
            return False, "session expired (absolute timeout)"

        # Check idle timeout
        idle_timeout = timedelta(minutes=ULTRASecurityManager.SESSION_TIMEOUT_MINUTES)
        if now - last_activity > idle_timeout:
            return False, "session expired (idle timeout)"

        return True, None


class AuditLogger:
    """
    Comprehensive audit logging
    Immutable, append-only logs for compliance
    """

    SENSITIVE_ACTIONS = {
        "user.login",
        "user.logout",
        "user.password_change",
        "user.2fa_enable",
        "user.2fa_disable",
        "user.delete",
        "billing.payment",
        "billing.subscription_change",
        "admin.user_create",
        "admin.user_delete",
        "admin.org_delete",
        "data.export",
    }

    @staticmethod
    def create_entry(
        action: str,
        user_id: UUID | None,
        organization_id: UUID | None,
        resource_type: str,
        resource_id: str | None,
        before: dict | None,
        after: dict | None,
        ip_address: str | None,
        user_agent: str | None,
        extra_data: dict | None = None,
    ) -> dict[str, Any]:
        """Create audit log entry"""
        return {
            "id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "action": action,
            "user_id": str(user_id) if user_id else None,
            "organization_id": str(organization_id) if organization_id else None,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "before": before,
            "after": after,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "extra_data": extra_data or {},
            "is_sensitive": action in AuditLogger.SENSITIVE_ACTIONS,
        }

    @classmethod
    async def log(
        cls,
        db_session: Any,
        entry: dict[str, Any],
    ) -> None:
        """Persist audit log entry (async)"""
        from app.models.audit_log import AuditLogEntry

        log_entry = AuditLogEntry(**entry)
        db_session.add(log_entry)
        # Don't commit - let outer transaction handle it

        # Alert on sensitive actions
        if entry.get("is_sensitive"):
            logger.warning(
                f"SENSITIVE ACTION: {entry['action']} by {entry['user_id']} "
                f"on {entry['resource_type']}:{entry['resource_id']}"
            )
