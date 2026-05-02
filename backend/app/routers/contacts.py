import uuid

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.contact import Contact
from app.models.user import User, UserPreferences

router = APIRouter(prefix="/api/contacts", tags=["contacts"])

VALID_OUTREACH_STATUSES = {"discovered", "message_drafted", "sent", "replied", "meeting_scheduled"}


class ContactUpdate(BaseModel):
    outreach_status: str | None = None
    notes: str | None = None
    outreach_message: str | None = None

    @field_validator("outreach_status")
    @classmethod
    def validate_outreach_status(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_OUTREACH_STATUSES:
            raise ValueError(f"outreach_status must be one of: {', '.join(sorted(VALID_OUTREACH_STATUSES))}")
        return v


@router.get("")
async def list_contacts(
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
    if company:
        query = query.where(Contact.company.ilike(f"%{company}%"))
    if status:
        query = query.where(Contact.outreach_status == status)
    if score_min:
        query = query.where(Contact.relevance_score >= score_min)

    result = await db.execute(query)
    contacts = result.scalars().all()
    return [_serialize(c) for c in contacts]


@router.get("/{contact_id}")
async def get_contact(
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")
    return _serialize(c)


@router.patch("/{contact_id}")
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(c, field, value)

    await db.commit()
    await db.refresh(c)
    return _serialize(c)


@router.post("/{contact_id}/draft-message")
async def draft_outreach_message(
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")

    prefs_result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == current_user.id)
    )
    prefs = prefs_result.scalar_one_or_none()

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    prompt = (
        f"Write a warm, concise LinkedIn cold outreach message (2-3 sentences) from a "
        f"{getattr(prefs, 'experience_level', 'entry') or 'entry'}-level job seeker "
        f"targeting {', '.join(getattr(prefs, 'target_roles', ['software engineering']) or ['software engineering'])} roles "
        f"to {c.first_name} {c.last_name or ''}, who is a {c.title} at {c.company}.\n\n"
        f"Rules: reference the company or team (not their title), ask to learn about the team or culture, "
        f"never ask for a job or referral directly. Return only the message text, no subject line."
    )

    resp = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    message = resp.content[0].text.strip()

    c.outreach_message = message
    await db.commit()
    await db.refresh(c)
    return _serialize(c)


@router.delete("", status_code=204)
async def delete_all_contacts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(Contact).where(Contact.user_id == current_user.id))
    await db.commit()


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(c)
    await db.commit()


def _serialize(c: Contact) -> dict:
    return {
        "id": str(c.id),
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
