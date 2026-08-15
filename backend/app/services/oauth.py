"""
OAuth 2.1 authorization server primitives for the MCP endpoint.

Design notes:
  - Codes and tokens are stored as SHA-256 hashes. They are high-entropy random
    strings, not passwords, so a fast hash is the right choice — bcrypt here would
    add latency to every MCP request for no security gain.
  - PKCE S256 is mandatory. `plain` is rejected outright.
  - Refresh tokens rotate: redeeming one revokes it and issues a new pair.
"""

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.oauth import (
    DEFAULT_SCOPES,
    SCOPES,
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthToken,
)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(48)


def verify_pkce(verifier: str, challenge: str, method: str) -> bool:
    """S256 only. A `plain` challenge is not accepted regardless of what's stored."""
    if method != "S256":
        return False
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(expected, challenge)


def normalize_scope(requested: str | None) -> str:
    """Drop unknown scopes rather than erroring — clients over-request routinely."""
    if not requested:
        return DEFAULT_SCOPES
    granted = [s for s in requested.split() if s in SCOPES]
    return " ".join(granted) if granted else DEFAULT_SCOPES


def has_scope(token_scope: str, required: str) -> bool:
    return required in token_scope.split()


def issuer_url() -> str:
    return settings.backend_url.rstrip("/")


def canonical_resource() -> str:
    """The RFC 8707 resource identifier for this MCP server."""
    return f"{issuer_url()}/mcp"


async def get_client(db: AsyncSession, client_id: str) -> OAuthClient | None:
    return (
        await db.execute(select(OAuthClient).where(OAuthClient.client_id == client_id))
    ).scalar_one_or_none()


async def register_client(
    db: AsyncSession,
    client_name: str,
    redirect_uris: list[str],
    scope: str | None = None,
    client_uri: str | None = None,
    token_endpoint_auth_method: str = "none",
) -> tuple[OAuthClient, str | None]:
    """Returns (client, plaintext_secret). The secret is None for public clients."""
    client_id = f"mcp_{secrets.token_urlsafe(18)}"
    secret_plain: str | None = None
    secret_hash: str | None = None

    if token_endpoint_auth_method != "none":
        secret_plain = secrets.token_urlsafe(32)
        secret_hash = hash_secret(secret_plain)

    client = OAuthClient(
        client_id=client_id,
        client_secret_hash=secret_hash,
        client_name=client_name[:255],
        redirect_uris=redirect_uris,
        grant_types=["authorization_code", "refresh_token"],
        token_endpoint_auth_method=token_endpoint_auth_method,
        scope=normalize_scope(scope),
        client_uri=client_uri,
    )
    db.add(client)
    await db.commit()
    return client, secret_plain


async def create_authorization_code(
    db: AsyncSession,
    client: OAuthClient,
    user_id: uuid.UUID,
    redirect_uri: str,
    scope: str,
    code_challenge: str,
    code_challenge_method: str,
    resource: str | None,
) -> str:
    code = generate_token()
    db.add(
        OAuthAuthorizationCode(
            code_hash=hash_secret(code),
            client_id=client.client_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scope=scope,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            resource=resource,
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=settings.oauth_authorization_code_ttl_seconds),
        )
    )
    await db.commit()
    return code


async def consume_authorization_code(
    db: AsyncSession, code: str
) -> OAuthAuthorizationCode | None:
    """
    Fetch and mark a code used, atomically enough for our purposes: the row is
    re-checked for `used_at` before being marked, and a replayed code returns None.
    """
    record = (
        await db.execute(
            select(OAuthAuthorizationCode).where(
                OAuthAuthorizationCode.code_hash == hash_secret(code)
            )
        )
    ).scalar_one_or_none()

    if not record or record.used_at is not None:
        return None
    if record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return None

    record.used_at = datetime.now(timezone.utc)
    await db.flush()
    return record


async def issue_tokens(
    db: AsyncSession,
    client_id: str,
    user_id: uuid.UUID,
    scope: str,
    resource: str | None,
) -> dict:
    access_token = generate_token()
    refresh_token = generate_token()
    now = datetime.now(timezone.utc)

    db.add(
        OAuthToken(
            access_token_hash=hash_secret(access_token),
            refresh_token_hash=hash_secret(refresh_token),
            client_id=client_id,
            user_id=user_id,
            scope=scope,
            resource=resource,
            expires_at=now + timedelta(seconds=settings.oauth_access_token_ttl_seconds),
            refresh_expires_at=now
            + timedelta(seconds=settings.oauth_refresh_token_ttl_seconds),
        )
    )
    await db.commit()

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": settings.oauth_access_token_ttl_seconds,
        "refresh_token": refresh_token,
        "scope": scope,
    }


async def rotate_refresh_token(db: AsyncSession, refresh_token: str) -> dict | None:
    """Redeem a refresh token, revoking it and issuing a fresh pair."""
    record = (
        await db.execute(
            select(OAuthToken).where(
                OAuthToken.refresh_token_hash == hash_secret(refresh_token)
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if not record or record.revoked_at is not None:
        return None
    if (
        record.refresh_expires_at
        and record.refresh_expires_at.replace(tzinfo=timezone.utc) < now
    ):
        return None

    record.revoked_at = now
    await db.flush()

    return await issue_tokens(
        db, record.client_id, record.user_id, record.scope, record.resource
    )


async def resolve_access_token(db: AsyncSession, token: str) -> OAuthToken | None:
    record = (
        await db.execute(
            select(OAuthToken).where(OAuthToken.access_token_hash == hash_secret(token))
        )
    ).scalar_one_or_none()

    if not record or not record.is_active:
        return None

    record.last_used_at = datetime.now(timezone.utc)
    await db.flush()
    return record


async def revoke_token(db: AsyncSession, token: str) -> bool:
    """Revoke by access OR refresh token — RFC 7009 allows either."""
    token_hash = hash_secret(token)
    record = (
        await db.execute(
            select(OAuthToken).where(
                (OAuthToken.access_token_hash == token_hash)
                | (OAuthToken.refresh_token_hash == token_hash)
            )
        )
    ).scalar_one_or_none()

    if not record or record.revoked_at is not None:
        return False

    record.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return True
