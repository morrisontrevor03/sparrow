from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserPreferences

router = APIRouter(prefix="/api/settings", tags=["settings"])


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
