import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.subscription import Subscription
from app.models.user import User
from app.services.analytics import posthog_capture

stripe.api_key = settings.stripe_secret_key
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stripe", tags=["stripe"])


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_email") or session.get("customer_details", {}).get("email")
        stripe_customer_id = session.get("customer")
        stripe_subscription_id = session.get("subscription")

        if customer_email:
            result = await db.execute(select(User).where(User.email == customer_email))
            user = result.scalar_one_or_none()
            if user:
                sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
                sub = sub_result.scalar_one_or_none()
                if not sub:
                    sub = Subscription(user_id=user.id)
                    db.add(sub)
                sub.plan = "pro"
                sub.status = "active"
                sub.stripe_customer_id = stripe_customer_id
                sub.stripe_subscription_id = stripe_subscription_id
                await db.commit()
                logger.info("Upgraded user %s to pro", user.email)
                await posthog_capture(str(user.id), "subscription_paid", {"plan": "pro", "email": user.email})

    elif event["type"] in ("customer.subscription.deleted", "customer.subscription.updated"):
        subscription_obj = event["data"]["object"]
        stripe_sub_id = subscription_obj.get("id")
        new_status = subscription_obj.get("status")

        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )
        sub = result.scalar_one_or_none()
        if sub:
            if new_status in ("canceled", "unpaid", "past_due"):
                sub.plan = "free"
                sub.status = new_status
            else:
                sub.status = new_status
            await db.commit()
            logger.info("Subscription %s status → %s", stripe_sub_id, new_status)
            # Look up user for PostHog
            from app.models.user import User as UserModel
            user_result = await db.execute(select(UserModel).where(UserModel.id == sub.user_id))
            sub_user = user_result.scalar_one_or_none()
            if sub_user:
                ph_event = "subscription_canceled" if new_status == "canceled" else f"subscription_{new_status}"
                await posthog_capture(str(sub_user.id), ph_event, {"status": new_status})

    return {"ok": True}


@router.post("/create-checkout-session")
async def create_checkout_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": settings.stripe_pro_price_id, "quantity": 1}],
        customer_email=current_user.email,
        success_url=f"{settings.frontend_url}/dashboard?upgraded=true",
        cancel_url=f"{settings.frontend_url}/pricing",
    )

    return {"url": session.url}


@router.post("/billing-portal")
async def billing_portal(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Subscription).where(Subscription.user_id == current_user.id))
    sub = result.scalar_one_or_none()

    if not sub or not sub.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer on record — please upgrade first")

    try:
        session = stripe.billing_portal.Session.create(
            customer=sub.stripe_customer_id,
            return_url=f"{settings.frontend_url}/settings",
        )
    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"url": session.url}


@router.post("/cancel-subscription")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Subscription).where(Subscription.user_id == current_user.id))
    sub = result.scalar_one_or_none()

    if not sub or sub.plan != "pro":
        raise HTTPException(status_code=400, detail="No active Pro subscription to cancel")

    if not sub.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No Stripe subscription ID on record")

    try:
        stripe.Subscription.cancel(sub.stripe_subscription_id)
    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    sub.plan = "free"
    sub.status = "canceled"
    await db.commit()

    logger.info("User %s cancelled Pro subscription %s", current_user.email, sub.stripe_subscription_id)
    return {"ok": True}
