from httpx import AsyncClient

from app.models.campaign import Campaign


async def test_create_and_list_campaign(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/campaigns",
        headers=auth_headers,
        json={
            "name": "Series B fintech",
            "campaign_type": "business_development",
            "objective": "Sell observability tooling to platform teams",
            "target_titles": ["VP of Engineering"],
            "target_companies": ["Ramp"],
            "status": "active",
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["name"] == "Series B fintech"
    assert created["campaign_type"] == "business_development"

    listed = await client.get("/api/campaigns", headers=auth_headers)
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [created["id"]]


async def test_unknown_campaign_type_is_rejected(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/campaigns",
        headers=auth_headers,
        json={"name": "Bad", "campaign_type": "telepathy", "target_titles": []},
    )
    assert resp.status_code == 422
    assert "campaign_type" in resp.json()["detail"]


async def test_campaigns_are_scoped_to_their_owner(
    client: AsyncClient, auth_headers, broke_auth_headers, campaign: Campaign
):
    mine = await client.get(f"/api/campaigns/{campaign.id}", headers=auth_headers)
    assert mine.status_code == 200

    theirs = await client.get(f"/api/campaigns/{campaign.id}", headers=broke_auth_headers)
    assert theirs.status_code == 404, "another user's campaign must not be readable"


async def test_run_without_credits_returns_402(
    client: AsyncClient, broke_auth_headers, broke_user, db
):
    created = await client.post(
        "/api/campaigns",
        headers=broke_auth_headers,
        json={
            "name": "Broke campaign",
            "campaign_type": "business_development",
            "target_titles": ["VP of Engineering"],
            "target_companies": ["Acme"],
        },
    )
    campaign_id = created.json()["id"]

    resp = await client.post(
        f"/api/campaigns/{campaign_id}/run", headers=broke_auth_headers, json={}
    )
    assert resp.status_code == 402
    assert "credits" in resp.json()["detail"].lower()


async def test_update_campaign_partially(client: AsyncClient, auth_headers, campaign: Campaign):
    resp = await client.patch(
        f"/api/campaigns/{campaign.id}",
        headers=auth_headers,
        json={"autopilot_enabled": True, "weekly_credit_cap": 250},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["autopilot_enabled"] is True
    assert body["weekly_credit_cap"] == 250
    # Untouched fields survive.
    assert body["name"] == campaign.name
    assert body["target_titles"] == campaign.target_titles


async def test_campaign_types_endpoint_lists_every_profile(client: AsyncClient):
    resp = await client.get("/api/campaigns/types")
    assert resp.status_code == 200
    keys = {t["key"] for t in resp.json()}
    assert keys == {
        "business_development",
        "job_search",
        "fundraising",
        "recruiting",
        "custom",
    }
