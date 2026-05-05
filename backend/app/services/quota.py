import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.subscription import MonthlyUsage, Subscription


async def get_plan(db: AsyncSession, user_id: uuid.UUID) -> str:
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    sub = result.scalar_one_or_none()
    # Only grant pro if both plan="pro" AND status="active" — guards against
    # canceled/past_due rows where plan hasn't been reset yet.
    return "pro" if (sub and sub.plan == "pro" and sub.status == "active") else "free"


async def _get_or_create_usage(db: AsyncSession, user_id: uuid.UUID) -> MonthlyUsage:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    result = await db.execute(
        select(MonthlyUsage).where(MonthlyUsage.user_id == user_id, MonthlyUsage.month == month)
    )
    usage = result.scalar_one_or_none()
    if not usage:
        usage = MonthlyUsage(user_id=user_id, month=month)
        db.add(usage)
        await db.flush()
    return usage


async def can_surface_job(db: AsyncSession, user_id: uuid.UUID) -> bool:
    plan = await get_plan(db, user_id)
    if plan == "pro":
        return True
    usage = await _get_or_create_usage(db, user_id)
    return usage.jobs_surfaced < settings.free_jobs_per_month


async def increment_jobs_surfaced(db: AsyncSession, user_id: uuid.UUID, count: int = 1):
    usage = await _get_or_create_usage(db, user_id)
    usage.jobs_surfaced += count
    await db.flush()  # flush only — caller is responsible for commit


async def can_surface_contact(db: AsyncSession, user_id: uuid.UUID) -> bool:
    plan = await get_plan(db, user_id)
    if plan == "pro":
        return True
    usage = await _get_or_create_usage(db, user_id)
    return usage.contacts_surfaced < settings.free_contacts_per_month


async def increment_contacts_surfaced(db: AsyncSession, user_id: uuid.UUID, count: int = 1):
    usage = await _get_or_create_usage(db, user_id)
    usage.contacts_surfaced += count
    await db.flush()  # flush only — caller is responsible for commit


async def can_run_agent(db: AsyncSession, user_id: uuid.UUID, agent_type: str) -> bool:
    plan = await get_plan(db, user_id)
    if plan == "pro":
        return True
    from app.models.agent_run import AgentRun
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(AgentRun.id)).where(
            AgentRun.user_id == user_id,
            AgentRun.agent_type == agent_type,
            AgentRun.started_at >= month_start,
        )
    )
    count = result.scalar() or 0
    return count < settings.free_agent_runs_per_month


async def can_generate_application(db: AsyncSession, user_id: uuid.UUID) -> bool:
    plan = await get_plan(db, user_id)
    if plan == "pro":
        return True
    from app.models.application import Application
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(Application.id)).where(
            Application.user_id == user_id,
            Application.created_at >= month_start,
        )
    )
    count = result.scalar() or 0
    return count < settings.free_applications_per_month


async def get_agent_run_count(db: AsyncSession, user_id: uuid.UUID, agent_type: str) -> int:
    from app.models.agent_run import AgentRun
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(AgentRun.id)).where(
            AgentRun.user_id == user_id,
            AgentRun.agent_type == agent_type,
            AgentRun.started_at >= month_start,
        )
    )
    return result.scalar() or 0
