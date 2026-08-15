"""
OAuth 2.1 authorization-server tests.

The three properties that actually matter for security: PKCE is enforced, codes
are single-use, and scope is honored on the resource side.
"""

import base64
import hashlib

from httpx import AsyncClient

from app.services import oauth

REDIRECT_URI = "http://127.0.0.1:33418/callback"


def pkce_pair() -> tuple[str, str]:
    verifier = "a" * 64
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


async def register(client: AsyncClient) -> str:
    resp = await client.post(
        "/oauth/register",
        json={"client_name": "Test MCP Client", "redirect_uris": [REDIRECT_URI]},
    )
    assert resp.status_code == 201
    return resp.json()["client_id"]


async def authorize(client: AsyncClient, auth_headers, client_id: str, challenge: str) -> str:
    """Approve consent and pull the code out of the returned redirect URL."""
    resp = await client.post(
        "/oauth/consent",
        headers=auth_headers,
        json={
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": "contacts:read campaigns:read",
            "state": "xyz",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "approved": True,
        },
    )
    assert resp.status_code == 200
    url = resp.json()["redirect_url"]
    assert "state=xyz" in url
    return url.split("code=")[1].split("&")[0]


async def test_discovery_documents_are_served_at_the_root(client: AsyncClient):
    prm = await client.get("/.well-known/oauth-protected-resource")
    assert prm.status_code == 200
    assert prm.json()["resource"].endswith("/mcp")

    # The MCP SDK's 401 advertises the path-suffixed form; both must resolve or
    # clients follow the WWW-Authenticate header into a 404.
    suffixed = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert suffixed.status_code == 200
    assert suffixed.json() == prm.json()

    asm = await client.get("/.well-known/oauth-authorization-server")
    assert asm.status_code == 200
    assert asm.json()["code_challenge_methods_supported"] == ["S256"]


async def test_full_authorization_code_flow(client: AsyncClient, auth_headers):
    client_id = await register(client)
    verifier, challenge = pkce_pair()
    code = await authorize(client, auth_headers, client_id, challenge)

    resp = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "code_verifier": verifier,
            "redirect_uri": REDIRECT_URI,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "Bearer"
    assert body["scope"] == "contacts:read campaigns:read"
    assert body["access_token"] and body["refresh_token"]


async def test_wrong_pkce_verifier_is_rejected(client: AsyncClient, auth_headers):
    client_id = await register(client)
    _, challenge = pkce_pair()
    code = await authorize(client, auth_headers, client_id, challenge)

    resp = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "code_verifier": "b" * 64,
            "redirect_uri": REDIRECT_URI,
        },
    )
    assert resp.status_code == 400


async def test_authorization_code_is_single_use(client: AsyncClient, auth_headers):
    client_id = await register(client)
    verifier, challenge = pkce_pair()
    code = await authorize(client, auth_headers, client_id, challenge)

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "code_verifier": verifier,
        "redirect_uri": REDIRECT_URI,
    }
    assert (await client.post("/oauth/token", data=payload)).status_code == 200
    assert (await client.post("/oauth/token", data=payload)).status_code == 400


async def test_refresh_token_rotates_and_old_one_dies(client: AsyncClient, auth_headers):
    client_id = await register(client)
    verifier, challenge = pkce_pair()
    code = await authorize(client, auth_headers, client_id, challenge)

    first = (
        await client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "code_verifier": verifier,
                "redirect_uri": REDIRECT_URI,
            },
        )
    ).json()

    refreshed = await client.post(
        "/oauth/token",
        data={"grant_type": "refresh_token", "refresh_token": first["refresh_token"]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != first["access_token"]

    replay = await client.post(
        "/oauth/token",
        data={"grant_type": "refresh_token", "refresh_token": first["refresh_token"]},
    )
    assert replay.status_code == 400, "a rotated refresh token must not work twice"


async def test_declined_consent_returns_access_denied(client: AsyncClient, auth_headers):
    client_id = await register(client)
    _, challenge = pkce_pair()
    resp = await client.post(
        "/oauth/consent",
        headers=auth_headers,
        json={
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": "contacts:read",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "approved": False,
        },
    )
    assert "error=access_denied" in resp.json()["redirect_url"]


async def test_redirect_uri_must_match_registration(client: AsyncClient, auth_headers):
    client_id = await register(client)
    _, challenge = pkce_pair()
    resp = await client.post(
        "/oauth/consent",
        headers=auth_headers,
        json={
            "client_id": client_id,
            "redirect_uri": "https://evil.example.com/steal",
            "scope": "contacts:read",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "approved": True,
        },
    )
    assert resp.status_code == 400


async def test_oauth_token_grants_only_its_scopes(client: AsyncClient, auth_headers):
    """A token without campaigns:read must not read campaigns."""
    client_id = await register(client)
    verifier, challenge = pkce_pair()

    consent = await client.post(
        "/oauth/consent",
        headers=auth_headers,
        json={
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": "profile:read",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "approved": True,
        },
    )
    code = consent.json()["redirect_url"].split("code=")[1].split("&")[0]

    tokens = (
        await client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "code_verifier": verifier,
                "redirect_uri": REDIRECT_URI,
            },
        )
    ).json()

    assert tokens["scope"] == "profile:read"
    assert not oauth.has_scope(tokens["scope"], "campaigns:read")
    assert oauth.has_scope(tokens["scope"], "profile:read")


async def test_revoked_token_stops_resolving(client: AsyncClient, auth_headers, db):
    client_id = await register(client)
    verifier, challenge = pkce_pair()
    code = await authorize(client, auth_headers, client_id, challenge)

    tokens = (
        await client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "code_verifier": verifier,
                "redirect_uri": REDIRECT_URI,
            },
        )
    ).json()

    assert await oauth.resolve_access_token(db, tokens["access_token"]) is not None

    await client.post("/oauth/revoke", data={"token": tokens["access_token"]})
    assert await oauth.resolve_access_token(db, tokens["access_token"]) is None


def test_pkce_rejects_plain_method():
    verifier, challenge = pkce_pair()
    assert oauth.verify_pkce(verifier, challenge, "S256") is True
    assert oauth.verify_pkce(verifier, challenge, "plain") is False


def test_unknown_scopes_are_dropped_not_granted():
    # Clients over-request routinely; we drop what we don't recognize rather
    # than failing the whole authorization.
    assert oauth.normalize_scope("contacts:read admin:everything") == "contacts:read"
    assert oauth.normalize_scope("") == oauth.DEFAULT_SCOPES
    assert oauth.normalize_scope("admin:everything") == oauth.DEFAULT_SCOPES
