import logging
import uuid as _uuid

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CREDIT_PACKS, pack_price_id, settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.credits import CreditPurchase
from app.models.subscription import BillingAccount
from app.models.user import User
from app.services import credits
from app.services.analytics import posthog_capture

stripe.api_key = settings.stripe_secret_key
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    pack_id: str


@router.get("/packs")
async def list_packs():
    return [
        {
            "id": pack_id,
            "name": pack["name"],
            "credits": pack["credits"],
            "amount_cents": pack["amount_cents"],
            "price_per_credit_cents": round(pack["amount_cents"] / pack["credits"], 3),
        }
        for pack_id, pack in CREDIT_PACKS.items()
    ]


@router.get("/balance")
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    balance = await credits.get_balance(db, current_user.id)
    return {
        "balance": balance,
        "low_balance": balance < settings.low_balance_threshold,
        "costs": {
            "contact": settings.credits_per_contact,
            "draft": settings.credits_per_draft,
            "mcp_call": settings.credits_per_mcp_call,
        },
    }


@router.get("/ledger")
async def get_ledger(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entries = await credits.recent_entries(db, current_user.id)
    return [
        {
            "id": str(e.id),
            "delta": e.delta,
            "reason": e.reason,
            "campaign_id": str(e.campaign_id) if e.campaign_id else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]


async def _get_or_create_customer(db: AsyncSession, user: User) -> str:
    account = (
        await db.execute(select(BillingAccount).where(BillingAccount.user_id == user.id))
    ).scalar_one_or_none()

    if account and account.stripe_customer_id:
        return account.stripe_customer_id

    customer = stripe.Customer.create(
        email=user.email,
        name=user.full_name or None,
        metadata={"user_id": str(user.id)},
    )
    if account:
        account.stripe_customer_id = customer.id
    else:
        db.add(BillingAccount(user_id=user.id, stripe_customer_id=customer.id))
    await db.commit()
    return customer.id


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pack = CREDIT_PACKS.get(body.pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Unknown credit pack")

    price_id = pack_price_id(body.pack_id)
    if not price_id:
        # Fail loudly rather than selling the wrong thing with a missing env var.
        logger.error("Stripe price ID not configured for pack %s", body.pack_id)
        raise HTTPException(status_code=503, detail="Billing is not configured")

    customer_id = await _get_or_create_customer(db, current_user)

    session = stripe.checkout.Session.create(
        mode="payment",
        customer=customer_id,
        client_reference_id=str(current_user.id),
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.frontend_url}/settings?tab=billing&purchase=success",
        cancel_url=f"{settings.frontend_url}/settings?tab=billing&purchase=canceled",
        metadata={
            "user_id": str(current_user.id),
            "pack_id": body.pack_id,
            "credits": str(pack["credits"]),
        },
        payment_intent_data={
            "metadata": {
                "user_id": str(current_user.id),
                "pack_id": body.pack_id,
                "credits": str(pack["credits"]),
            }
        },
    )

    db.add(
        CreditPurchase(
            user_id=current_user.id,
            pack_id=body.pack_id,
            credits=pack["credits"],
            amount_cents=pack["amount_cents"],
            stripe_checkout_session_id=session.id,
            status="pending",
        )
    )
    await db.commit()

    # posthog_capture is async; the old Stripe router called it without await,
    # which produced a never-awaited coroutine and silently dropped the event.
    await posthog_capture(str(current_user.id), "checkout_started", {"pack_id": body.pack_id})
    return {"url": session.url, "session_id": session.id}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except Exception as exc:
        logger.warning("Stripe webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook signature") from exc

    if event["type"] != "checkout.session.completed":
        return {"received": True}

    session = event["data"]["object"]
    if session.get("payment_status") != "paid":
        logger.info("Checkout session %s completed but not paid — ignoring", session.get("id"))
        return {"received": True}

    payment_intent_id = session.get("payment_intent")
    if not payment_intent_id:
        logger.error("Checkout session %s has no payment_intent — cannot grant idempotently", session.get("id"))
        return {"received": True}

    metadata = session.get("metadata") or {}
    user_id_ref = session.get("client_reference_id") or metadata.get("user_id")

    user = None
    if user_id_ref:
        try:
            _uuid.UUID(user_id_ref)
        except ValueError:
            logger.error(
                "checkout.session.completed: client_reference_id %r is not a valid UUID (session %s)",
                user_id_ref,
                session.get("id"),
            )
        else:
            user = (
                await db.execute(select(User).where(User.id == user_id_ref))
            ).scalar_one_or_none()

    if not user:
        logger.error(
            "checkout.session.completed: could not resolve a user for session %s", session.get("id")
        )
        return {"received": True}

    purchase = (
        await db.execute(
            select(CreditPurchase).where(
                CreditPurchase.stripe_checkout_session_id == session.get("id")
            )
        )
    ).scalar_one_or_none()

    # Trust the pack recorded at checkout time; fall back to session metadata for
    # sessions created outside the app.
    amount = purchase.credits if purchase else int(metadata.get("credits") or 0)
    if amount <= 0:
        logger.error("checkout.session.completed: no credit amount for session %s", session.get("id"))
        return {"received": True}

    balance = await credits.grant(
        db,
        user.id,
        amount,
        "purchase",
        stripe_payment_intent_id=payment_intent_id,
        metadata={"pack_id": metadata.get("pack_id"), "session_id": session.get("id")},
    )

    if purchase and purchase.status != "paid":
        purchase.status = "paid"
        purchase.stripe_payment_intent_id = payment_intent_id
        from datetime import datetime, timezone

        purchase.completed_at = datetime.now(timezone.utc)

    await db.commit()

    await posthog_capture(
        str(user.id),
        "credits_purchased",
        {"credits": amount, "pack_id": metadata.get("pack_id"), "balance": balance},
    )
    logger.info("Granted %d credits to user %s (balance %d)", amount, user.id, balance)
    return {"received": True}
