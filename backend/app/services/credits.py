"""
Prepaid credit accounting.

Balance is always SUM(credit_ledger.delta) for the user — there is no cached
counter to drift. Callers spend *after* the unit of work succeeds, so a failed
Exa call or a failed draft is never billed.

Every function here flushes but does not commit: the caller owns the transaction
boundary, matching how the agents batch their writes.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.credits import CreditLedgerEntry

logger = logging.getLogger(__name__)


class InsufficientCredits(Exception):
    """Raised when a spend would take the balance below zero."""

    def __init__(self, required: int, balance: int):
        self.required = required
        self.balance = balance
        super().__init__(f"Insufficient credits: need {required}, have {balance}")


async def get_balance(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(CreditLedgerEntry.delta), 0)).where(
            CreditLedgerEntry.user_id == user_id
        )
    )
    return int(result.scalar() or 0)


async def has_credits(db: AsyncSession, user_id: uuid.UUID, cost: int) -> bool:
    return await get_balance(db, user_id) >= cost


async def spend(
    db: AsyncSession,
    user_id: uuid.UUID,
    cost: int,
    reason: str,
    campaign_id: uuid.UUID | None = None,
    agent_run_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> int:
    """Debit `cost` credits. Returns the new balance. Raises InsufficientCredits."""
    if cost <= 0:
        return await get_balance(db, user_id)

    balance = await get_balance(db, user_id)
    if balance < cost:
        raise InsufficientCredits(cost, balance)

    db.add(
        CreditLedgerEntry(
            user_id=user_id,
            delta=-cost,
            reason=reason,
            campaign_id=campaign_id,
            agent_run_id=agent_run_id,
            entry_metadata=metadata,
        )
    )
    await db.flush()
    return balance - cost


async def grant(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
    reason: str,
    stripe_payment_intent_id: str | None = None,
    metadata: dict | None = None,
) -> int:
    """
    Credit `amount` to a user. Returns the new balance.

    When `stripe_payment_intent_id` is given the grant is idempotent: a redelivered
    webhook hits the unique constraint, we roll back to the savepoint, and the
    balance is unchanged. Checking-then-inserting instead would still race two
    concurrent deliveries, so the constraint is the real guard.
    """
    if amount <= 0:
        return await get_balance(db, user_id)

    entry = CreditLedgerEntry(
        user_id=user_id,
        delta=amount,
        reason=reason,
        stripe_payment_intent_id=stripe_payment_intent_id,
        entry_metadata=metadata,
    )

    if stripe_payment_intent_id:
        try:
            async with db.begin_nested():
                db.add(entry)
                await db.flush()
        except IntegrityError:
            logger.info(
                "Duplicate credit grant ignored for payment_intent=%s", stripe_payment_intent_id
            )
            return await get_balance(db, user_id)
    else:
        db.add(entry)
        await db.flush()

    return await get_balance(db, user_id)


async def campaign_spend_since(
    db: AsyncSession, campaign_id: uuid.UUID, since: datetime
) -> int:
    """Credits spent on a campaign since `since`, as a positive number."""
    result = await db.execute(
        select(func.coalesce(func.sum(CreditLedgerEntry.delta), 0)).where(
            CreditLedgerEntry.campaign_id == campaign_id,
            CreditLedgerEntry.delta < 0,
            CreditLedgerEntry.created_at >= since,
        )
    )
    return abs(int(result.scalar() or 0))


async def weekly_spend(db: AsyncSession, campaign_id: uuid.UUID) -> int:
    """Credits spent on a campaign in the trailing 7 days (the autopilot cap window)."""
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    return await campaign_spend_since(db, campaign_id, week_ago)


async def recent_entries(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 50
) -> list[CreditLedgerEntry]:
    result = await db.execute(
        select(CreditLedgerEntry)
        .where(CreditLedgerEntry.user_id == user_id)
        .order_by(CreditLedgerEntry.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def grant_signup_credits(db: AsyncSession, user_id: uuid.UUID) -> int:
    return await grant(db, user_id, settings.signup_credit_grant, "signup_grant")
