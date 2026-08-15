import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.campaign import Campaign
from app.models.user import User
from app.services import credits

logger = logging.getLogger(__name__)

# NOTE: in-memory jobstore. Running more than one instance of this app will
# double-fire every scheduled campaign — and under prepaid credits that means
# charging users twice. Move to a persistent jobstore or a scheduler lock before
# scaling out.
scheduler = AsyncIOScheduler()


async def run_autopilot_campaigns():
    """
    Fire outreach runs for campaigns whose autopilot is due.

    Three gates, in order: the campaign is active and due, the user has credits,
    and the campaign is under its weekly spend cap. The cap applies only here —
    manual and MCP runs are user-initiated and uncapped.
    """
    from app.services.agent_runner import pre_create_run, run_outreach

    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Campaign, User)
            .join(User, User.id == Campaign.user_id)
            .where(
                User.is_active.is_(True),
                Campaign.status == "active",
                Campaign.autopilot_enabled.is_(True),
            )
        )
        rows = result.all()

    due: list[tuple[Campaign, User]] = []
    for campaign, user in rows:
        if campaign.last_run_at:
            next_due = campaign.last_run_at.replace(tzinfo=timezone.utc) + timedelta(
                days=campaign.autopilot_cadence_days
            )
            if now < next_due:
                continue
        due.append((campaign, user))

    logger.info("Autopilot: %d campaigns due", len(due))

    for campaign, user in due:
        try:
            async with AsyncSessionLocal() as db:
                balance = await credits.get_balance(db, user.id)
                if balance < settings.credits_per_contact:
                    logger.info(
                        "Autopilot skipped campaign %s — user %s has no credits",
                        campaign.id,
                        user.id,
                    )
                    continue

                spent = await credits.weekly_spend(db, campaign.id)
                if spent >= campaign.weekly_credit_cap:
                    logger.info(
                        "Autopilot skipped campaign %s — weekly cap reached (%d/%d)",
                        campaign.id,
                        spent,
                        campaign.weekly_credit_cap,
                    )
                    continue

                remaining_cap = campaign.weekly_credit_cap - spent

            # Bound the run so it cannot blow through the cap in a single pass.
            max_contacts = max(1, remaining_cap // (settings.credits_per_contact + settings.credits_per_draft))

            run_id = await pre_create_run(user.id, campaign.id, "scheduled")
            await run_outreach(
                user.id, campaign.id, "scheduled", run_id=run_id, max_contacts=max_contacts
            )

            async with AsyncSessionLocal() as db:
                fresh = await db.get(Campaign, campaign.id)
                if fresh:
                    fresh.last_run_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            logger.exception("Autopilot run failed for campaign %s", campaign.id)


async def send_low_balance_alerts():
    """One nudge per user when the balance crosses below the threshold."""
    from app.models.user import UserPreferences
    from app.services.email_service import low_balance_email, send_email

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User, UserPreferences)
            .join(UserPreferences, User.id == UserPreferences.user_id)
            .where(
                User.is_active.is_(True),
                User.is_verified.is_(True),
                UserPreferences.email_low_balance_enabled.is_(True),
            )
        )
        rows = result.all()

        for user, _prefs in rows:
            try:
                balance = await credits.get_balance(db, user.id)
                if balance >= settings.low_balance_threshold or balance <= 0:
                    continue
                # Only alert users with an active autopilot campaign — everyone
                # else will discover the balance when they next click Run.
                has_autopilot = await db.scalar(
                    select(func.count(Campaign.id)).where(
                        Campaign.user_id == user.id,
                        Campaign.autopilot_enabled.is_(True),
                        Campaign.status == "active",
                    )
                )
                if not has_autopilot:
                    continue

                await send_email(
                    user.email,
                    "Your Sparrow credits are running low",
                    low_balance_email(balance, settings.frontend_url),
                )
            except Exception:
                logger.exception("Low balance alert failed for user %s", user.id)


