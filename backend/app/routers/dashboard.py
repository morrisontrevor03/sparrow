from fastapi import APIRouter, Depends
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.agent_run import AgentRun
from app.models.application import Application
from app.models.contact import Contact
from app.models.job import Job
from app.models.subscription import MonthlyUsage, Subscription
from app.models.user import User, UserPreferences
from app.models.resume import Resume
from app.config import settings as app_settings
from datetime import datetime, timezone

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    jobs_count = await db.scalar(
        select(func.count(Job.id)).where(Job.user_id == current_user.id, Job.is_dismissed == False)
    )
    new_jobs_count = await db.scalar(
        select(func.count(Job.id)).where(Job.user_id == current_user.id, Job.is_new == True, Job.is_dismissed == False)
    )
    applications_count = await db.scalar(
        select(func.count(Application.id)).where(Application.user_id == current_user.id)
    )
    contacts_count = await db.scalar(
        select(func.count(Contact.id)).where(Contact.user_id == current_user.id)
    )

    # Usage this month
    usage_result = await db.execute(
        select(MonthlyUsage).where(
            MonthlyUsage.user_id == current_user.id,
            MonthlyUsage.month == current_month,
        )
    )
    usage = usage_result.scalar_one_or_none()

    # Subscription/plan
    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id)
    )
    sub = sub_result.scalar_one_or_none()
    plan = sub.plan if sub else "free"

    # Setup completeness
    prefs_result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == current_user.id)
    )
    prefs = prefs_result.scalar_one_or_none()
    target_roles_configured = bool(prefs and prefs.target_roles)
    companies_configured = bool(
        prefs and (prefs.target_companies or prefs.work_environment or prefs.company_stages)
    )

    resume_result = await db.execute(
        select(Resume).where(Resume.user_id == current_user.id).limit(1)
    )
    resume_uploaded = resume_result.scalar_one_or_none() is not None

    first_run_result = await db.execute(
        select(AgentRun.id)
        .where(AgentRun.user_id == current_user.id, AgentRun.status == "completed")
        .limit(1)
    )
    first_run_completed = first_run_result.scalar_one_or_none() is not None

    # Agent run counts this month — single GROUP BY instead of 3 separate queries
    run_counts_result = await db.execute(
        select(AgentRun.agent_type, func.count(AgentRun.id).label("cnt"))
        .where(AgentRun.user_id == current_user.id, AgentRun.started_at >= month_start)
        .group_by(AgentRun.agent_type)
    )
    run_counts = {row.agent_type: row.cnt for row in run_counts_result}

    run_limit = None if plan == "pro" else app_settings.free_agent_runs_per_month

    return {
        "jobs_count": jobs_count or 0,
        "new_jobs_count": new_jobs_count or 0,
        "applications_count": applications_count or 0,
        "contacts_count": contacts_count or 0,
        "plan": plan,
        "target_roles_configured": target_roles_configured,
        "resume_uploaded": resume_uploaded,
        "companies_configured": companies_configured,
        "first_run_completed": first_run_completed,
        "usage": {
            "jobs_surfaced": usage.jobs_surfaced if usage else 0,
            "contacts_surfaced": usage.contacts_surfaced if usage else 0,
            "jobs_limit": None if plan == "pro" else app_settings.free_jobs_per_month,
            "contacts_limit": None if plan == "pro" else app_settings.free_contacts_per_month,
            "agent_runs": {
                "job_scout": run_counts.get("job_scout", 0),
                "networking": run_counts.get("networking", 0),
                "application": run_counts.get("application", 0),
            },
            "agent_runs_limit": run_limit,
        },
    }


@router.get("/activity")
async def get_activity(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    runs_result = await db.execute(
        select(AgentRun)
        .where(AgentRun.user_id == current_user.id, AgentRun.status == "completed")
        .order_by(desc(AgentRun.started_at))
        .limit(10)
    )
    runs = runs_result.scalars().all()

    activity = []
    for r in runs:
        if r.agent_type == "job_scout" and r.jobs_found:
            activity.append({
                "type": "jobs_found",
                "count": r.jobs_found,
                "timestamp": r.completed_at.isoformat() if r.completed_at else None,
            })
        elif r.agent_type == "networking" and r.contacts_found:
            activity.append({
                "type": "contacts_found",
                "count": r.contacts_found,
                "timestamp": r.completed_at.isoformat() if r.completed_at else None,
            })
        elif r.agent_type == "application" and r.applications_created:
            activity.append({
                "type": "drafts_created",
                "count": r.applications_created,
                "timestamp": r.completed_at.isoformat() if r.completed_at else None,
            })

    return activity
