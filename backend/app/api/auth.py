import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
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
from app.services.risk_engine import RiskEngine
from app.services.session_service import RefreshTokenReuseDetected, SessionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
risk_engine = RiskEngine()
DUMMY_PASSWORD_HASH = get_password_hash("not-the-real-password")
DATABASE_UNAVAILABLE_DETAIL = (
    "Database unavailable. Check DATABASE_URL connectivity and database reachability."
)


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


class SocialLoginRequest(BaseModel):
    token: str
    provider: str


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
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


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
    user_data: UserRegister, request: Request, response: Response, db=Depends(get_db)
):
    try:
        existing_user = await _lookup_user_by_email(db, user_data.email)
    except Exception as exc:
        if _is_database_unavailable_error(exc):
            _raise_database_unavailable(exc)
        raise
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )
    if len(user_data.password) < 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 12 characters",
        )

    user = User(
        id=uuid4(),
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role="user",
        is_active=True,
        totp_enabled=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except Exception as exc:
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
    await session_service.record_successful_login(
        user_id=str(user.id),
        identifier=f"login:{user.email.lower()}",
        device_id=get_device_fingerprint(request),
    )
    try:
        await log_audit_event(
            db=db,
            action="auth.register",
            event_type="register",
            event_category="auth",
            metadata={"email": user.email},
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
        logger.warning("Auth register audit logging skipped: %s", exc)

    # ── AUTOMATION: Welcome email ──
    try:
        if user.organization_id:
            from app.services.automation_email_service import AutomationEmailService

            automation_svc = AutomationEmailService(db)
            await automation_svc.trigger_welcome(
                organization_id=user.organization_id,
                customer_email=user.email,
                customer_name=user.full_name or user.email.split("@")[0],
            )
    except Exception as exc:
        logger.warning("Welcome email automation skipped: %s", exc)

    logger.info("New user registered: %s", user.email)
    return auth_response


@router.post("/social-login", response_model=AuthResponse)
async def social_login(
    payload: SocialLoginRequest,
    request: Request,
    response: Response,
    db=Depends(get_db),
):
    import jwt as pyjwt

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

    email = decoded.get("email")
    supabase_uid = decoded.get("sub")
    user_metadata = decoded.get("user_metadata", {})
    full_name = user_metadata.get("full_name") or user_metadata.get("name")
    avatar_url = user_metadata.get("avatar_url") or user_metadata.get("picture")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Social login provider did not return an email",
        )

    try:
        user = await _lookup_user_by_email(db, email)
    except Exception as exc:
        if _is_database_unavailable_error(exc):
            _raise_database_unavailable(exc)
        raise

    if not user:
        from datetime import datetime

        user = User(
            id=uuid4(),
            email=email,
            hashed_password=DUMMY_PASSWORD_HASH,
            full_name=full_name,
            role="user",
            is_active=True,
            provider=payload.provider,
            provider_id=supabase_uid,
            avatar_url=avatar_url,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(user)
        try:
            await db.commit()
            await db.refresh(user)
        except Exception as exc:
            if _is_database_unavailable_error(exc):
                _raise_database_unavailable(exc)
            raise

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
    else:
        from datetime import datetime

        # Update existing user with provider info if missing
        changed = False
        if not user.provider:
            user.provider = payload.provider
            user.provider_id = supabase_uid
            changed = True
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
            changed = True

        user.last_login_at = datetime.now(UTC)
        try:
            await db.commit()
        except Exception as exc:
            if _is_database_unavailable_error(exc):
                _raise_database_unavailable(exc)
            raise
        if changed:
            logger.info(
                "Linked social provider %s to existing user: %s",
                payload.provider,
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

    session_service = SessionService(getattr(request.app.state, "redis", None))
    identifier = f"login:{email}"

    try:
        user = await _lookup_user_by_email(db, email)
    except Exception as exc:
        if _is_database_unavailable_error(exc):
            _raise_database_unavailable(exc)
        raise

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from datetime import datetime

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
