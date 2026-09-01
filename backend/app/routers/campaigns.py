import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.agent_run import AgentRun
from app.models.campaign import CAMPAIGN_STATUSES, CAMPAIGN_TYPES, Campaign
from app.models.contact import Contact
from app.models.user import User
from app.services import credits, targeting
from app.services.agent_runner import pre_create_run, run_outreach

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

# Per-user rate limit for manual runs: 10 per hour.
# NOTE: in-process only. If this app is ever scaled past one instance, move to
# a Postgres-backed counter — see the MCP workstream notes.
_run_rate_store: dict[str, list[datetime]] = defaultdict(list)
_RATE_WINDOW = timedelta(hours=1)
_RATE_MAX = 10


def _enforce_run_rate_limit(user_id: uuid.UUID) -> None:
    key = str(user_id)
    now = datetime.now(timezone.utc)
    cutoff = now - _RATE_WINDOW
    attempts = [t for t in _run_rate_store[key] if t > cutoff]
    if len(attempts) >= _RATE_MAX:
        raise HTTPException(
            status_code=429, detail="Rate limit reached — maximum 10 campaign runs per hour"
        )
    attempts.append(now)
    _run_rate_store[key] = attempts


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    campaign_type: str = "business_development"
    objective: str | None = None
    target_titles: list[str] = []
    target_companies: list[str] = []
    target_industries: list[str] = []
    target_locations: list[str] = []
    excluded_companies: list[str] = []
    company_stages: list[str] = []
    discover_beyond_list: bool = False
    status: str = "draft"
    autopilot_enabled: bool = False
    autopilot_cadence_days: int = Field(default=3, ge=1, le=30)
    weekly_credit_cap: int = Field(default=100, ge=0, le=100_000)


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    campaign_type: str | None = None
    objective: str | None = None
    target_titles: list[str] | None = None
    target_companies: list[str] | None = None
    target_industries: list[str] | None = None
    target_locations: list[str] | None = None
    excluded_companies: list[str] | None = None
    company_stages: list[str] | None = None
    discover_beyond_list: bool | None = None
    status: str | None = None
    autopilot_enabled: bool | None = None
    autopilot_cadence_days: int | None = Field(default=None, ge=1, le=30)
    weekly_credit_cap: int | None = Field(default=None, ge=0, le=100_000)


class RunRequest(BaseModel):
    company: str | None = None
    max_contacts: int | None = Field(default=None, ge=1, le=200)


def _validate_enums(campaign_type: str | None, status: str | None) -> None:
    if campaign_type is not None and campaign_type not in CAMPAIGN_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"campaign_type must be one of: {', '.join(CAMPAIGN_TYPES)}",
        )
    if status is not None and status not in CAMPAIGN_STATUSES:
        raise HTTPException(
            status_code=422, detail=f"status must be one of: {', '.join(CAMPAIGN_STATUSES)}"
        )


def _serialize(campaign: Campaign, contact_count: int = 0, spent_this_week: int = 0) -> dict:
    return {
        "id": str(campaign.id),
        "name": campaign.name,
        "campaign_type": campaign.campaign_type,
        "objective": campaign.objective,
        "target_titles": campaign.target_titles or [],
        "target_companies": campaign.target_companies or [],
        "target_industries": campaign.target_industries or [],
        "target_locations": campaign.target_locations or [],
        "excluded_companies": campaign.excluded_companies or [],
        "company_stages": campaign.company_stages or [],
        "discover_beyond_list": campaign.discover_beyond_list,
        "status": campaign.status,
        "autopilot_enabled": campaign.autopilot_enabled,
        "autopilot_cadence_days": campaign.autopilot_cadence_days,
        "weekly_credit_cap": campaign.weekly_credit_cap,
        "contact_count": contact_count,
        "credits_spent_this_week": spent_this_week,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "last_run_at": campaign.last_run_at.isoformat() if campaign.last_run_at else None,
    }


async def _get_owned(db: AsyncSession, campaign_id: uuid.UUID, user_id: uuid.UUID) -> Campaign:
    campaign = (
        await db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user_id)
        )
    ).scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.get("/types")
