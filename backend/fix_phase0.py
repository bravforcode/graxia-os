"""
Phase 0 Emergency Triage Fixes — Graxia OS
Applies TASK-0-01, TASK-0-04, TASK-1-02, TASK-1-03, TASK-1-01 (Dockerfile port)
Run: python fix_phase0.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent
APP = ROOT / "app"

results = []

# ─────────────────────────────────────────────────────────────
# TASK-0-01: Re-enable production security gate in config.py
# ─────────────────────────────────────────────────────────────
config_path = APP / "config.py"
config = config_path.read_text(encoding="utf-8")

OLD_GATE = (
    "    def validate_production_configuration(self) -> None:\n"
    "        # Temporarily disabled for debugging\n"
    "        # errors = self.get_production_configuration_errors()\n"
    "        # if errors:\n"
    "        #     raise RuntimeError(\n"
    '        #         "Production security configuration is invalid: " + "; ".join(errors)\n'
    "        #     )\n"
    "        pass"
)
NEW_GATE = (
    "    def validate_production_configuration(self) -> None:\n"
    "        errors = self.get_production_configuration_errors()\n"
    "        if errors:\n"
    "            raise RuntimeError(\n"
    '                "Production security configuration is invalid: " + "; ".join(errors)\n'
    "            )"
)

if OLD_GATE in config:
    config_path.write_text(config.replace(OLD_GATE, NEW_GATE), encoding="utf-8")
    results.append("TASK-0-01 ✅  Production security gate restored in config.py")
else:
    results.append("TASK-0-01 ⚠️  Pattern not found — gate may already be fixed or changed")

# ─────────────────────────────────────────────────────────────
# TASK-0-04: Fix get_current_user to return ORM User
# ─────────────────────────────────────────────────────────────
auth_mw_path = APP / "middleware" / "auth.py"
auth_mw = auth_mw_path.read_text(encoding="utf-8")

OLD_GET_USER = '''async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "user_id": str(user_id),
        "roles": [payload.get("role", "user")],
        "email": payload.get("email"),
        "session_id": payload.get("session_id"),
    }


async def get_current_active_user(current_user: dict[str, Any] = Security(get_current_user)) -> dict[str, Any]:
    return current_user


async def require_role(required_role: str, current_user: dict[str, Any] = Security(get_current_user)) -> dict[str, Any]:
    user_roles = current_user.get("roles", [])
    if required_role not in user_roles and "admin" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required role: {required_role}",
        )
    return current_user'''

NEW_GET_USER = '''async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    db: AsyncSession = Depends(get_db_dependency),
) -> "User":
    """
    Returns the authenticated ORM User object.
    Validates: token present, signature valid, session active, user exists, user active.
    """
    if credentials is None:
        # Fall back to cookie-based token (same as middleware)
        token = request.cookies.get(settings.ACCESS_COOKIE_NAME)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        token = credentials.credentials

    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate session is still active
    session_id = str(payload.get("session_id") or "")
    if session_id:
        session_service = SessionService(getattr(request.app.state, "redis", None))
        if not await session_service.is_session_active(session_id):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session is no longer active",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Load ORM User from DB
    from uuid import UUID as _UUID
    from app.models.user import User as _User
    user = await db.get(_User, _UUID(str(user_id)))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(current_user: "User" = Depends(get_current_user)) -> "User":
    return current_user


async def require_role(required_role: str, current_user: "User" = Depends(get_current_user)) -> "User":
    user_role = getattr(current_user, "role", "user") or "user"
    if not role_satisfies(
        AuthLevel.ADMIN if required_role == "admin" else AuthLevel.OPERATOR,
        user_role,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required role: {required_role}",
        )
    return current_user'''

if OLD_GET_USER in auth_mw:
    # Also need to add get_db import + AsyncSession
    new_mw = auth_mw.replace(OLD_GET_USER, NEW_GET_USER)

    # Inject get_db import if not already present
    if "from app.database import" not in new_mw:
        new_mw = new_mw.replace(
            "from app.config import settings",
            "from app.config import settings\nfrom app.database import get_db as get_db_dependency",
        )
    elif "get_db" not in new_mw:
        new_mw = new_mw.replace(
            "from app.database import",
            "from app.database import get_db as get_db_dependency,",
        )
    else:
        new_mw = new_mw.replace(
            "from app.database import get_db",
            "from app.database import get_db as get_db_dependency",
        )

    # Inject AsyncSession import if not present
    if "AsyncSession" not in new_mw:
        new_mw = new_mw.replace(
            "from sqlalchemy",
            "from sqlalchemy.ext.asyncio import AsyncSession\nfrom sqlalchemy",
        )

    # Add Depends import if not already imported
    if "Depends" not in new_mw:
        new_mw = new_mw.replace(
            "from fastapi import",
            "from fastapi import Depends,",
        )

    auth_mw_path.write_text(new_mw, encoding="utf-8")
    results.append("TASK-0-04 ✅  get_current_user now returns ORM User")
else:
    results.append("TASK-0-04 ⚠️  Pattern not found — auth middleware may have changed")

# ─────────────────────────────────────────────────────────────
# TASK-1-02: Add require_admin to deps.py
# ─────────────────────────────────────────────────────────────
deps_path = APP / "api" / "deps.py"
deps = deps_path.read_text(encoding="utf-8")

REQUIRE_ADMIN = '''

async def require_admin(
    current_user: "User" = Depends(get_current_user),
) -> "User":
    """FastAPI dependency — rejects non-admin callers with HTTP 403."""
    from app.middleware.auth import role_satisfies, AuthLevel, ROLE_ORDER
    user_role = getattr(current_user, "role", "user") or "user"
    if ROLE_ORDER.get(user_role, -1) < ROLE_ORDER.get("admin", 3):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user
'''

if "require_admin" not in deps:
    # Append before __all__
    new_deps = deps.replace(
        "\n__all__",
        REQUIRE_ADMIN + "\n__all__",
    )
    # Update __all__
    new_deps = new_deps.replace(
        '__all__ = ["get_db", "get_org", "get_current_user"]',
        '__all__ = ["get_db", "get_org", "get_current_user", "require_admin"]',
    )
    deps_path.write_text(new_deps, encoding="utf-8")
    results.append("TASK-1-02 ✅  require_admin dependency added to deps.py")
else:
    results.append("TASK-1-02 ⚠️  require_admin already exists in deps.py")

# ─────────────────────────────────────────────────────────────
# TASK-1-02b: Wire require_admin into admin.py
# ─────────────────────────────────────────────────────────────
admin_path = APP / "api" / "admin.py"
admin = admin_path.read_text(encoding="utf-8")

if "require_admin" not in admin:
    # Add import
    new_admin = admin.replace(
        "from app.database import get_db",
        "from app.api.deps import require_admin\nfrom app.database import get_db",
    )
    # Add dependency to every @router.get / @router.post / @router.delete
    # We patch each route to add `_: object = Depends(require_admin)` as first dep
    import re as _re
    def _add_admin_dep(m):
        func_sig = m.group(0)
        # If already has require_admin, skip
        if "require_admin" in func_sig:
            return func_sig
        # Insert before first existing Depends or before closing paren of args
        if "Depends" in func_sig:
            # Add before first Depends
            return func_sig.replace(
                "Depends(",
                "_adm: object = Depends(require_admin),\n    Depends(",
                1,
            )
        # No deps — add before closing paren
        return func_sig[:-2] + ",\n    _adm: object = Depends(require_admin),\n):"
    # Match async def signatures
    new_admin = _re.sub(
        r'async def \w+\([^)]*\)\s*->.*?:',
        _add_admin_dep,
        new_admin,
        flags=_re.DOTALL,
    )
    admin_path.write_text(new_admin, encoding="utf-8")
    results.append("TASK-1-02b ✅  require_admin wired to all admin endpoints")
else:
    results.append("TASK-1-02b ⚠️  require_admin already in admin.py")

# ─────────────────────────────────────────────────────────────
# TASK-1-03: Replace datetime.utcnow with datetime.now(UTC)
# ─────────────────────────────────────────────────────────────
models_dir = APP / "models"
patched_utcnow = []
for py_file in list(models_dir.glob("*.py")) + list((APP / "api").glob("*.py")):
    text = py_file.read_text(encoding="utf-8")
    if "datetime.utcnow" in text:
        new_text = text.replace("datetime.utcnow", "lambda: datetime.now(UTC)")
        # Ensure UTC imported
        if "from datetime import" in new_text and "UTC" not in new_text:
            new_text = new_text.replace(
                "from datetime import datetime",
                "from datetime import UTC, datetime",
            )
        py_file.write_text(new_text, encoding="utf-8")
        patched_utcnow.append(py_file.name)

if patched_utcnow:
    results.append(f"TASK-1-03 ✅  Replaced datetime.utcnow in: {', '.join(patched_utcnow)}")
else:
    results.append("TASK-1-03 ✅  No datetime.utcnow found in models/api (already clean)")

# ─────────────────────────────────────────────────────────────
# TASK-1-01: Fix Docker port mismatch (8080 → 8000)
# ─────────────────────────────────────────────────────────────
dockerfile_path = ROOT / "Dockerfile"
if dockerfile_path.exists():
    df = dockerfile_path.read_text(encoding="utf-8")
    new_df = df.replace("EXPOSE 8080", "EXPOSE 8000").replace("--port 8080", "--port 8000")
    if new_df != df:
        dockerfile_path.write_text(new_df, encoding="utf-8")
        results.append("TASK-1-01 ✅  Dockerfile port aligned to 8000")
    else:
        results.append("TASK-1-01 ⚠️  Port already set or pattern not matched in Dockerfile")
else:
    results.append("TASK-1-01 ⚠️  Dockerfile not found at backend/Dockerfile")

# ─────────────────────────────────────────────────────────────
# TASK-0-02: Add organization_id scope to contacts.py
# ─────────────────────────────────────────────────────────────
contacts_path = APP / "api" / "contacts.py"
contacts = contacts_path.read_text(encoding="utf-8")

if "get_org" not in contacts:
    # 1. Add import
    new_contacts = contacts.replace(
        "from app.database import get_db",
        "from app.api.deps import get_org\nfrom app.database import get_db",
    )
    # 2. Import Organization model
    if "Organization" not in new_contacts:
        new_contacts = new_contacts.replace(
            "from app.models.contact import Contact",
            "from app.models.contact import Contact\nfrom app.models.organization import Organization",
        )
    # 3. Rewrite _active_contacts to accept org_id
    new_contacts = new_contacts.replace(
        "def _active_contacts():\n    return select(Contact).where(Contact.is_deleted.is_(False))",
        "def _active_contacts(org_id: \"UUID\"):\n    return select(Contact).where(\n        Contact.is_deleted.is_(False),\n        Contact.organization_id == org_id,\n    )",
    )
    # 4. Add org dep to list_contacts
    new_contacts = new_contacts.replace(
        "async def list_contacts(\n    db: DbSession,",
        "async def list_contacts(\n    db: DbSession,\n    org: Organization = Depends(get_org),",
    )
    # 5. Use org.id in query
    new_contacts = new_contacts.replace(
        "    query = _active_contacts()\n    filters = ContactListFilters(",
        "    query = _active_contacts(org.id)\n    filters = ContactListFilters(",
    )
    # 6. Add org dep + org_id to create_contact
    new_contacts = new_contacts.replace(
        "async def create_contact(data: ContactCreate, db: DbSession):",
        "async def create_contact(data: ContactCreate, db: DbSession, org: Organization = Depends(get_org)):",
    )
    new_contacts = new_contacts.replace(
        "    row = Contact(\n        name=data.name,",
        "    row = Contact(\n        organization_id=org.id,\n        name=data.name,",
    )
    # 7. Add org dep to bulk_upsert
    new_contacts = new_contacts.replace(
        "async def bulk_upsert_contacts(items: list[ContactCreate], db: DbSession)",
        "async def bulk_upsert_contacts(items: list[ContactCreate], db: DbSession, org: Organization = Depends(get_org))",
    )
    # 8. Scope bulk email lookup
    new_contacts = new_contacts.replace(
        "                    _active_contacts().where(Contact.email == email).limit(1)",
        "                    _active_contacts(org.id).where(Contact.email == email).limit(1)",
    )
    # 9. Set org_id on bulk create
    new_contacts = new_contacts.replace(
        "        row = Contact(\n            name=item.name,",
        "        row = Contact(\n            organization_id=org.id,\n            name=item.name,",
    )
    # 10. Add org dep + org-scoped query to get_contact
    new_contacts = new_contacts.replace(
        "async def get_contact(contact_id: UUID, db: DbSession):",
        "async def get_contact(contact_id: UUID, db: DbSession, org: Organization = Depends(get_org)):",
    )
    new_contacts = new_contacts.replace(
        "        await db.execute(_active_contacts().where(Contact.id == contact_id).limit(1))",
        "        await db.execute(_active_contacts(org.id).where(Contact.id == contact_id).limit(1))",
    )
    # 11. Add org dep + org-scoped query to update_contact
    new_contacts = new_contacts.replace(
        "async def update_contact(contact_id: UUID, data: ContactUpdate, db: DbSession)",
        "async def update_contact(contact_id: UUID, data: ContactUpdate, db: DbSession, org: Organization = Depends(get_org))",
    )
    # 12. Add org dep + org-scoped query to delete_contact
    new_contacts = new_contacts.replace(
        "async def delete_contact(contact_id: UUID, db: DbSession)",
        "async def delete_contact(contact_id: UUID, db: DbSession, org: Organization = Depends(get_org))",
    )
    # Replace remaining _active_contacts() bare calls
    new_contacts = new_contacts.replace(
        "await db.execute(_active_contacts().where(Contact.id == contact_id)",
        "await db.execute(_active_contacts(org.id).where(Contact.id == contact_id)",
    )

    # Add Depends import if missing
    if "Depends" not in new_contacts:
        new_contacts = new_contacts.replace(
            "from fastapi import APIRouter",
            "from fastapi import APIRouter, Depends",
        )
    elif ", Depends" not in new_contacts and "Depends," not in new_contacts:
        new_contacts = new_contacts.replace(
            "from fastapi import APIRouter,",
            "from fastapi import APIRouter, Depends,",
        )

    contacts_path.write_text(new_contacts, encoding="utf-8")
    results.append("TASK-0-02 ✅  organization_id scope added to all contacts endpoints")
else:
    results.append("TASK-0-02 ⚠️  get_org already imported in contacts.py — may already be patched")

# ─────────────────────────────────────────────────────────────
# TASK-1-06: Raise password minimum to 12 characters
# ─────────────────────────────────────────────────────────────
auth_path = APP / "api" / "auth.py"
auth = auth_path.read_text(encoding="utf-8")
patched_pw = False
for old, new in [
    ("len(new_password) < 8", "len(new_password) < 12"),
    ("len(password) < 8", "len(password) < 12"),
    ("min_length=8", "min_length=12"),
]:
    if old in auth:
        auth = auth.replace(old, new)
        patched_pw = True
auth_path.write_text(auth, encoding="utf-8")
if patched_pw:
    results.append("TASK-1-06 ✅  Password minimum raised to 12 characters")
else:
    results.append("TASK-1-06 ⚠️  Password length pattern not found — check auth.py manually")

# ─────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("  PHASE 0 + PHASE 1 FIXES — RESULTS")
print("="*60)
for r in results:
    print(" ", r)
print("="*60)
print("\nNext steps:")
print("  1. Run: pytest backend/tests/ -x -q")
print("  2. Verify: docker compose build backend && docker compose up -d")
print("  3. Verify: curl http://localhost:8000/health")
print("  4. Verify: pytest backend/tests/test_config_validation_contracts.py -v")
