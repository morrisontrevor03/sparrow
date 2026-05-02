import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import create_access_token, get_current_user, hash_password, verify_password
from app.models.subscription import Subscription
from app.models.user import User, UserPreferences
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.email_service import send_email, verification_email

router = APIRouter(prefix="/api/auth", tags=["auth"])

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def _google_redirect_uri() -> str:
    return f"{settings.backend_url.rstrip('/')}/api/auth/google/callback"


def _make_verification_token() -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    return token, expires


@router.get("/google/login")
async def google_login():
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    google_url = f"{_GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    resp = RedirectResponse(url=google_url, status_code=302)
    resp.set_cookie(
        "oauth_state", state,
        httponly=True, samesite="lax", max_age=600,
        secure=settings.environment == "production",
    )
    return resp


@router.get("/google/callback")
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    frontend_url = settings.frontend_url.rstrip("/")

    if error or not code:
        return RedirectResponse(url=f"{frontend_url}/login?error=oauth_denied", status_code=302)

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(_GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": _google_redirect_uri(),
            "grant_type": "authorization_code",
        })
        if token_resp.status_code != 200:
            return RedirectResponse(url=f"{frontend_url}/login?error=oauth_failed", status_code=302)

        google_access_token = token_resp.json().get("access_token")
        userinfo_resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {google_access_token}"},
        )
        if userinfo_resp.status_code != 200:
            return RedirectResponse(url=f"{frontend_url}/login?error=oauth_failed", status_code=302)

    info = userinfo_resp.json()
    google_id: str = info["id"]
    email: str = info["email"]
    full_name: str | None = info.get("name")

    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    new_user = False
    if not user:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            user.google_id = google_id
            user.is_verified = True  # Google already verified this email
        else:
            new_user = True
            user = User(
                email=email,
                hashed_password=None,
                full_name=full_name,
                google_id=google_id,
                is_verified=True,  # Google already verified this email
            )
            db.add(user)
            await db.flush()
            db.add(UserPreferences(user_id=user.id))
            db.add(Subscription(user_id=user.id, plan="free"))
    else:
        # Ensure existing Google users are marked verified
        if not user.is_verified:
            user.is_verified = True

    await db.commit()
    await db.refresh(user)

    app_token = create_access_token(user.id)
    dest = "onboarding" if new_user else "dashboard"
    resp = RedirectResponse(
        url=f"{frontend_url}/oauth-callback?token={app_token}&next={dest}",
        status_code=302,
    )
    resp.delete_cookie("oauth_state")
    return resp


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    token, expires = _make_verification_token()
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        is_verified=False,
        verification_token=token,
        verification_token_expires=expires,
    )
    db.add(user)
    await db.flush()

    db.add(UserPreferences(user_id=user.id))
    db.add(Subscription(user_id=user.id, plan="free"))

    await db.commit()
    await db.refresh(user)

    verify_url = f"{settings.backend_url.rstrip('/')}/api/auth/verify-email?token={token}"
    await send_email(user.email, "Verify your ApplyNow account", verification_email(verify_url))

    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/verify-email")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    frontend_url = settings.frontend_url.rstrip("/")

    result = await db.execute(select(User).where(User.verification_token == token))
    user = result.scalar_one_or_none()

    if not user:
        return RedirectResponse(url=f"{frontend_url}/login?error=invalid_token", status_code=302)

    now = datetime.now(timezone.utc)
    if user.verification_token_expires and user.verification_token_expires < now:
        return RedirectResponse(url=f"{frontend_url}/login?error=token_expired", status_code=302)

    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    await db.commit()

    return RedirectResponse(url=f"{frontend_url}/login?verified=true", status_code=302)


@router.post("/resend-verification")
async def resend_verification(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.is_verified:
        raise HTTPException(status_code=400, detail="Email already verified")

    token, expires = _make_verification_token()
    current_user.verification_token = token
    current_user.verification_token_expires = expires
    await db.commit()

    verify_url = f"{settings.backend_url.rstrip('/')}/api/auth/verify-email?token={token}"
    sent = await send_email(current_user.email, "Verify your ApplyNow account", verification_email(verify_url))
    if not sent:
        raise HTTPException(status_code=503, detail="Failed to send verification email — try again shortly")

    return {"ok": True}


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    # JWT is stateless — actual invalidation happens client-side by clearing the token.
    return {"ok": True}