async def list_campaign_types():
    """Metadata for the campaign creation wizard."""
    return [
        {
            "key": p.key,
            "label": p.label,
            "description": p.description,
            "example_titles": list(p.query_expansions),
        }
        for p in targeting.PROFILES.values()
    ]


@router.get("")
async def list_campaigns(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaigns = (
        (
            await db.execute(
                select(Campaign)
                .where(Campaign.user_id == current_user.id)
                .order_by(desc(Campaign.created_at))
            )
        )
        .scalars()
        .all()
    )

    counts_result = await db.execute(
        select(Contact.campaign_id, func.count(Contact.id))
        .where(Contact.user_id == current_user.id)
        .group_by(Contact.campaign_id)
    )
    counts = {row[0]: row[1] for row in counts_result}

    return [_serialize(c, counts.get(c.id, 0)) for c in campaigns]


@router.post("", status_code=201)
async def create_campaign(
    body: CampaignCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_enums(body.campaign_type, body.status)

    campaign = Campaign(user_id=current_user.id, **body.model_dump())
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return _serialize(campaign)


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await _get_owned(db, campaign_id, current_user.id)
    count = await db.scalar(
        select(func.count(Contact.id)).where(Contact.campaign_id == campaign.id)
    )
    spent = await credits.weekly_spend(db, campaign.id)
    return _serialize(campaign, count or 0, spent)


@router.patch("/{campaign_id}")
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await _get_owned(db, campaign_id, current_user.id)
    _validate_enums(body.campaign_type, body.status)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(campaign, field, value)

    await db.commit()
    await db.refresh(campaign)
    return _serialize(campaign)


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await _get_owned(db, campaign_id, current_user.id)
    # Contacts survive with campaign_id set to NULL (ON DELETE SET NULL) — a
    # user deleting a campaign should not silently lose the people they found.
    await db.delete(campaign)
    await db.commit()


@router.post("/{campaign_id}/run")
async def run_campaign(
    campaign_id: uuid.UUID,
    body: RunRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await _get_owned(db, campaign_id, current_user.id)
    _enforce_run_rate_limit(current_user.id)

    balance = await credits.get_balance(db, current_user.id)
    if balance < settings.credits_per_contact:
        raise HTTPException(
            status_code=402,
            detail="Out of credits — top up to run this campaign",
        )

    run_id = await pre_create_run(current_user.id, campaign.id, "manual")
    background_tasks.add_task(
        run_outreach,
        current_user.id,
        campaign.id,
        "manual",
        run_id=run_id,
        company=body.company,
        max_contacts=body.max_contacts,
    )

    campaign.last_run_at = datetime.now(timezone.utc)
    await db.commit()

    return {"ok": True, "run_id": str(run_id), "balance": balance}


@router.get("/{campaign_id}/contacts")
async def list_campaign_contacts(
    campaign_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned(db, campaign_id, current_user.id)
    contacts = (
        (
            await db.execute(
                select(Contact)
                .where(Contact.campaign_id == campaign_id)
                .order_by(desc(Contact.relevance_score), desc(Contact.discovered_at))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(c.id),
            "first_name": c.first_name,
            "last_name": c.last_name,
            "title": c.title,
            "company": c.company,
            "linkedin_url": c.linkedin_url,
            "seniority": c.seniority,
            "department": c.department,
            "relevance_score": c.relevance_score,
            "relevance_reasoning": c.relevance_reasoning,
            "outreach_status": c.outreach_status,
            "outreach_message": c.outreach_message,
            "discovered_at": c.discovered_at.isoformat() if c.discovered_at else None,
        }
        for c in contacts
    ]


@router.get("/{campaign_id}/runs")
async def list_campaign_runs(
    campaign_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned(db, campaign_id, current_user.id)
    runs = (
        (
            await db.execute(
                select(AgentRun)
                .where(AgentRun.campaign_id == campaign_id)
                .order_by(desc(AgentRun.started_at))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(r.id),
            "trigger": r.trigger,
            "status": r.status,
            "contacts_found": r.contacts_found,
            "drafts_written": r.drafts_written,
            "credits_spent": r.credits_spent,
            "current_step": r.current_step,
            "output_summary": r.output_summary,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]
