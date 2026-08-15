"""
The Sparrow MCP server.

Mounted at /mcp on the main FastAPI app and authenticated with the same OAuth 2.1
tokens issued by app/routers/oauth.py. Every tool resolves the caller from the
bearer token, checks scope, and — where the tool does real work — spends credits.

Tools return structured data, not prose: an MCP client is a program, and prose
forces the model on the other side to re-parse what we already know.
"""

import logging
import uuid
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from pydantic import AnyHttpUrl
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.campaign import CAMPAIGN_TYPES, Campaign
from app.models.contact import Contact
from app.models.user import User
from app.services import credits, drafting, oauth, targeting
from app.services.agent_runner import pre_create_run, run_outreach

logger = logging.getLogger(__name__)


class SparrowTokenVerifier(TokenVerifier):
    """Resolves an opaque Sparrow access token against the oauth_tokens table."""

    async def verify_token(self, token: str) -> AccessToken | None:
        async with AsyncSessionLocal() as db:
            record = await oauth.resolve_access_token(db, token)
            if not record:
                return None
            await db.commit()
            return AccessToken(
                token=token,
                client_id=record.client_id,
                scopes=record.scope.split(),
                expires_at=int(record.expires_at.timestamp()),
                resource=record.resource,
                subject=str(record.user_id),
            )


mcp = MCPServer(
    name="sparrow",
    title="Sparrow",
    description="Find the right people at target companies and draft outreach to them.",
    instructions=(
        "Sparrow runs outreach campaigns. A campaign describes who the user wants to "
        "reach and why; running one finds matching people and drafts a first message "
        "to each. Discovery and drafting consume the user's prepaid credits — check "
        "get_credit_balance before starting large runs, and tell the user what a run "
        "will cost if they seem unaware."
    ),
    token_verifier=SparrowTokenVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(oauth.issuer_url()),
        resource_server_url=AnyHttpUrl(oauth.canonical_resource()),
        required_scopes=[],
    ),
)


class ToolError(Exception):
    """Surfaced to the MCP client as a tool error."""


def _require_scope(scope: str) -> AccessToken:
    token = get_access_token()
    if token is None:
        raise ToolError("Not authenticated. Reconnect this client to Sparrow.")
    if scope not in token.scopes:
        raise ToolError(
            f"This connection is missing the '{scope}' scope. Reconnect and grant it."
        )
    return token


def _user_id(token: AccessToken) -> uuid.UUID:
    return uuid.UUID(token.subject)


def _top_up_url() -> str:
    return f"{settings.frontend_url.rstrip('/')}/settings?tab=billing"


def _serialize_campaign(c: Campaign, contact_count: int | None = None) -> dict[str, Any]:
    data = {
        "id": str(c.id),
        "name": c.name,
        "type": c.campaign_type,
        "objective": c.objective,
        "status": c.status,
        "target_titles": c.target_titles or [],
        "target_companies": c.target_companies or [],
        "target_industries": c.target_industries or [],
        "target_locations": c.target_locations or [],
        "autopilot_enabled": c.autopilot_enabled,
        "weekly_credit_cap": c.weekly_credit_cap,
        "last_run_at": c.last_run_at.isoformat() if c.last_run_at else None,
    }
    if contact_count is not None:
        data["contact_count"] = contact_count
    return data


def _serialize_contact(c: Contact) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "campaign_id": str(c.campaign_id) if c.campaign_id else None,
        "name": f"{c.first_name or ''} {c.last_name or ''}".strip(),
        "title": c.title,
        "company": c.company,
        "linkedin_url": c.linkedin_url,
        "seniority": c.seniority,
        "department": c.department,
        "relevance_score": c.relevance_score,
        "why_relevant": c.relevance_reasoning,
        "outreach_status": c.outreach_status,
        "outreach_message": c.outreach_message,
    }


@mcp.tool()
async def get_credit_balance() -> dict[str, Any]:
    """Check the user's remaining Sparrow credits and what each action costs."""
    token = _require_scope("profile:read")
    async with AsyncSessionLocal() as db:
        balance = await credits.get_balance(db, _user_id(token))
    return {
        "balance": balance,
        "costs": {
            "contact_discovered": settings.credits_per_contact,
            "outreach_draft": settings.credits_per_draft,
        },
        "top_up_url": _top_up_url(),
    }


