"""
OAuth 2.1 authorization server for the Sparrow MCP endpoint.

Discovery documents are mounted at the ROOT (not under /api) because MCP clients
fetch `/.well-known/oauth-protected-resource` on the resource server's origin.
"""

import logging
import urllib.parse

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.oauth import SCOPES, OAuthToken
from app.models.user import User
from app.services import oauth

logger = logging.getLogger(__name__)

# Discovery lives at the root; everything else is namespaced.
discovery_router = APIRouter(tags=["oauth"])
router = APIRouter(prefix="/oauth", tags=["oauth"])


def _protected_resource_document() -> dict:
    issuer = oauth.issuer_url()
    return {
        "resource": oauth.canonical_resource(),
        "authorization_servers": [issuer],
        "scopes_supported": list(SCOPES.keys()),
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{settings.frontend_url.rstrip('/')}/docs/mcp",
    }


@discovery_router.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata():
    """RFC 9728 — tells an MCP client which authorization server guards /mcp."""
    return _protected_resource_document()


@discovery_router.get("/.well-known/oauth-protected-resource/{resource_path:path}")
async def protected_resource_metadata_for_path(resource_path: str):
    """
    RFC 9728 path-suffixed form.

    The MCP SDK's 401 advertises `/.well-known/oauth-protected-resource/mcp`
    (resource path appended), not the bare well-known path. Serving only the bare
    one means every client follows the header straight into a 404 and silently
    fails to connect — so both forms return the same document.
    """
    return _protected_resource_document()


@discovery_router.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata():
    """RFC 8414 — the authorization server's endpoints and capabilities."""
    issuer = oauth.issuer_url()
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth/authorize",
        "token_endpoint": f"{issuer}/oauth/token",
        "registration_endpoint": f"{issuer}/oauth/register",
        "revocation_endpoint": f"{issuer}/oauth/revoke",
        "scopes_supported": list(SCOPES.keys()),
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
    }


class ClientRegistration(BaseModel):
    client_name: str = Field(default="MCP Client", max_length=255)
    redirect_uris: list[str]
    scope: str | None = None
    client_uri: str | None = None
    token_endpoint_auth_method: str = "none"
    grant_types: list[str] | None = None
    response_types: list[str] | None = None


@router.post("/register", status_code=201)
async def register_client(body: ClientRegistration, db: AsyncSession = Depends(get_db)):
    """RFC 7591 dynamic client registration."""
    if not body.redirect_uris:
        raise HTTPException(status_code=400, detail="redirect_uris is required")

    for uri in body.redirect_uris:
        parsed = urllib.parse.urlparse(uri)
        # Localhost over http is explicitly allowed — that is how desktop MCP
        # clients receive the callback. Everything else must be https.
        is_loopback = parsed.hostname in ("127.0.0.1", "localhost", "::1")
        if parsed.scheme == "http" and not is_loopback:
            raise HTTPException(
                status_code=400, detail=f"redirect_uri must use https: {uri}"
            )
        if parsed.scheme not in ("http", "https") and not parsed.scheme:
            raise HTTPException(status_code=400, detail=f"invalid redirect_uri: {uri}")

    client, secret = await oauth.register_client(
        db,
        client_name=body.client_name,
        redirect_uris=body.redirect_uris,
        scope=body.scope,
        client_uri=body.client_uri,
        token_endpoint_auth_method=body.token_endpoint_auth_method,
    )

    response = {
        "client_id": client.client_id,
        "client_name": client.client_name,
        "redirect_uris": client.redirect_uris,
        "grant_types": client.grant_types,
        "token_endpoint_auth_method": client.token_endpoint_auth_method,
        "scope": client.scope,
    }
    if secret:
        response["client_secret"] = secret
    return response


def _error_redirect(redirect_uri: str, error: str, description: str, state: str | None) -> RedirectResponse:
    params = {"error": error, "error_description": description}
    if state:
        params["state"] = state
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(url=f"{redirect_uri}{sep}{urllib.parse.urlencode(params)}", status_code=302)


