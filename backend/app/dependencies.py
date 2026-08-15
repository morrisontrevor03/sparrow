import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        user_uuid = uuid.UUID(user_id)
    except (JWTError, ValueError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


@dataclass
class Principal:
    """
    Whoever is making this request, and what they're allowed to do.

    A session JWT from the web app carries every scope — the user is driving the
    UI directly. An OAuth access token carries only what they consented to when
    connecting the MCP client.
    """

    user: User
    scopes: frozenset[str]
    via: str  # "session" | "oauth"
    client_id: str | None = None

    def has(self, scope: str) -> bool:
        return scope in self.scopes

    def require(self, scope: str) -> None:
        if not self.has(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This connection is missing the '{scope}' scope",
            )


async def get_principal(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    """Resolve a bearer token that may be either a session JWT or an OAuth token."""
    from app.models.oauth import SCOPES
    from app.services import oauth as oauth_service

    # OAuth tokens are opaque random strings; JWTs have two dots. Try the JWT path
    # first and fall through, rather than sniffing the format.
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
        if user_id:
            user = (
                await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
            ).scalar_one_or_none()
            if user and user.is_active:
                return Principal(user=user, scopes=frozenset(SCOPES.keys()), via="session")
    except (JWTError, ValueError):
        pass

    record = await oauth_service.resolve_access_token(db, token)
    if record:
        user = (
            await db.execute(select(User).where(User.id == record.user_id))
        ).scalar_one_or_none()
        if user and user.is_active:
            await db.commit()
            return Principal(
                user=user,
                scopes=frozenset(record.scope.split()),
                via="oauth",
                client_id=record.client_id,
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
