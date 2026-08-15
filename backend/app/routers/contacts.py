import uuid

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.contact import Contact
from app.models.user import User
from app.services import credits, drafting, targeting

router = APIRouter(prefix="/api/contacts", tags=["contacts"])

VALID_OUTREACH_STATUSES = {
    "discovered",
    "message_drafted",
    "sent",
    "replied",
    "meeting_scheduled",
}


class ContactUpdate(BaseModel):
    outreach_status: str | None = None
    notes: str | None = None
    outreach_message: str | None = None

    @field_validator("outreach_status")
    @classmethod
    def validate_outreach_status(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_OUTREACH_STATUSES:
            raise ValueError(
                f"outreach_status must be one of: {', '.join(sorted(VALID_OUTREACH_STATUSES))}"
            )
        return v


@router.get("")
async def list_contacts(
    campaign_id: uuid.UUID | None = Query(None),
    company: str | None = Query(None),
    status: str | None = Query(None),
    score_min: float = Query(0.0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Contact)
        .where(Contact.user_id == current_user.id)
        .order_by(desc(Contact.relevance_score), desc(Contact.discovered_at))
    )
    if campaign_id:
        query = query.where(Contact.campaign_id == campaign_id)
    if company:
        query = query.where(Contact.company.ilike(f"%{company}%"))
    if status:
        query = query.where(Contact.outreach_status == status)
    if score_min:
        query = query.where(Contact.relevance_score >= score_min)

    result = await db.execute(query)
    return [_serialize(c) for c in result.scalars().all()]


async def _get_owned(db: AsyncSession, contact_id: uuid.UUID, user_id: uuid.UUID) -> Contact:
    contact = (
        await db.execute(
            select(Contact).where(Contact.id == contact_id, Contact.user_id == user_id)
        )
    ).scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.get("/{contact_id}")
async def get_contact(
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _serialize(await _get_owned(db, contact_id, current_user.id))


@router.patch("/{contact_id}")
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contact = await _get_owned(db, contact_id, current_user.id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(contact, field, value)
    await db.commit()
    await db.refresh(contact)
    return _serialize(contact)


@router.post("/{contact_id}/draft-message")
async def draft_outreach_message(
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contact = await _get_owned(db, contact_id, current_user.id)

    if not await credits.has_credits(db, current_user.id, settings.credits_per_draft):
        raise HTTPException(
            status_code=402,
            detail=f"Out of credits — drafting a message costs {settings.credits_per_draft}",
        )

    campaign = await drafting.load_campaign_for_contact(db, contact, current_user.id)
    profile = targeting.get_profile(campaign.campaign_type if campaign else None)
    objective = (
        (campaign.objective or campaign.name)
        if campaign
        else "Start a genuine professional conversation with this person."
    )

    sender = await drafting.build_sender_context(db, current_user)
    prompt = drafting.build_draft_prompt(sender, contact, profile, objective)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model="claude-sonnet-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    message = next((b.text for b in resp.content if b.type == "text"), "").strip()
    if not message:
        raise HTTPException(status_code=502, detail="Draft generation returned no text")

    contact.outreach_message = message
    if contact.outreach_status == "discovered":
        contact.outreach_status = "message_drafted"

    # Charge only after a usable draft exists.
    await credits.spend(
        db,
        current_user.id,
        settings.credits_per_draft,
        "outreach_draft",
        campaign_id=contact.campaign_id,
    )
    await db.commit()
    await db.refresh(contact)
    return _serialize(contact)


@router.delete("", status_code=204)
async def delete_all_contacts(
    campaign_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = delete(Contact).where(Contact.user_id == current_user.id)
    if campaign_id:
        stmt = stmt.where(Contact.campaign_id == campaign_id)
    await db.execute(stmt)
    await db.commit()


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contact = await _get_owned(db, contact_id, current_user.id)
    await db.delete(contact)
    await db.commit()


def _serialize(c: Contact) -> dict:
    return {
        "id": str(c.id),
        "campaign_id": str(c.campaign_id) if c.campaign_id else None,
        "company": c.company,
        "first_name": c.first_name,
        "last_name": c.last_name,
        "title": c.title,
        "linkedin_url": c.linkedin_url,
        "email": c.email,
        "seniority": c.seniority,
        "department": c.department,
        "relevance_score": c.relevance_score,
        "relevance_reasoning": c.relevance_reasoning,
        "outreach_status": c.outreach_status,
        "outreach_message": c.outreach_message,
        "notes": c.notes,
        "discovered_at": c.discovered_at.isoformat() if c.discovered_at else None,
    }