@mcp.tool()
async def list_campaigns() -> dict[str, Any]:
    """List the user's outreach campaigns."""
    token = _require_scope("campaigns:read")
    async with AsyncSessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(Campaign)
                    .where(Campaign.user_id == _user_id(token))
                    .order_by(Campaign.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return {"campaigns": [_serialize_campaign(c) for c in rows]}


@mcp.tool()
async def get_campaign(campaign_id: str) -> dict[str, Any]:
    """Get one campaign, including how many contacts it has found."""
    token = _require_scope("campaigns:read")
    async with AsyncSessionLocal() as db:
        campaign = await _load_campaign(db, campaign_id, _user_id(token))
        count = len(
            (
                await db.execute(select(Contact.id).where(Contact.campaign_id == campaign.id))
            )
            .scalars()
            .all()
        )
        return _serialize_campaign(campaign, count)


@mcp.tool()
async def create_campaign(
    name: str,
    campaign_type: str,
    objective: str,
    target_titles: list[str],
    target_companies: list[str] | None = None,
    target_industries: list[str] | None = None,
    target_locations: list[str] | None = None,
) -> dict[str, Any]:
    """
    Create an outreach campaign.

    campaign_type must be one of: business_development, job_search, fundraising,
    recruiting, custom. It decides who is considered a good target — business
    development ranks VPs and Directors highest, job_search ranks IC peers highest.

    objective is free text describing what the user wants out of this campaign, and
    is used verbatim when drafting messages, so make it specific.

    Provide target_companies, or target_industries so Sparrow can discover companies.
    """
    token = _require_scope("campaigns:run")

    if campaign_type not in CAMPAIGN_TYPES:
        raise ToolError(f"campaign_type must be one of: {', '.join(CAMPAIGN_TYPES)}")
    if not target_titles:
        raise ToolError("target_titles is required — Sparrow needs roles to search for")
    if not target_companies and not target_industries:
        raise ToolError(
            "Provide target_companies, or target_industries so Sparrow can find companies"
        )

    async with AsyncSessionLocal() as db:
        campaign = Campaign(
            user_id=_user_id(token),
            name=name,
            campaign_type=campaign_type,
            objective=objective,
            target_titles=target_titles,
            target_companies=target_companies or [],
            target_industries=target_industries or [],
            target_locations=target_locations or [],
            status="active",
        )
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
        return _serialize_campaign(campaign)


@mcp.tool()
async def run_campaign(campaign_id: str, max_contacts: int = 10) -> dict[str, Any]:
    """
    Run a campaign: find people matching it and draft a message to each.

    This spends credits — roughly (credits_per_contact + credits_per_draft) per
    person found. Runs synchronously and returns what it found. Cap max_contacts to
    control spend; it stops early if the balance runs out.
    """
    token = _require_scope("campaigns:run")
    user_id = _user_id(token)

    if max_contacts < 1 or max_contacts > 50:
        raise ToolError("max_contacts must be between 1 and 50")

    async with AsyncSessionLocal() as db:
        campaign = await _load_campaign(db, campaign_id, user_id)
        balance = await credits.get_balance(db, user_id)
        campaign_uuid = campaign.id

    per_contact = settings.credits_per_contact + settings.credits_per_draft
    if balance < per_contact:
        raise ToolError(
            f"Not enough credits: {balance} left, need at least {per_contact}. "
            f"Top up at {_top_up_url()}"
        )

    run_id = await pre_create_run(user_id, campaign_uuid, "mcp")
    result = await run_outreach(
        user_id, campaign_uuid, "mcp", run_id=run_id, max_contacts=max_contacts
    )

    async with AsyncSessionLocal() as db:
        new_contacts = (
            (
                await db.execute(
                    select(Contact)
                    .where(Contact.campaign_id == campaign_uuid)
                    .order_by(Contact.discovered_at.desc())
                    .limit(result.get("contacts_found", 0) or 0)
                )
            )
            .scalars()
            .all()
        )
        remaining = await credits.get_balance(db, user_id)

    return {
        "summary": result.get("summary"),
        "contacts_found": result.get("contacts_found", 0),
        "drafts_written": result.get("drafts_written", 0),
        "credits_spent": result.get("credits_spent", 0),
        "credits_remaining": remaining,
        "contacts": [_serialize_contact(c) for c in new_contacts],
    }


@mcp.tool()
async def search_contacts(
    campaign_id: str | None = None,
    company: str | None = None,
    outreach_status: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Search the contacts Sparrow has already found. Free — reads stored data."""
    token = _require_scope("contacts:read")

    async with AsyncSessionLocal() as db:
        query = (
            select(Contact)
            .where(Contact.user_id == _user_id(token))
            .order_by(Contact.relevance_score.desc(), Contact.discovered_at.desc())
            .limit(min(max(limit, 1), 100))
        )
        if campaign_id:
            query = query.where(Contact.campaign_id == uuid.UUID(campaign_id))
        if company:
            query = query.where(Contact.company.ilike(f"%{company}%"))
        if outreach_status:
            query = query.where(Contact.outreach_status == outreach_status)

        rows = (await db.execute(query)).scalars().all()
        return {"contacts": [_serialize_contact(c) for c in rows], "count": len(rows)}


@mcp.tool()
async def draft_outreach(contact_id: str, extra_context: str | None = None) -> dict[str, Any]:
    """
    Draft (or redraft) an outreach message for one contact.

    Spends credits. `extra_context` is optional guidance to fold into this specific
    message — a shared connection, a recent announcement, a reason for reaching out now.
    """
    import anthropic

    token = _require_scope("contacts:write")
    user_id = _user_id(token)

    async with AsyncSessionLocal() as db:
        contact = (
            await db.execute(
                select(Contact).where(
                    Contact.id == uuid.UUID(contact_id), Contact.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if not contact:
            raise ToolError("Contact not found")

        if not await credits.has_credits(db, user_id, settings.credits_per_draft):
            raise ToolError(
                f"Not enough credits to draft a message. Top up at {_top_up_url()}"
            )

        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
        campaign = await drafting.load_campaign_for_contact(db, contact, user_id)
        profile = targeting.get_profile(campaign.campaign_type if campaign else None)
        objective = (
            (campaign.objective or campaign.name)
            if campaign
            else "Start a genuine professional conversation with this person."
        )
        if extra_context:
            objective = f"{objective}\n\nAdditional context for this message: {extra_context}"

        sender = await drafting.build_sender_context(db, user)
        prompt = drafting.build_draft_prompt(sender, contact, profile, objective)

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            model="claude-sonnet-5",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        message = next((b.text for b in resp.content if b.type == "text"), "").strip()
        if not message:
            raise ToolError("Draft generation returned no text")

        contact.outreach_message = message
        if contact.outreach_status == "discovered":
            contact.outreach_status = "message_drafted"

        await credits.spend(
            db,
            user_id,
            settings.credits_per_draft,
            "outreach_draft",
            campaign_id=contact.campaign_id,
        )
        await db.commit()
        await db.refresh(contact)
        remaining = await credits.get_balance(db, user_id)

    return {"contact": _serialize_contact(contact), "credits_remaining": remaining}


@mcp.tool()
async def update_contact_status(
    contact_id: str, outreach_status: str, notes: str | None = None
) -> dict[str, Any]:
    """
    Update where a contact is in the pipeline. Free.

    outreach_status: discovered, message_drafted, sent, replied, meeting_scheduled.
    """
    token = _require_scope("contacts:write")
    valid = {"discovered", "message_drafted", "sent", "replied", "meeting_scheduled"}
    if outreach_status not in valid:
        raise ToolError(f"outreach_status must be one of: {', '.join(sorted(valid))}")

    async with AsyncSessionLocal() as db:
        contact = (
            await db.execute(
                select(Contact).where(
                    Contact.id == uuid.UUID(contact_id), Contact.user_id == _user_id(token)
                )
            )
        ).scalar_one_or_none()
        if not contact:
            raise ToolError("Contact not found")

        contact.outreach_status = outreach_status
        if notes is not None:
            contact.notes = notes
        await db.commit()
        await db.refresh(contact)
        return _serialize_contact(contact)


async def _load_campaign(db, campaign_id: str, user_id: uuid.UUID) -> Campaign:
    try:
        parsed = uuid.UUID(campaign_id)
    except ValueError:
        raise ToolError(f"Not a valid campaign id: {campaign_id}")

    campaign = (
        await db.execute(
            select(Campaign).where(Campaign.id == parsed, Campaign.user_id == user_id)
        )
    ).scalar_one_or_none()
    if not campaign:
        raise ToolError("Campaign not found")
    return campaign
