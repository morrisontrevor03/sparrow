import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User, UserPreferences

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def run_job_scout_for_all_users():
    from app.agents.job_scout import JobScoutAgent

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User)
            .join(UserPreferences, User.id == UserPreferences.user_id)
            .where(User.is_active == True, UserPreferences.scout_enabled == True)
        )
        users = result.scalars().all()

    for user in users:
        try:
            async with AsyncSessionLocal() as db:
                agent = JobScoutAgent(db, user.id)
                await agent.run(trigger="scheduled")
        except Exception:
            logger.exception("Job scout failed for user %s", user.id)


async def run_networking_for_all_users():
    from app.agents.networking import NetworkingAgent

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User)
            .join(UserPreferences, User.id == UserPreferences.user_id)
            .where(User.is_active == True, UserPreferences.networking_enabled == True)
        )
        users = result.scalars().all()

    for user in users:
        try:
            async with AsyncSessionLocal() as db:
                agent = NetworkingAgent(db, user.id)
                await agent.run(trigger="scheduled")
        except Exception:
            logger.exception("Networking agent failed for user %s", user.id)


async def run_application_agent_for_all_users():
    from app.agents.application import ApplicationAgent

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User)
            .join(UserPreferences, User.id == UserPreferences.user_id)
            .where(User.is_active == True, UserPreferences.application_agent_enabled == True)
        )
        users = result.scalars().all()

    for user in users:
        try:
            async with AsyncSessionLocal() as db:
                agent = ApplicationAgent(db, user.id)
                await agent.run(trigger="scheduled")
        except Exception:
            logger.exception("Application agent failed for user %s", user.id)


async def reset_monthly_usage():
    from sqlalchemy import delete
    from app.models.subscription import MonthlyUsage

    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(MonthlyUsage).where(MonthlyUsage.month != current_month)
        )
        await db.commit()
    logger.info("Monthly usage reset complete")


async def send_activation_emails():
    """
    Two checks per hour:
    - Signed up > 1h ago, verified, no resume → send "Finish setup" (once)
    - Has resume, no contacts/networking runs → send "First outreach ready" (once)
    """
    from app.models.resume import Resume
    from app.models.contact import Contact
    from app.models.agent_run import AgentRun
    from app.services.email_service import send_email, finish_setup_email, first_outreach_ready_email

    cutoff_1h = datetime.now(timezone.utc) - timedelta(hours=1)
    cutoff_2h = datetime.now(timezone.utc) - timedelta(hours=2)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.is_active == True, User.is_verified == True)
        )
        users = result.scalars().all()

    for user in users:
        try:
            async with AsyncSessionLocal() as db:
                resume_result = await db.execute(
                    select(Resume.id).where(Resume.user_id == user.id).limit(1)
                )
                has_resume = resume_result.scalar_one_or_none() is not None

                # Check 1: no resume after 1 hour
                if (
                    not has_resume
                    and not user.finish_setup_email_sent
                    and user.created_at.replace(tzinfo=timezone.utc) < cutoff_1h
                ):
                    html = finish_setup_email(settings.frontend_url)
                    sent = await send_email(user.email, "Finish your ApplyNow setup", html)
                    if sent:
                        user.finish_setup_email_sent = True
                        db.add(user)
                        await db.commit()
                    continue

                # Check 2: has resume but no outreach after 2 hours
                if (
                    has_resume
                    and not user.first_outreach_email_sent
                    and user.created_at.replace(tzinfo=timezone.utc) < cutoff_2h
                ):
                    contacts_result = await db.execute(
                        select(Contact.id).where(Contact.user_id == user.id).limit(1)
                    )
                    has_contacts = contacts_result.scalar_one_or_none() is not None

                    runs_result = await db.execute(
                        select(AgentRun.id).where(
                            AgentRun.user_id == user.id,
                            AgentRun.agent_type == "networking",
                        ).limit(1)
                    )
                    has_networking_run = runs_result.scalar_one_or_none() is not None

                    if not has_contacts and not has_networking_run:
                        html = first_outreach_ready_email(settings.frontend_url)
                        sent = await send_email(user.email, "Your first outreach is ready", html)
                        if sent:
                            user.first_outreach_email_sent = True
                            db.add(user)
                            await db.commit()
        except Exception:
            logger.exception("Activation email check failed for user %s", user.id)


async def send_weekly_summaries():
    from app.models.agent_run import AgentRun
    from app.services.email_service import send_email, weekly_summary_email

    since = datetime.now(timezone.utc) - timedelta(days=7)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.is_active == True))
        users = result.scalars().all()

    for user in users:
        try:
            async with AsyncSessionLocal() as db:
                runs_result = await db.execute(
                    select(
                        func.count(AgentRun.id).label("total_runs"),
                        func.coalesce(func.sum(AgentRun.jobs_found), 0).label("jobs_found"),
                        func.coalesce(func.sum(AgentRun.contacts_found), 0).label("contacts_found"),
                        func.coalesce(func.sum(AgentRun.applications_created), 0).label("applications_created"),
                    ).where(
                        AgentRun.user_id == user.id,
                        AgentRun.status == "completed",
                        AgentRun.started_at >= since,
                    )
                )
                row = runs_result.one()

            total_runs = row.total_runs or 0
            jobs_found = int(row.jobs_found or 0)
            contacts_found = int(row.contacts_found or 0)
            applications_created = int(row.applications_created or 0)

            # Skip users with no activity this week
            if total_runs == 0:
                continue

            html = weekly_summary_email(
                name=user.full_name,
                jobs_found=jobs_found,
                contacts_found=contacts_found,
                applications_created=applications_created,
                agent_runs=total_runs,
                frontend_url=settings.frontend_url,
            )
            await send_email(user.email, "Your ApplyNow weekly summary", html)
        except Exception:
            logger.exception("Weekly summary failed for user %s", user.id)


def register_jobs():
    # Every 30 min: the core promise is being first to a new posting, so a 4-hour
    # cadence directly undercut the product. Interval keeps fresh listings flowing;
    # per-user free-plan quotas still bound how many jobs actually get surfaced.
    scheduler.add_job(
        run_job_scout_for_all_users,
        IntervalTrigger(minutes=30),
        id="job_scout_global",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        run_networking_for_all_users,
        CronTrigger(day_of_week="sun,wed", hour=9, minute=0, timezone="UTC"),
        id="networking_global",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        reset_monthly_usage,
        CronTrigger(day=1, hour=0, minute=0),
        id="reset_monthly_usage",
        replace_existing=True,
    )
    scheduler.add_job(
        send_weekly_summaries,
        CronTrigger(day_of_week="fri", hour=12, minute=0, timezone="UTC"),
        id="weekly_summary",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        send_activation_emails,
        IntervalTrigger(minutes=60),
        id="activation_emails",
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info("APScheduler jobs registered")
