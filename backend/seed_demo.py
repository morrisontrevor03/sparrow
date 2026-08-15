"""
Seed a demo Sparrow account.

Replaces the old job-search seeder (1300 lines of job/application fixtures, all
of which described features that no longer exist). This one produces what a
Sparrow demo actually needs: a user with a profile, two campaigns of different
types so the per-type ranking is visible, contacts at various pipeline stages,
and a credit balance with some history.

    python seed_demo.py            # seed
    python seed_demo.py --reset    # delete the demo user first, then seed
"""

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.agent_run import AgentRun
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.credits import CreditLedgerEntry
from app.models.subscription import BillingAccount
from app.models.user import User, UserPreferences

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEMO_EMAIL = "demo@sparrow.email"
DEMO_PASSWORD = "sparrow-demo-2026"

USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
BD_CAMPAIGN_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
FUND_CAMPAIGN_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")

now = datetime.now(timezone.utc)


BD_CONTACTS = [
    ("Priya", "Raghavan", "VP of Engineering", "Ramp", "vp", "engineering", 0.95,
     "VP/Head of — typically owns the budget for this", "replied"),
    ("Marcus", "Webb", "Head of Platform", "Mercury", "vp", "engineering", 0.95,
     "VP/Head of — typically owns the budget for this", "sent"),
    ("Dani", "Okonjo", "Director of Data Platform", "Brex", "director", "data", 0.90,
     "Director — owns the problem and can sponsor a pilot", "message_drafted"),
    ("Tom", "Lindqvist", "Director of Infrastructure", "Modern Treasury", "director",
     "engineering", 0.90, "Director — owns the problem and can sponsor a pilot", "message_drafted"),
    ("Alicia", "Fuentes", "Engineering Manager, Observability", "Plaid", "manager",
     "engineering", 0.70, "Manager/Lead — close to the pain, can champion internally", "discovered"),
    ("Sam", "Oyelaran", "Staff Engineer, Data Infra", "Ramp", "manager", "data", 0.70,
     "Manager/Lead — close to the pain, can champion internally", "discovered"),
    ("Nina", "Castellanos", "Head of Data", "Column", "vp", "data", 0.95,
     "VP/Head of — typically owns the budget for this", "meeting_scheduled"),
    ("Jonah", "Pierce", "Senior Platform Engineer", "Mercury", "mid", "engineering", 0.55,
     "Individual contributor in a relevant team — useful for context", "discovered"),
]

FUND_CONTACTS = [
    ("Erica", "Vandermeer", "General Partner", "Foundry Group", "investor", "investing", 0.95,
     "GP/MD — writes cheques and leads rounds", "sent"),
    ("Ravi", "Shankaran", "Partner", "Amplify Partners", "investor", "investing", 0.90,
     "Partner — decision-maker on new investments", "replied"),
    ("Beatrice", "Nolan", "Partner", "Uncork Capital", "investor", "investing", 0.90,
     "Partner — decision-maker on new investments", "message_drafted"),
    ("Hugo", "Ferreira", "Principal", "Heavybit", "investor", "investing", 0.80,
     "Principal — sources and champions deals internally", "message_drafted"),
    ("Sana", "Qureshi", "Investor", "Essence VC", "investor", "investing", 0.70,
     "Investor — relevant cheque-writer", "discovered"),
    ("Will", "Tanaka", "Associate", "Amplify Partners", "mid", "investing", 0.55,
     "Associate/Analyst — sources deals; a realistic first touch", "discovered"),
]

DRAFTS = {
    "message_drafted": (
        "Saw Ramp shipped the new spend-controls surface last month — that kind of "
        "release cadence usually means alerting is doing a lot of quiet work. We cut "
        "alert noise about 70% for data platform teams on dbt and Airflow. Worth a "
        "15-minute conversation to see whether that's a real problem for your team?"
    ),
    "sent": (
        "We're building observability tooling for data teams and hit $40k MRR without "
        "a sales hire. Given Foundry's work with infrastructure companies at this "
        "stage, I'd value 20 minutes to hear how you're thinking about the category."
    ),
}


async def build_contacts(
    db: AsyncSession, campaign_id: uuid.UUID, rows: list, offset_days: int
) -> None:
    for i, (first, last, title, company, seniority, dept, score, reason, status) in enumerate(rows):
        db.add(
            Contact(
                user_id=USER_ID,
                campaign_id=campaign_id,
                first_name=first,
                last_name=last,
                title=title,
                company=company,
                linkedin_url=f"https://www.linkedin.com/in/{first.lower()}-{last.lower()}",
                seniority=seniority,
                department=dept,
                relevance_score=score,
                relevance_reasoning=reason,
                outreach_status=status,
                outreach_message=DRAFTS.get(status),
                discovered_at=now - timedelta(days=offset_days, hours=i),
            )
        )


