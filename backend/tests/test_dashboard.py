from httpx import AsyncClient


async def test_stats_new_user(client: AsyncClient, auth_headers):
    resp = await client.get("/api/dashboard/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["contacts_count"] == 0
    assert data["drafted_count"] == 0
    assert data["in_flight_count"] == 0
    assert data["campaign_count"] == 0
    assert data["active_campaign_count"] == 0

    assert data["credits"]["balance"] == 100
    assert data["credits"]["spent_this_week"] == 0

    setup = data["setup"]
    assert setup["profile_completed"] is False
    assert setup["resume_uploaded"] is False
    assert setup["campaign_created"] is False
    assert setup["first_run_completed"] is False


async def test_stats_reflects_a_campaign(client: AsyncClient, auth_headers, campaign):
    resp = await client.get("/api/dashboard/stats", headers=auth_headers)
    data = resp.json()
    assert data["campaign_count"] == 1
    assert data["active_campaign_count"] == 1
    assert data["setup"]["campaign_created"] is True


async def test_stats_requires_auth(client: AsyncClient):
    resp = await client.get("/api/dashboard/stats")
    assert resp.status_code == 401


async def test_activity_empty(client: AsyncClient, auth_headers):
    resp = await client.get("/api/dashboard/activity", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_activity_requires_auth(client: AsyncClient):
    resp = await client.get("/api/dashboard/activity")
    assert resp.status_code == 401