@router.get("/authorize")
async def authorize(
    client_id: str,
    redirect_uri: str,
    response_type: str = "code",
    scope: str | None = None,
    state: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str = "S256",
    resource: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Render the consent screen.

    Errors before the client is validated are shown as HTML — redirecting to an
    unvalidated redirect_uri would make this an open redirector.
    """
    client = await oauth.get_client(db, client_id)
    if not client:
        raise HTTPException(status_code=400, detail="Unknown client_id")
    if redirect_uri not in client.redirect_uris:
        raise HTTPException(status_code=400, detail="redirect_uri does not match this client")

    if response_type != "code":
        return _error_redirect(redirect_uri, "unsupported_response_type", "only 'code' is supported", state)
    if not code_challenge:
        return _error_redirect(redirect_uri, "invalid_request", "PKCE code_challenge is required", state)
    if code_challenge_method != "S256":
        return _error_redirect(redirect_uri, "invalid_request", "code_challenge_method must be S256", state)

    granted_scope = oauth.normalize_scope(scope or client.scope)

    # The consent form posts back to /oauth/authorize with the user's session
    # token, which the frontend attaches. If the user isn't signed in, the
    # frontend login page bounces them back here with `next`.
    login_url = (
        f"{settings.frontend_url.rstrip('/')}/oauth/consent?"
        + urllib.parse.urlencode(
            {
                "client_id": client_id,
                "client_name": client.client_name,
                "redirect_uri": redirect_uri,
                "scope": granted_scope,
                "state": state or "",
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "resource": resource or oauth.canonical_resource(),
            }
        )
    )
    return RedirectResponse(url=login_url, status_code=302)


class ConsentDecision(BaseModel):
    client_id: str
    redirect_uri: str
    scope: str
    state: str | None = None
    code_challenge: str
    code_challenge_method: str = "S256"
    resource: str | None = None
    approved: bool = True


@router.post("/consent")
async def submit_consent(
    body: ConsentDecision,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Called by the frontend consent screen with the user's session JWT.
    Returns the redirect URL for the browser to follow.
    """
    client = await oauth.get_client(db, body.client_id)
    if not client or body.redirect_uri not in client.redirect_uris:
        raise HTTPException(status_code=400, detail="Invalid client or redirect_uri")

    if not body.approved:
        params = {"error": "access_denied", "error_description": "User declined"}
        if body.state:
            params["state"] = body.state
        sep = "&" if "?" in body.redirect_uri else "?"
        return {"redirect_url": f"{body.redirect_uri}{sep}{urllib.parse.urlencode(params)}"}

    if body.code_challenge_method != "S256":
        raise HTTPException(status_code=400, detail="code_challenge_method must be S256")

    granted = oauth.normalize_scope(body.scope)
    code = await oauth.create_authorization_code(
        db,
        client=client,
        user_id=current_user.id,
        redirect_uri=body.redirect_uri,
        scope=granted,
        code_challenge=body.code_challenge,
        code_challenge_method=body.code_challenge_method,
        resource=body.resource or oauth.canonical_resource(),
    )

    params = {"code": code}
    if body.state:
        params["state"] = body.state
    sep = "&" if "?" in body.redirect_uri else "?"
    return {"redirect_url": f"{body.redirect_uri}{sep}{urllib.parse.urlencode(params)}"}


@router.post("/token")
async def token(
    grant_type: str = Form(...),
    code: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    client_id: str | None = Form(None),
    client_secret: str | None = Form(None),
    code_verifier: str | None = Form(None),
    refresh_token: str | None = Form(None),
    resource: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    if grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(status_code=400, detail={"error": "invalid_request"})
        tokens = await oauth.rotate_refresh_token(db, refresh_token)
        if not tokens:
            raise HTTPException(status_code=400, detail={"error": "invalid_grant"})
        return tokens

    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail={"error": "unsupported_grant_type"})

    if not code or not code_verifier or not client_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_request", "error_description": "code, code_verifier and client_id are required"},
        )

    client = await oauth.get_client(db, client_id)
    if not client:
        raise HTTPException(status_code=401, detail={"error": "invalid_client"})

    if client.client_secret_hash:
        if not client_secret or oauth.hash_secret(client_secret) != client.client_secret_hash:
            raise HTTPException(status_code=401, detail={"error": "invalid_client"})

    record = await oauth.consume_authorization_code(db, code)
    if not record or record.client_id != client_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_grant", "error_description": "code is invalid, expired, or already used"},
        )

    if redirect_uri and redirect_uri != record.redirect_uri:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_grant", "error_description": "redirect_uri mismatch"},
        )

    if not oauth.verify_pkce(code_verifier, record.code_challenge, record.code_challenge_method):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_grant", "error_description": "PKCE verification failed"},
        )

    # RFC 8707: if the client names a resource, it must be the one this code was
    # bound to. Silently issuing a token for a different audience is the exact
    # confused-deputy problem resource indicators exist to prevent.
    if resource and record.resource and resource.rstrip("/") != record.resource.rstrip("/"):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_target", "error_description": "resource does not match the authorization"},
        )

    return await oauth.issue_tokens(
        db, client_id, record.user_id, record.scope, record.resource
    )


@router.post("/revoke")
async def revoke(token: str = Form(...), db: AsyncSession = Depends(get_db)):
    # RFC 7009: always 200, even for an unknown token, so a caller can't probe.
    await oauth.revoke_token(db, token)
    return {"ok": True}


@router.get("/connections")
async def list_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Authorized MCP clients, for the Settings → Connections tab."""
    tokens = (
        (
            await db.execute(
                select(OAuthToken)
                .where(OAuthToken.user_id == current_user.id, OAuthToken.revoked_at.is_(None))
                .order_by(OAuthToken.created_at.desc())
            )
        )
        .unique()
        .scalars()
        .all()
    )
    return [
        {
            "id": str(t.id),
            "client_id": t.client_id,
            "client_name": t.client.client_name if t.client else t.client_id,
            "scope": t.scope.split(),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
        }
        for t in tokens
    ]


@router.delete("/connections/{token_id}", status_code=204)
async def revoke_connection(
    token_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = (
        await db.execute(
            select(OAuthToken).where(
                OAuthToken.id == token_id, OAuthToken.user_id == current_user.id
            )
        )
    ).unique().scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Connection not found")

    from datetime import datetime, timezone

    record.revoked_at = datetime.now(timezone.utc)
    await db.commit()