async def seed(db: AsyncSession) -> None:
    db.add(
        User(
            id=USER_ID,
            email=DEMO_EMAIL,
            hashed_password=pwd.hash(DEMO_PASSWORD),
            full_name="Jordan Blake",
            is_active=True,
            is_verified=True,
            created_at=now - timedelta(days=21),
        )
    )
    await db.flush()

    db.add(
        UserPreferences(
            user_id=USER_ID,
            headline="Co-founder at Kestrel — observability for data teams",
            value_prop=(
                "We cut alert noise by roughly 70% for data platform teams running dbt "
                "and Airflow, without another dashboard to babysit."
            ),
            timezone="America/New_York",
        )
    )
    db.add(BillingAccount(user_id=USER_ID))

    db.add(
        Campaign(
            id=BD_CAMPAIGN_ID,
            user_id=USER_ID,
            name="Series B fintech — platform teams",
            campaign_type="business_development",
            objective=(
                "Sell Kestrel's observability tooling to platform and data engineering "
                "teams at Series B fintechs who already run dbt and Airflow"
            ),
            target_titles=["VP of Engineering", "Head of Platform", "Director of Data"],
            target_companies=["Ramp", "Mercury", "Brex", "Modern Treasury", "Plaid", "Column"],
            target_industries=["fintech"],
            target_locations=["New York", "Remote"],
            status="active",
            autopilot_enabled=True,
            autopilot_cadence_days=3,
            weekly_credit_cap=150,
            created_at=now - timedelta(days=18),
            last_run_at=now - timedelta(days=2),
        )
    )
    db.add(
        Campaign(
            id=FUND_CAMPAIGN_ID,
            user_id=USER_ID,
            name="Seed round",
            campaign_type="fundraising",
            objective=(
                "Raise a $3M seed for a developer tools company at $40k MRR, growing "
                "20% month over month"
            ),
            target_titles=["Partner", "General Partner", "Principal"],
            target_companies=["Foundry Group", "Amplify Partners", "Uncork Capital", "Heavybit"],
            target_industries=["venture capital"],
            status="active",
            autopilot_enabled=False,
            weekly_credit_cap=100,
            created_at=now - timedelta(days=9),
            last_run_at=now - timedelta(days=1),
        )
    )
    await db.flush()

    await build_contacts(db, BD_CAMPAIGN_ID, BD_CONTACTS, offset_days=12)
    await build_contacts(db, FUND_CAMPAIGN_ID, FUND_CONTACTS, offset_days=6)

    for campaign_id, contacts_found, drafts, days_ago in (
        (BD_CAMPAIGN_ID, 5, 5, 12),
        (BD_CAMPAIGN_ID, 3, 3, 2),
        (FUND_CAMPAIGN_ID, 6, 6, 1),
    ):
        spent = contacts_found * 1 + drafts * 2
        db.add(
            AgentRun(
                user_id=USER_ID,
                campaign_id=campaign_id,
                agent_type="outreach",
                trigger="scheduled" if campaign_id == BD_CAMPAIGN_ID else "manual",
                status="completed",
                output_summary=f"Found {contacts_found} new contacts, drafted {drafts} messages",
                contacts_found=contacts_found,
                drafts_written=drafts,
                credits_spent=spent,
                started_at=now - timedelta(days=days_ago),
                completed_at=now - timedelta(days=days_ago) + timedelta(minutes=4),
                duration_ms=240_000,
            )
        )

    # Ledger: signup grant, a purchase, then the spend from the runs above.
    db.add(
        CreditLedgerEntry(
            user_id=USER_ID,
            delta=25,
            reason="signup_grant",
            created_at=now - timedelta(days=21),
        )
    )
    db.add(
        CreditLedgerEntry(
            user_id=USER_ID,
            delta=500,
            reason="purchase",
            stripe_payment_intent_id="pi_demo_seed_0001",
            entry_metadata={"pack_id": "starter"},
            created_at=now - timedelta(days=19),
        )
    )
    for campaign_id, contacts_found, drafts, days_ago in (
        (BD_CAMPAIGN_ID, 5, 5, 12),
        (BD_CAMPAIGN_ID, 3, 3, 2),
        (FUND_CAMPAIGN_ID, 6, 6, 1),
    ):
        db.add(
            CreditLedgerEntry(
                user_id=USER_ID,
                delta=-contacts_found,
                reason="contact_discovered",
                campaign_id=campaign_id,
                created_at=now - timedelta(days=days_ago),
            )
        )
        db.add(
            CreditLedgerEntry(
                user_id=USER_ID,
                delta=-drafts * 2,
                reason="outreach_draft",
                campaign_id=campaign_id,
                created_at=now - timedelta(days=days_ago),
            )
        )

    await db.commit()


async def reset(db: AsyncSession) -> None:
    user = (
        await db.execute(select(User).where(User.email == DEMO_EMAIL))
    ).scalar_one_or_none()
    if not user:
        return
    # Everything else cascades from users.
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()
    print("Removed existing demo user")


async def main() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        if "--reset" in sys.argv:
            await reset(db)

        existing = (
            await db.execute(select(User).where(User.email == DEMO_EMAIL))
        ).scalar_one_or_none()
        if existing:
            print(f"Demo user already exists ({DEMO_EMAIL}). Re-run with --reset to rebuild.")
            return

        await seed(db)

    await engine.dispose()
    print(f"Seeded demo account: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print("  2 campaigns (business development + fundraising), 14 contacts, 3 runs")
    print("  Credit balance: 465")


if __name__ == "__main__":
    asyncio.run(main())
