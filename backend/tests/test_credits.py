import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import credits
from app.services.credits import InsufficientCredits


async def test_balance_is_the_sum_of_the_ledger(db: AsyncSession, user: User):
    assert await credits.get_balance(db, user.id) == 100

    await credits.spend(db, user.id, 30, "contact_discovered")
    await db.commit()
    assert await credits.get_balance(db, user.id) == 70

    await credits.grant(db, user.id, 15, "promo_grant")
    await db.commit()
    assert await credits.get_balance(db, user.id) == 85


async def test_spend_beyond_balance_is_refused(db: AsyncSession, user: User):
    with pytest.raises(InsufficientCredits) as exc:
        await credits.spend(db, user.id, 101, "outreach_draft")

    assert exc.value.required == 101
    assert exc.value.balance == 100
    # The failed spend must leave no trace.
    assert await credits.get_balance(db, user.id) == 100


async def test_spend_can_take_balance_to_exactly_zero(db: AsyncSession, user: User):
    await credits.spend(db, user.id, 100, "contact_discovered")
    await db.commit()
    assert await credits.get_balance(db, user.id) == 0
    assert not await credits.has_credits(db, user.id, 1)


async def test_grant_is_idempotent_on_payment_intent(db: AsyncSession, user: User):
    """
    The webhook redelivery guard. Stripe resends `checkout.session.completed`
    freely; granting twice for one payment would be free money.
    """
    first = await credits.grant(db, user.id, 500, "purchase", stripe_payment_intent_id="pi_abc")
    await db.commit()
    assert first == 600

    second = await credits.grant(db, user.id, 500, "purchase", stripe_payment_intent_id="pi_abc")
    await db.commit()
    assert second == 600, "redelivered webhook must not double-credit"


async def test_distinct_payment_intents_both_credit(db: AsyncSession, user: User):
    await credits.grant(db, user.id, 500, "purchase", stripe_payment_intent_id="pi_one")
    await db.commit()
    await credits.grant(db, user.id, 500, "purchase", stripe_payment_intent_id="pi_two")
    await db.commit()
    assert await credits.get_balance(db, user.id) == 1100


async def test_weekly_spend_tracks_only_debits_for_that_campaign(
    db: AsyncSession, user: User, campaign
):
    await credits.spend(db, user.id, 10, "contact_discovered", campaign_id=campaign.id)
    await credits.spend(db, user.id, 4, "outreach_draft", campaign_id=campaign.id)
    # A debit with no campaign must not count toward the campaign's cap.
    await credits.spend(db, user.id, 7, "mcp_tool_call")
    # Nor should a credit.
    await credits.grant(db, user.id, 50, "promo_grant")
    await db.commit()

    assert await credits.weekly_spend(db, campaign.id) == 14


async def test_zero_and_negative_amounts_are_no_ops(db: AsyncSession, user: User):
    assert await credits.spend(db, user.id, 0, "contact_discovered") == 100
    assert await credits.grant(db, user.id, 0, "promo_grant") == 100
    assert await credits.get_balance(db, user.id) == 100
