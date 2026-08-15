"""
Guards for how the MCP transport is mounted.

The MCP app is mounted at the application root so that `/mcp` — the URL users
paste into their client — is served directly. Two things can silently break
that: registering a route after the mount (the mount swallows it), or mounting
at "/mcp" (which makes `/mcp` a 307 to `/mcp/`, and clients that drop the
Authorization header across redirects then fail to authenticate).
"""

from httpx import AsyncClient


async def test_health_still_reachable_past_the_root_mount(client: AsyncClient):
    """If this 404s, a route was registered after the root mount in main.py."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_api_routes_still_reachable_past_the_root_mount(client: AsyncClient):
    resp = await client.get("/api/campaigns/types")
    assert resp.status_code == 200


async def test_discovery_documents_still_reachable(client: AsyncClient):
    for path in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
        "/.well-known/oauth-authorization-server",
    ):
        assert (await client.get(path)).status_code == 200, path


async def test_mcp_answers_directly_without_redirect(client: AsyncClient):
    """`/mcp` must challenge for auth, not redirect to `/mcp/`."""
    resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert resp.status_code == 401, f"expected an auth challenge, got {resp.status_code}"

    # The header is how a client discovers where to authenticate; without it
    # connecting fails with no indication of why.
    www = resp.headers.get("www-authenticate", "")
    assert "resource_metadata=" in www, www
