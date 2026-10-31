import httpx
import logging
import time
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import settings
from app.core.errors import AppError, RateLimitedError
from app.core.email_identity import normalize_email
from app.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    extract_bearer_token,
    get_password_hash,
    parse_subject_uuid,
    verify_password,
)
from app.database import get_db
from app.middleware.auth import (
    extract_access_token_from_request,
    get_client_ip,
    get_device_fingerprint,
)
from app.middleware.security import generate_csrf_token
from app.models.user import User
from app.services.audit_service import log_audit_event
from app.services.invitation_service import consume_invitation, issue_invitation, revoke_invitation
from app.services.risk_engine import RiskEngine
from app.services.session_service import RefreshTokenReuseDetected, SessionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
risk_engine = RiskEngine()
DUMMY_PASSWORD_HASH = get_password_hash("not-the-real-password")
DATABASE_UNAVAILABLE_DETAIL = (
    "Database unavailable. Check DATABASE_URL connectivity and database reachability."
)

_login_attempts: dict[str, list[float]] = {}
LOGIN_RATE_LIMIT = 5  # max attempts
LOGIN_WINDOW = 300  # 5 minutes


def _check_rate_limit(identifier: str) -> None:
    now = time.time()
    attempts = _login_attempts.get(identifier, [])
    attempts = [t for t in attempts if now - t < LOGIN_WINDOW]
    if len(attempts) >= LOGIN_RATE_LIMIT:
        raise RateLimitedError(retry_after_seconds=max(1, int(LOGIN_WINDOW - (now - attempts[0]))))
    attempts.append(now)
    _login_attempts[identifier] = attempts


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    invite_token: str | None = None


class SocialLoginRequest(BaseModel):
    token: str
    provider: str
    invite_token: str | None = None


class InvitationRequest(BaseModel):
    email: EmailStr
    role: Literal["operator", "viewer"]


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


def _serialize_user(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
) -> None:
    domain = settings.COOKIE_DOMAIN or None
    secure = settings.COOKIE_SECURE_EFFECTIVE
    response.set_cookie(
        key=settings.ACCESS_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/api/v1",
        domain=domain,
    )
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth/refresh",
        domain=domain,
    )
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        domain=domain,
    )


def _clear_auth_cookies(response: Response) -> None:
    domain = settings.COOKIE_DOMAIN or None
    response.set_cookie(
        settings.ACCESS_COOKIE_NAME, "", max_age=0, path="/api/v1", domain=domain
    )
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        "",
        max_age=0,
        path="/api/v1/auth/refresh",
        domain=domain,
    )
    response.set_cookie(
        settings.CSRF_COOKIE_NAME, "", max_age=0, path="/", domain=domain
    )


def _build_auth_payloads(
    user: User, *, session_id: str, device_id: str, refresh_jti: str
) -> tuple[str, str]:
    access_payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "session_id": session_id,
        "device_id": device_id,
        "jti": str(uuid4()),
    }
    refresh_payload = {
        "sub": str(user.id),
        "session_id": session_id,
        "device_id": device_id,
        "jti": refresh_jti,
    }
    return create_access_token(access_payload), create_refresh_token(refresh_payload)


async def _lookup_user_by_email(db, email: str) -> User | None:
    normalized_email = normalize_email(email)
    result = await db.execute(
        select(User)
        .where(func.lower(func.trim(User.email)) == normalized_email)
        .limit(2)
    )
    users = list(result.scalars().all())
    return users[0] if len(users) == 1 else None


async def _lookup_user_by_provider_id(db, provider_id: str) -> User | None:
    result = await db.execute(select(User).where(User.provider_id == provider_id))
    return result.scalar_one_or_none()


async def _lookup_users_by_canonical_email(db, email: str) -> list[User]:
    normalized_email = normalize_email(email)
    result = await db.execute(
        select(User)
        .where(func.lower(func.trim(User.email)) == normalized_email)
        .limit(2)
    )
    users = list(result.scalars().all())
    if len(users) > 1:
        raise AppError(
            code="SOCIAL_EMAIL_CONFLICT",
            message="The verified social email is linked to multiple accounts.",
            status_code=status.HTTP_409_CONFLICT,
        )
    return users


