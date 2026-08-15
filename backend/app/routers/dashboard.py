from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.agent_run import AgentRun
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.resume import Resume
from app.models.user import User, UserPreferences
from app.services import credits

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    week_start = datetime.now(timezone.utc) - timedelta(days=7)

    contacts_count = await db.scalar(
        select(func.count(Contact.id)).where(Contact.user_id == current_user.id)
    )
    drafted_count = await db.scalar(
        select(func.count(Contact.id)).where(
            Contact.user_id == current_user.id,
            Contact.outreach_status == "message_drafted",
        )
    )
    in_flight_count = await db.scalar(
        select(func.count(Contact.id)).where(
            Contact.user_id == current_user.id,
            Contact.outreach_status.in_(("sent", "replied", "meeting_scheduled")),
        )
    )
    campaign_count = await db.scalar(
        select(func.count(Campaign.id)).where(Campaign.user_id == current_user.id)
    )
    active_campaign_count = await db.scalar(
        select(func.count(Campaign.id)).where(
            Campaign.user_id == current_user.id, Campaign.status == "active"
        )
    )

    balance = await credits.get_balance(db, current_user.id)

    spent_this_week = abs(
        int(
            await db.scalar(
                select(func.coalesce(func.sum(AgentRun.credits_spent), 0)).where(
                    AgentRun.user_id == current_user.id, AgentRun.started_at >= week_start
                )
            )
            or 0
        )
    )

    # Onboarding completeness — drives the "start here" checklist.
    prefs = (
        await db.execute(
            select(UserPreferences).where(UserPreferences.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    resume_uploaded = (
        await db.execute(select(Resume.id).where(Resume.user_id == current_user.id).limit(1))
    ).scalar_one_or_none() is not None
    first_run_completed = (
        await db.execute(
            select(AgentRun.id)
            .where(AgentRun.user_id == current_user.id, AgentRun.status == "completed")
            .limit(1)
        )
    ).scalar_one_or_none() is not None

    return {
        "contacts_count": contacts_count or 0,
        "drafted_count": drafted_count or 0,
        "in_flight_count": in_flight_count or 0,
        "campaign_count": campaign_count or 0,
        "active_campaign_count": active_campaign_count or 0,
        "credits": {
            "balance": balance,
            "spent_this_week": spent_this_week,
            "low_balance": balance < app_settings.low_balance_threshold,
        },
        "setup": {
            "profile_completed": bool(prefs and (prefs.headline or prefs.value_prop)),
            "resume_uploaded": resume_uploaded,
            "campaign_created": (campaign_count or 0) > 0,
            "first_run_completed": first_run_completed,
        },
    }


@router.get("/activity")
async def get_activity(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    runs = (
        (
            await db.execute(
                select(AgentRun)
                .where(AgentRun.user_id == current_user.id, AgentRun.status == "completed")
                .order_by(desc(AgentRun.started_at))
                .limit(10)
            )
        )
        .scalars()
        .all()
    )

    return [
        {
            "id": str(r.id),
            "campaign_id": str(r.campaign_id) if r.campaign_id else None,
            "trigger": r.trigger,
            "contacts_found": r.contacts_found,
            "drafts_written": r.drafts_written,
            "credits_spent": r.credits_spent,
            "summary": r.output_summary,
            "timestamp": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]
