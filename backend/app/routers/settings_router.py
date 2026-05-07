import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserPreferences
from app.services.company_match import FUNDING_DB_KEYWORDS, clean_company_name

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Per-user rate limit for autocomplete (calls Claude): 5 per hour
_autocomplete_rate_store: dict[str, list[datetime]] = defaultdict(list)
_AUTOCOMPLETE_RATE_WINDOW = timedelta(hours=1)
_AUTOCOMPLETE_RATE_MAX = 5


def _enforce_autocomplete_rate_limit(user_id: uuid.UUID) -> None:
    key = str(user_id)
    now = datetime.now(timezone.utc)
    cutoff = now - _AUTOCOMPLETE_RATE_WINDOW
    attempts = [t for t in _autocomplete_rate_store[key] if t > cutoff]
    if len(attempts) >= _AUTOCOMPLETE_RATE_MAX:
        raise HTTPException(status_code=429, detail="Rate limit reached — maximum 5 autocomplete requests per hour")
    attempts.append(now)
    _autocomplete_rate_store[key] = attempts


class PreferencesUpdate(BaseModel):
    target_roles: list[str] | None = None
    target_companies: list[str] | None = None
    target_locations: list[str] | None = None
    excluded_companies: list[str] | None = None
    min_salary: int | None = None
    max_salary: int | None = None
    employment_types: list[str] | None = None
    experience_level: str | None = None
    salary_type: str | None = None
    location_flexible: bool | None = None
    work_environment: list[str] | None = None
    open_to_similar_companies: bool | None = None
    company_stages: list[str] | None = None
    company_industries: list[str] | None = None
    scout_enabled: bool | None = None
    networking_enabled: bool | None = None
    application_agent_enabled: bool | None = None


class PreferencesResponse(BaseModel):
    target_roles: list[str]
    target_companies: list[str]
    target_locations: list[str]
    excluded_companies: list[str]
    min_salary: int | None
    max_salary: int | None
    employment_types: list[str]
    experience_level: str | None
    salary_type: str | None
    location_flexible: bool
    work_environment: list[str]
    open_to_similar_companies: bool
    company_stages: list[str]
    company_industries: list[str]
    scout_enabled: bool
    networking_enabled: bool
    application_agent_enabled: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=PreferencesResponse)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserPreferences).where(UserPreferences.user_id == current_user.id))
    prefs = result.scalar_one_or_none()
    if not prefs:
        raise HTTPException(status_code=404, detail="Preferences not found")
    return prefs


@router.put("", response_model=PreferencesResponse)
async def update_settings(
    body: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserPreferences).where(UserPreferences.user_id == current_user.id))
    prefs = result.scalar_one_or_none()
    if not prefs:
        prefs = UserPreferences(user_id=current_user.id)
        db.add(prefs)

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(prefs, field, value)

    await db.commit()
    await db.refresh(prefs)
    return prefs


class AutocompleteRequest(BaseModel):
    seed_companies: list[str]


@router.post("/companies/autocomplete")
async def autocomplete_companies(
    body: AutocompleteRequest,
    current_user: User = Depends(get_current_user),
):
    _enforce_autocomplete_rate_limit(current_user.id)
    if len(body.seed_companies) < 5:
        raise HTTPException(status_code=400, detail="Add at least 5 companies before using Autocomplete")

    max_suggestions = 25 - len(body.seed_companies)
    if max_suggestions <= 0:
        return {"suggestions": []}

    seeds_str = ", ".join(body.seed_companies[:20])
    prompt = (
        f"List exactly {max_suggestions} real, currently-active technology companies "
        f"that are similar in size, stage, and industry to these companies: {seeds_str}.\n\n"
        "Rules:\n"
        "- Do NOT include any of the seed companies or obvious variants of them.\n"
        "- One company name per line, no numbering, no extra text.\n"
        "- Official trading name only (e.g. 'Stripe' not 'Stripe Inc.').\n"
        "- Only include actual operating technology businesses — not investment data platforms "
        "(PitchBook, Crunchbase, AngelList, Carta, CB Insights, Dealroom, Preqin, etc.).\n"
        f"If fewer than {max_suggestions} companies match, return as many as you can."
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()

    seed_lower = {clean_company_name(c).lower() for c in body.seed_companies}
    suggestions: list[str] = []
    for line in raw.splitlines():
        name = line.strip()
        if not name:
            continue
        name = re.sub(r"^[\d]+[.)]\s*", "", name)
        name = re.sub(r"^[-•]\s*", "", name)
        if not name:
            continue
        if any(kw in name.lower() for kw in FUNDING_DB_KEYWORDS):
            continue
        if clean_company_name(name).lower() in seed_lower:
            continue
        suggestions.append(name)
        if len(suggestions) >= max_suggestions:
            break

    return {"suggestions": suggestions}