async def _fetch_supabase_user(access_token: str) -> dict:
    supabase_url = settings.SUPABASE_URL.rstrip("/")
    anon_key = settings.SUPABASE_ANON_KEY
    if not supabase_url.startswith("https://") or not anon_key:
        raise AppError(
            code="SOCIAL_AUTH_UNAVAILABLE",
            message="Social sign-in is temporarily unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            response = await client.get(
                f"{supabase_url}/auth/v1/user",
                headers={
                    "apikey": anon_key,
                    "Authorization": f"Bearer {access_token}",
                },
            )
    except httpx.RequestError as exc:
        raise AppError(
            code="SOCIAL_AUTH_UNAVAILABLE",
            message="Social sign-in is temporarily unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc

    if response.status_code in {401, 403}:
        raise AppError(
            code="AUTH_INVALID",
            message="The social sign-in session is invalid or expired.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if response.status_code != 200:
        raise AppError(
            code="SOCIAL_AUTH_UNAVAILABLE",
            message="Social sign-in is temporarily unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    try:
        canonical_user = response.json()
    except ValueError as exc:
        raise AppError(
            code="SOCIAL_AUTH_UNAVAILABLE",
            message="Social sign-in is temporarily unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    if not isinstance(canonical_user, dict):
        raise AppError(
            code="SOCIAL_AUTH_UNAVAILABLE",
            message="Social sign-in is temporarily unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return canonical_user


def _confirmed_social_identity(
    *,
    decoded: dict,
    canonical_user: dict,
    requested_provider: str,
) -> tuple[str, str, dict]:
    subject = decoded.get("sub")
    canonical_subject = canonical_user.get("id")
    if (
        not isinstance(subject, str)
        or not subject.strip()
        or canonical_subject != subject
    ):
        raise AppError(
            code="AUTH_INVALID",
            message="The social sign-in identity could not be verified.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    email = canonical_user.get("email")
    if (
        not isinstance(email, str)
        or not email.strip()
        or email.strip() != email
        or "@" not in email
        or not canonical_user.get("email_confirmed_at")
    ):
        raise AppError(
            code="SOCIAL_EMAIL_UNVERIFIED",
            message="Confirm your email with the identity provider before signing in.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    app_metadata = canonical_user.get("app_metadata")
    app_metadata = app_metadata if isinstance(app_metadata, dict) else {}
    provider_names = app_metadata.get("providers")
    if not isinstance(provider_names, list):
        provider_names = []
    primary_provider = app_metadata.get("provider")
    if isinstance(primary_provider, str):
        provider_names.append(primary_provider)
    identities = canonical_user.get("identities")
    if isinstance(identities, list):
        provider_names.extend(
            identity.get("provider")
            for identity in identities
            if isinstance(identity, dict) and isinstance(identity.get("provider"), str)
        )
    if (
        requested_provider not in {"google", "facebook"}
        or requested_provider not in provider_names
    ):
        raise AppError(
            code="AUTH_INVALID",
            message="The social sign-in provider could not be verified.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    user_metadata = canonical_user.get("user_metadata")
    user_metadata = user_metadata if isinstance(user_metadata, dict) else {}
    return subject, normalize_email(email), user_metadata


def _is_database_unavailable_error(exc: Exception) -> bool:
    return isinstance(
        exc, (SQLAlchemyError, OSError, ConnectionError, TimeoutError, PermissionError)
    )


def _raise_database_unavailable(exc: Exception) -> None:
    logger.error("Database unavailable during auth flow: %s", exc, exc_info=True)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=DATABASE_UNAVAILABLE_DETAIL,
    ) from exc


async def _resolve_refresh_token(request: Request) -> str | None:
    cookie_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    auth_token = extract_bearer_token(request.headers.get("Authorization"))
    if auth_token:
        return auth_token
    try:
        body = await request.json()
    except Exception:
        return None
    return body.get("refresh_token")


async def _issue_auth_response(
    *,
    response: Response,
    user: User,
    request: Request,
    session_service: SessionService,
    db,
) -> AuthResponse:
    device_id = get_device_fingerprint(request)
    session = await session_service.create_session(
        user_id=str(user.id),
        device_id=device_id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    refresh_jti = str(uuid4())
    access_token, refresh_token = _build_auth_payloads(
        user,
        session_id=session.session_id,
        device_id=device_id,
        refresh_jti=refresh_jti,
    )
    await session_service.bind_refresh_jti(session.session_id, refresh_jti)
    csrf_token = generate_csrf_token(session.session_id)
    _set_auth_cookies(
        response,
        access_token=access_token,
        refresh_token=refresh_token,
        csrf_token=csrf_token,
    )
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=_serialize_user(user),
    )


async def get_current_user(request: Request, db=Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = getattr(request.state, "auth_payload", None)
    if payload is None:
        token = extract_access_token_from_request(request)
        if not token:
            raise credentials_exception
        try:
            payload = decode_access_token(token)
        except HTTPException as exc:
            raise credentials_exception from exc

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    query = select(User).where(User.id == parse_subject_uuid(user_id))
    try:
        result = await db.execute(query)
    except Exception as exc:
        if _is_database_unavailable_error(exc):
            _raise_database_unavailable(exc)
        raise
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled"
        )
    return user


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    user_data: UserRegister,
    request: Request,
    response: Response,
    db=Depends(get_db),
):
    _check_rate_limit(f"register:{user_data.email.lower()}")
    if not user_data.invite_token:
        raise AppError(
            code="PASSWORD_REGISTRATION_DISABLED",
            message=(
                "Password registration is disabled. Continue with Google or sign in "
                "to an existing account."
            ),
            status_code=status.HTTP_403_FORBIDDEN,
        )
    email = normalize_email(user_data.email)
    try:
        existing_matches = await _lookup_users_by_canonical_email(db, email)
    except Exception as exc:
        if _is_database_unavailable_error(exc):
            _raise_database_unavailable(exc)
        raise
    if existing_matches:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )
    if len(user_data.password) < 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 12 characters",
        )
    try:
        invitation = await consume_invitation(db, user_data.invite_token, email)
    except Exception:
        await db.rollback()
        raise
    user = User(
        id=uuid4(),
        email=email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=invitation.role,
        organization_id=invitation.organization_id,
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except Exception as exc:
        await db.rollback()
        if _is_database_unavailable_error(exc):
            _raise_database_unavailable(exc)
        raise

    session_service = SessionService(getattr(request.app.state, "redis", None))
    auth_response = await _issue_auth_response(
        response=response,
        user=user,
        request=request,
        session_service=session_service,
        db=db,
    )
    logger.info("New user registered via invitation: %s", user.email)
    return auth_response


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    payload: InvitationRequest,
    owner: User = Depends(get_current_user),
    db=Depends(get_db),
):
    invitation, token = await issue_invitation(db, owner, payload.email, payload.role)
    await db.commit()
    return {
        "id": str(invitation.id),
        "email": invitation.email,
        "role": invitation.role,
        "expires_at": invitation.expires_at,
        "invite_token": token,
    }


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invitation(
    invitation_id: UUID,
    owner: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await revoke_invitation(db, owner, invitation_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/social-login", response_model=AuthResponse)
async def social_login(
    payload: SocialLoginRequest,
    request: Request,
    response: Response,
    db=Depends(get_db),
):
    import jwt as pyjwt

    if payload.provider not in {"google", "facebook"}:
        raise AppError(
            code="SOCIAL_PROVIDER_UNSUPPORTED",
            message="This social sign-in provider is not supported.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # Supabase JWTs are signed with a secret.
        # For security, the user must provide SUPABASE_JWT_SECRET in .env
        if not settings.SUPABASE_JWT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Supabase JWT secret not configured",
            )

        decoded = pyjwt.decode(
            payload.token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except Exception as e:
        logger.error("Social login token verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid social login token",
        )

    supabase_uid = decoded.get("sub")
    if not isinstance(supabase_uid, str) or not supabase_uid.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid social login token",
        )
    canonical_user = await _fetch_supabase_user(payload.token)
    supabase_uid, email, user_metadata = _confirmed_social_identity(
        decoded=decoded,
        canonical_user=canonical_user,
        requested_provider=payload.provider,
    )
    full_name = user_metadata.get("full_name") or user_metadata.get("name")
    avatar_url = user_metadata.get("avatar_url") or user_metadata.get("picture")

    try:
        user = await _lookup_user_by_provider_id(db, supabase_uid)
        email_matches = await _lookup_users_by_canonical_email(db, email)
    except Exception as exc:
        if _is_database_unavailable_error(exc):
            _raise_database_unavailable(exc)
        raise

    email_owner = email_matches[0] if email_matches else None
    if user is not None and email_owner is not None and email_owner.id != user.id:
        raise AppError(
            code="SOCIAL_ACCOUNT_LINK_REQUIRED",
            message=(
                "This social account is not linked to the account that owns this email."
            ),
            status_code=status.HTTP_409_CONFLICT,
        )
    if user is None and email_owner is not None:
        raise AppError(
            code="SOCIAL_ACCOUNT_LINK_REQUIRED",
            message=(
                "This social account is not linked to the account that owns this email."
            ),
            status_code=status.HTTP_409_CONFLICT,
        )

    new_user_created = False
    if not user:
        if not payload.invite_token:
            raise AppError(
                code="INVITATION_REQUIRED",
                message="An invitation is required to create an account.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        new_user = User(
            id=uuid4(),
            email=email,
            hashed_password=DUMMY_PASSWORD_HASH,
            full_name=full_name,
            is_active=True,
            provider=payload.provider,
            provider_id=supabase_uid,
            avatar_url=avatar_url,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        try:
            invitation = await consume_invitation(db, payload.invite_token, email)
            new_user.role = invitation.role
            new_user.organization_id = invitation.organization_id
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
        except IntegrityError as exc:
            await db.rollback()
            try:
                race_winner = await _lookup_user_by_provider_id(db, supabase_uid)
                raced_email_matches = await _lookup_users_by_canonical_email(db, email)
            except Exception as lookup_exc:
                if _is_database_unavailable_error(lookup_exc):
                    _raise_database_unavailable(lookup_exc)
                raise exc from lookup_exc
            raced_email_owner = raced_email_matches[0] if raced_email_matches else None
            if race_winner is None and raced_email_owner is None:
                raise
            if race_winner is None or (
                raced_email_owner is not None
                and raced_email_owner.id != race_winner.id
            ):
                raise AppError(
                    code="SOCIAL_ACCOUNT_LINK_REQUIRED",
                    message=(
                        "This social account is not linked to the account that owns this email."
                    ),
                    status_code=status.HTTP_409_CONFLICT,
                ) from exc
            user = race_winner
            user.email = email
            try:
                await db.commit()
            except IntegrityError as retry_exc:
                await db.rollback()
                raise AppError(
                    code="SOCIAL_ACCOUNT_LINK_REQUIRED",
                    message="This social account is not linked to the account that owns this email.",
                    status_code=status.HTTP_409_CONFLICT,
                ) from retry_exc
        except Exception as exc:
            await db.rollback()
            if _is_database_unavailable_error(exc):
                _raise_database_unavailable(exc)
            raise
        else:
            user = new_user
            new_user_created = True

            # ── AUTOMATION: Welcome email for social signup ──
            try:
                if user.organization_id:
                    from app.services.automation_email_service import AutomationEmailService

                    automation_svc = AutomationEmailService(db)
                    await automation_svc.trigger_welcome(
                        organization_id=user.organization_id,
                        customer_email=user.email,
                        customer_name=full_name or user.email.split("@")[0],
                    )
            except Exception as exc:
                logger.warning(
                    "Welcome email automation skipped for social signup: %s", exc
                )

            logger.info("Created new social user: %s via %s", email, payload.provider)

    if not new_user_created:
        # Existing users authenticate only through their stored provider subject.
        changed = user.email != email
        user.email = email
        if user.provider != payload.provider:
            user.provider = payload.provider
            changed = True
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
            changed = True

        subject_user_id = user.id
        user.last_login_at = datetime.now(UTC)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            try:
                raced_email_matches = await _lookup_users_by_canonical_email(db, email)
            except Exception as lookup_exc:
                if _is_database_unavailable_error(lookup_exc):
                    _raise_database_unavailable(lookup_exc)
                raise exc from lookup_exc
            raced_email_owner = (
                raced_email_matches[0] if raced_email_matches else None
            )
            if (
                raced_email_owner is not None
                and raced_email_owner.id != subject_user_id
            ):
                raise AppError(
                    code="SOCIAL_ACCOUNT_LINK_REQUIRED",
                    message=(
                        "This social account is not linked to the account that owns this email."
                    ),
                    status_code=status.HTTP_409_CONFLICT,
                ) from exc
            raise
        except Exception as exc:
            if _is_database_unavailable_error(exc):
                _raise_database_unavailable(exc)
            raise
        if changed:
            logger.info(
                "Updated social profile metadata for existing user: %s",
                email,
            )

    session_service = SessionService(getattr(request.app.state, "redis", None))
    auth_response = await _issue_auth_response(
        response=response,
        user=user,
        request=request,
        session_service=session_service,
        db=db,
    )

    try:
        await log_audit_event(
            db=db,
            action="auth.social_login",
            event_type="login_success",
            event_category="auth",
            metadata={"provider": payload.provider, "email": email},
            user_id=str(user.id),
            session_id=decode_access_token(auth_response.access_token).get(
                "session_id"
            ),
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_path=str(request.url.path),
            request_method=request.method,
        )
        await db.commit()
    except Exception as exc:
        logger.warning("Auth social login audit logging skipped: %s", exc)
    return auth_response


@router.post("/login", response_model=AuthResponse)
async def login(request: Request, response: Response, db=Depends(get_db)):
    content_type = (request.headers.get("content-type") or "").lower()
    raw_body = await request.body()
    email = ""
    password = ""
    form = None

    if (not email or not password) and "application/json" in content_type:
        try:
            import json as _json

            payload = _json.loads(raw_body.decode("utf-8", errors="ignore") or "{}")
            if isinstance(payload, dict):
                email = (
                    str(payload.get("email") or payload.get("username") or "")
                    .strip()
                    .lower()
                )
                password = str(payload.get("password") or "")
        except Exception:
            pass

    if (
        not email or not password
    ) and "application/x-www-form-urlencoded" in content_type:
        try:
            from urllib.parse import parse_qs

            parsed = parse_qs(raw_body.decode("utf-8", errors="ignore"))
            email = str((parsed.get("username") or [""])[0]).strip().lower()
            password = str((parsed.get("password") or [""])[0])
        except Exception:
            pass

    if not email or not password:
        try:
            form = await request.form()
            email = str(form.get("username") or "").strip().lower()
            password = str(form.get("password") or "")
        except Exception:
            pass

    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing credentials"
        )

    _check_rate_limit(email)

    session_service = SessionService(getattr(request.app.state, "redis", None))
    identifier = f"login:{email}"

    try:
        user = await _lookup_user_by_email(db, email)
    except Exception as exc:
        if _is_database_unavailable_error(exc):
            _raise_database_unavailable(exc)
        raise

    if (
        not user
        or user.provider is not None
        or user.provider_id is not None
        or not verify_password(password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user.last_login_at = datetime.now(UTC)
    try:
        await db.commit()
    except Exception as exc:
        if _is_database_unavailable_error(exc):
            _raise_database_unavailable(exc)
        raise

    auth_response = await _issue_auth_response(
        response=response,
        user=user,
        request=request,
        session_service=session_service,
        db=db,
    )
    await session_service.record_successful_login(
        user_id=str(user.id),
        identifier=identifier,
        device_id=get_device_fingerprint(request),
    )
    payload = decode_access_token(auth_response.access_token)
    try:
        await log_audit_event(
            db=db,
            action="auth.login",
            event_type="login_success",
            event_category="auth",
            metadata={
                "risk_score": 0,
                "factors": [],
                "device_id": payload.get("device_id"),
            },
            user_id=str(user.id),
            session_id=str(payload.get("session_id") or ""),
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_path=str(request.url.path),
            request_method=request.method,
        )
        await db.commit()
    except Exception as exc:
        logger.warning("Auth login audit logging skipped: %s", exc)
    logger.info("User logged in: %s", user.email)
    return auth_response


@router.post("/refresh", response_model=Token)
async def refresh_token(request: Request, response: Response, db=Depends(get_db)):
    refresh_token = await _resolve_refresh_token(request)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
        )
    try:
        payload = decode_refresh_token(refresh_token)
        user_id = parse_subject_uuid(payload.get("sub"))
        session_id = str(payload.get("session_id") or "")
        old_jti = str(payload.get("jti") or "")
    except HTTPException as exc:
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    try:
        result = await db.execute(select(User).where(User.id == user_id))
    except Exception as exc:
        if _is_database_unavailable_error(exc):
            _raise_database_unavailable(exc)
        raise
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    session_service = SessionService(getattr(request.app.state, "redis", None))
    if not await session_service.is_session_active(session_id):
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is no longer active",
        )

    new_refresh_jti = str(uuid4())
    try:
        await session_service.rotate_refresh_token(
            old_jti=old_jti,
            session_id=session_id,
            new_jti=new_refresh_jti,
        )
    except RefreshTokenReuseDetected as exc:
        try:
            await log_audit_event(
                db=db,
                action="auth.refresh",
                event_type="refresh_token_reuse",
                event_category="security",
                severity="CRITICAL",
                outcome="blocked",
                success=False,
                metadata={"session_id": session_id, "jti": old_jti},
                user_id=str(user.id),
                session_id=session_id,
                ip_address=get_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                request_path=str(request.url.path),
                request_method=request.method,
            )
            await db.commit()
        except Exception as exc:
            logger.warning("Auth refresh reuse audit logging skipped: %s", exc)
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected",
        ) from exc

    access_token, next_refresh_token = _build_auth_payloads(
        user,
        session_id=session_id,
        device_id=str(payload.get("device_id") or get_device_fingerprint(request)),
        refresh_jti=new_refresh_jti,
    )
    _set_auth_cookies(
        response,
        access_token=access_token,
        refresh_token=next_refresh_token,
        csrf_token=generate_csrf_token(session_id),
    )
    try:
        await log_audit_event(
            db=db,
            action="auth.refresh",
            event_type="refresh_token_issued",
            event_category="auth",
            metadata={"session_id": session_id},
            user_id=str(user.id),
            session_id=session_id,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_path=str(request.url.path),
            request_method=request.method,
        )
        await db.commit()
    except Exception as exc:
        logger.warning("Auth refresh audit logging skipped: %s", exc)
    return Token(
        access_token=access_token, refresh_token=next_refresh_token, token_type="bearer"
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return _serialize_user(current_user)


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    request: Request,
    full_name: str | None = None,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    if full_name is not None:
        current_user.full_name = full_name
    current_user.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(current_user)
    await log_audit_event(
        db=db,
        action="auth.profile_update",
        event_type="profile_updated",
        event_category="auth",
        metadata={"full_name_updated": full_name is not None},
        user_id=str(current_user.id),
        session_id=getattr(request.state, "session_id", None),
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_path=str(request.url.path),
        request_method=request.method,
    )
    await db.commit()
    return _serialize_user(current_user)


@router.post("/change-password")
async def change_password(
    request: Request,
    response: Response,
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    if not verify_password(
        password_data.current_password, current_user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if len(password_data.new_password) < 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 12 characters",
        )

    current_user.hashed_password = get_password_hash(password_data.new_password)
    current_user.updated_at = datetime.now(UTC)
    await db.commit()

    session_service = SessionService(getattr(request.app.state, "redis", None))
    await session_service.invalidate_all_user_sessions(
        str(current_user.id), reason="password_change"
    )
    _clear_auth_cookies(response)
    await log_audit_event(
        db=db,
        action="auth.change_password",
        event_type="password_changed",
        event_category="auth",
        severity="HIGH",
        metadata={"email": current_user.email},
        user_id=str(current_user.id),
        session_id=getattr(request.state, "session_id", None),
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_path=str(request.url.path),
        request_method=request.method,
    )
    await db.commit()
    logger.info("Password changed for user: %s", current_user.email)
    return {"message": "Password changed successfully"}


@router.post("/logout")
async def logout(request: Request, response: Response):
    session_service = SessionService(getattr(request.app.state, "redis", None))
    token = extract_access_token_from_request(request)
    payload = None
    if token:
        try:
            payload = decode_access_token(token)
        except HTTPException:
            payload = None
    else:
        refresh_cookie = request.cookies.get(settings.REFRESH_COOKIE_NAME)
        if refresh_cookie:
            try:
                payload = decode_refresh_token(refresh_cookie)
            except HTTPException:
                payload = None

    if payload and payload.get("session_id"):
        await session_service.invalidate_session(
            str(payload["session_id"]), reason="logout"
        )
        await log_audit_event(
            app=request.app,
            action="auth.logout",
            event_type="logout",
            event_category="auth",
            metadata={"email": payload.get("email")},
            user_id=str(payload.get("sub") or ""),
            session_id=str(payload.get("session_id") or ""),
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_path=str(request.url.path),
            request_method=request.method,
        )

    _clear_auth_cookies(response)
    return {"message": "Logged out successfully"}