async def send_activation_emails():
    """
    Two checks per hour:
    - Signed up > 1h ago, verified, no campaign → "Finish setup" (once)
    - Has a campaign but no contacts → "Your first outreach is ready" (once)
    """
    from app.models.agent_run import AgentRun
    from app.models.contact import Contact
    from app.services.email_service import (
        finish_setup_email,
        first_outreach_ready_email,
        send_email,
    )

    cutoff_1h = datetime.now(timezone.utc) - timedelta(hours=1)
    cutoff_2h = datetime.now(timezone.utc) - timedelta(hours=2)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.is_active.is_(True), User.is_verified.is_(True))
        )
        users = result.scalars().all()

    for user in users:
        try:
            async with AsyncSessionLocal() as db:
                has_campaign = (
                    await db.execute(
                        select(Campaign.id).where(Campaign.user_id == user.id).limit(1)
                    )
                ).scalar_one_or_none() is not None

                created_at = user.created_at.replace(tzinfo=timezone.utc)

                if (
                    not has_campaign
                    and not user.finish_setup_email_sent
                    and created_at < cutoff_1h
                ):
                    sent = await send_email(
                        user.email,
                        "Finish setting up Sparrow",
                        finish_setup_email(settings.frontend_url),
                    )
                    if sent:
                        user.finish_setup_email_sent = True
                        db.add(user)
                        await db.commit()
                    continue

                if (
                    has_campaign
                    and not user.first_outreach_email_sent
                    and created_at < cutoff_2h
                ):
                    has_contacts = (
                        await db.execute(
                            select(Contact.id).where(Contact.user_id == user.id).limit(1)
                        )
                    ).scalar_one_or_none() is not None
                    has_run = (
                        await db.execute(
                            select(AgentRun.id).where(AgentRun.user_id == user.id).limit(1)
                        )
                    ).scalar_one_or_none() is not None

                    if not has_contacts and not has_run:
                        sent = await send_email(
                            user.email,
                            "Your first outreach is ready",
                            first_outreach_ready_email(settings.frontend_url),
                        )
                        if sent:
                            user.first_outreach_email_sent = True
                            db.add(user)
                            await db.commit()
        except Exception:
            logger.exception("Activation email check failed for user %s", user.id)


async def send_weekly_summaries():
    from app.models.agent_run import AgentRun
    from app.models.user import UserPreferences
    from app.services.email_service import send_email, weekly_summary_email

    since = datetime.now(timezone.utc) - timedelta(days=7)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User, UserPreferences)
            .join(UserPreferences, User.id == UserPreferences.user_id)
            .where(User.is_active.is_(True), UserPreferences.email_digest_enabled.is_(True))
        )
        rows = result.all()

    for user, _prefs in rows:
        try:
            async with AsyncSessionLocal() as db:
                row = (
                    await db.execute(
                        select(
                            func.count(AgentRun.id).label("total_runs"),
                            func.coalesce(func.sum(AgentRun.contacts_found), 0).label("contacts"),
                            func.coalesce(func.sum(AgentRun.drafts_written), 0).label("drafts"),
                            func.coalesce(func.sum(AgentRun.credits_spent), 0).label("credits"),
                        ).where(
                            AgentRun.user_id == user.id,
                            AgentRun.status == "completed",
                            AgentRun.started_at >= since,
                        )
                    )
                ).one()
                balance = await credits.get_balance(db, user.id)

            if not row.total_runs:
                continue

            await send_email(
                user.email,
                "Your Sparrow week",
                weekly_summary_email(
                    name=user.full_name,
                    contacts_found=int(row.contacts or 0),
                    drafts_written=int(row.drafts or 0),
                    credits_spent=int(row.credits or 0),
                    balance=balance,
                    agent_runs=row.total_runs,
                    frontend_url=settings.frontend_url,
                ),
            )
        except Exception:
            logger.exception("Weekly summary failed for user %s", user.id)


def register_jobs():
    # Hourly tick; per-campaign cadence decides what actually runs.
    scheduler.add_job(
        run_autopilot_campaigns,
        IntervalTrigger(hours=1),
        id="autopilot_campaigns",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.add_job(
        send_low_balance_alerts,
        CronTrigger(hour=15, minute=0, timezone="UTC"),
        id="low_balance_alerts",
        replace_existing=True,
        misfire_grace_time=3600,
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
