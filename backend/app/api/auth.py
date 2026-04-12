import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import select

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
from app.middleware.auth import extract_access_token_from_request, get_client_ip, get_device_fingerprint
from app.middleware.security import generate_csrf_token
from app.models.user import User
from app.services.audit_service import log_audit_event
from app.services.risk_engine import RiskEngine, verify_totp_code
from app.services.session_service import RefreshTokenReuseDetected, SessionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
risk_engine = RiskEngine()
DUMMY_PASSWORD_HASH = get_password_hash("not-the-real-password")


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: Optional[str]
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
    response.set_cookie(settings.ACCESS_COOKIE_NAME, "", max_age=0, path="/api/v1", domain=domain)
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME, "", max_age=0, path="/api/v1/auth/refresh", domain=domain
    )
    response.set_cookie(settings.CSRF_COOKIE_NAME, "", max_age=0, path="/", domain=domain)


def _build_auth_payloads(user: User, *, session_id: str, device_id: str, refresh_jti: str) -> tuple[str, str]:
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
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
    return user


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, request: Request, response: Response, db=Depends(get_db)):
    existing_user = await _lookup_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    if len(user_data.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    user = User(
        id=uuid4(),
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role="user",
        is_active=True,
        totp_enabled=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

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
    await log_audit_event(
        db=db,
        action="auth.register",
        event_type="register",
        event_category="auth",
        metadata={"email": user.email},
        user_id=str(user.id),
        session_id=decode_access_token(auth_response.access_token).get("session_id"),
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_path=str(request.url.path),
        request_method=request.method,
    )
    await db.commit()
    logger.info("New user registered: %s", user.email)
    return auth_response


@router.post("/login", response_model=AuthResponse)
async def login(request: Request, response: Response, db=Depends(get_db)):
    form = await request.form()
    email = str(form.get("username") or "").strip().lower()
    password = str(form.get("password") or "")
    totp_code = str(form.get("totp_code") or "").strip()
    if not email or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing credentials")

    session_service = SessionService(getattr(request.app.state, "redis", None))
    identifier = f"login:{email}"
    lockout_status = await session_service.check_lockout(identifier)
    if lockout_status.is_locked:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account temporarily locked")

    user = await _lookup_user_by_email(db, email)
    hashed_password = user.hashed_password if user else DUMMY_PASSWORD_HASH
    password_valid = verify_password(password, hashed_password)
    if not user or not password_valid:
        result = await session_service.record_failed_login(
            identifier=identifier,
            ip_address=get_client_ip(request),
        )
        await log_audit_event(
            db=db,
            action="auth.login",
            event_type="login_failure",
            event_category="auth",
            severity="WARNING",
            outcome="failure",
            success=False,
            metadata={"email": email, "lockout_imminent": result.failures_in_window >= 4},
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_path=str(request.url.path),
            request_method=request.method,
        )
        await db.commit()
        if result.is_locked:
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account temporarily locked")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")

    risk = risk_engine.evaluate_login(
        user=user,
        device_fingerprint=get_device_fingerprint(request),
        ip_address=get_client_ip(request),
        known_devices=await session_service.get_known_devices(str(user.id)),
        prior_failures=lockout_status.failures_in_window,
        recent_login_count=await session_service.recent_login_count(str(user.id)),
    )
    if risk.should_block:
        await log_audit_event(
            db=db,
            action="auth.login",
            event_type="login_blocked",
            event_category="security",
            severity="CRITICAL",
            outcome="blocked",
            success=False,
            metadata={"email": email, "risk_score": risk.total, "factors": risk.factors},
            user_id=str(user.id),
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_path=str(request.url.path),
            request_method=request.method,
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="High-risk authentication blocked")

    if risk.requires_step_up:
        if not user.totp_enabled or not user.totp_secret or not verify_totp_code(user.totp_secret, totp_code):
            await log_audit_event(
                db=db,
                action="auth.login",
                event_type="totp_required",
                event_category="auth",
                severity="HIGH",
                outcome="blocked",
                success=False,
                metadata={"email": email, "risk_score": risk.total, "factors": risk.factors},
                user_id=str(user.id),
                ip_address=get_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                request_path=str(request.url.path),
                request_method=request.method,
            )
            await db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="TOTP step-up authentication required")

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

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
    await log_audit_event(
        db=db,
        action="auth.login",
        event_type="login_success",
        event_category="auth",
        metadata={"risk_score": risk.total, "factors": risk.factors, "device_id": payload.get("device_id")},
        user_id=str(user.id),
        session_id=str(payload.get("session_id") or ""),
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_path=str(request.url.path),
        request_method=request.method,
    )
    await db.commit()
    logger.info("User logged in: %s", user.email)
    return auth_response


@router.post("/refresh", response_model=Token)
async def refresh_token(request: Request, response: Response, db=Depends(get_db)):
    refresh_token = await _resolve_refresh_token(request)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    try:
        payload = decode_refresh_token(refresh_token)
        user_id = parse_subject_uuid(payload.get("sub"))
        session_id = str(payload.get("session_id") or "")
        old_jti = str(payload.get("jti") or "")
    except HTTPException as exc:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    session_service = SessionService(getattr(request.app.state, "redis", None))
    if not await session_service.is_session_active(session_id):
        _clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer active")

    new_refresh_jti = str(uuid4())
    try:
        await session_service.rotate_refresh_token(
            old_jti=old_jti,
            session_id=session_id,
            new_jti=new_refresh_jti,
        )
    except RefreshTokenReuseDetected as exc:
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
        _clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token reuse detected") from exc

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
    return Token(access_token=access_token, refresh_token=next_refresh_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return _serialize_user(current_user)


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    request: Request,
    full_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    if full_name is not None:
        current_user.full_name = full_name
    current_user.updated_at = datetime.now(timezone.utc)
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
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if len(password_data.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters",
        )

    current_user.hashed_password = get_password_hash(password_data.new_password)
    current_user.updated_at = datetime.now(timezone.utc)
    await db.commit()

    session_service = SessionService(getattr(request.app.state, "redis", None))
    await session_service.invalidate_all_user_sessions(str(current_user.id), reason="password_change")
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
        await session_service.invalidate_session(str(payload["session_id"]), reason="logout")
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
