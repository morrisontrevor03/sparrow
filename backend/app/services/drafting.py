"""
Outreach message drafting.

Shared by the agent (bulk drafting during a run), the REST API (re-draft a single
contact), and the MCP server, so all three produce the same voice.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.resume import Resume
from app.models.user import User, UserPreferences
from app.services.targeting import TargetingProfile


async def build_sender_context(db: AsyncSession, user: User) -> str:
    """Assemble who the sender is, for personalizing outreach."""
    prefs = (
        await db.execute(select(UserPreferences).where(UserPreferences.user_id == user.id))
    ).scalar_one_or_none()

    parts: list[str] = []
    if user.full_name:
        parts.append(f"Name: {user.full_name}")
    if prefs and prefs.headline:
        parts.append(f"Headline: {prefs.headline}")
    if prefs and prefs.value_prop:
        parts.append(f"What they offer: {prefs.value_prop}")

    resume = (
        (
            await db.execute(
                select(Resume)
                .where(Resume.user_id == user.id, Resume.is_active.is_(True))
                .order_by(Resume.created_at.desc())
            )
        )
        .scalars()
        .first()
    )

    if resume and resume.structured_data:
        data = resume.structured_data
        if summary := data.get("summary"):
            parts.append(f"Background: {summary}")
        if skills := data.get("skills"):
            parts.append(f"Skills: {', '.join(skills[:10])}")
        experience = data.get("experience") or []
        if experience:
            latest = experience[0]
            role, org = latest.get("role", ""), latest.get("company", "")
            if role or org:
                parts.append(f"Most recent role: {role} at {org}".strip())

    return "\n".join(parts) if parts else "No background provided."


def build_draft_prompt(
    sender_context: str,
    contact: Contact,
    profile: TargetingProfile,
    objective: str,
) -> str:
    full_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or "there"
    return (
        f"Write a LinkedIn cold outreach message from {profile.persona}.\n\n"
        f"ABOUT THE SENDER:\n{sender_context}\n\n"
        f"WHAT THE SENDER IS TRYING TO ACCOMPLISH:\n{objective}\n\n"
        f"RECIPIENT: {full_name} — {contact.title} at {contact.company}\n\n"
        f"GUIDANCE FOR THIS KIND OF OUTREACH:\n{profile.ask_guidance}\n\n"
        "Rules: 2-3 sentences. Reference something specific about their company or team "
        "rather than flattering their title. Sound like a person, not a template — no "
        "'I hope this finds you well', no 'I wanted to reach out'. Return only the message "
        "text, with no subject line and no signature."
    )


async def load_campaign_for_contact(
    db: AsyncSession, contact: Contact, user_id: uuid.UUID
) -> Campaign | None:
    if not contact.campaign_id:
        return None
    return (
        await db.execute(
            select(Campaign).where(
                Campaign.id == contact.campaign_id, Campaign.user_id == user_id
            )
        )
    ).scalar_one_or_none()
