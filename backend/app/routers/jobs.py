import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.application import Application
from app.models.job import Job
from app.models.user import User
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobResponse(BaseModel):
    id: str
    external_id: str | None
    source: str
    title: str
    company: str
    location: str | None
    description: str | None
    url: str
    salary_min: int | None
    salary_max: int | None
    employment_type: str | None
    posted_at: str | None
    match_score: float | None
    match_reasoning: str | None
    is_new: bool
    is_dismissed: bool
    discovered_at: str

    model_config = {"from_attributes": True}

    def model_post_init(self, __context):
        self.id = str(self.id)
        self.discovered_at = str(self.discovered_at)


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    score_min: float = Query(0.0),
    company: str | None = Query(None),
    is_new: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Job)
        .options(selectinload(Job.application))
        .where(Job.user_id == current_user.id, Job.is_dismissed == False)
        .order_by(desc(Job.match_score), desc(Job.discovered_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if score_min:
        query = query.where(Job.match_score >= score_min)
    if company:
        query = query.where(Job.company.ilike(f"%{company}%"))
    if is_new is not None:
        query = query.where(Job.is_new == is_new)

    result = await db.execute(query)
    jobs = result.scalars().all()
    return [_serialize_job(j) for j in jobs]


@router.get("/{job_id}")
async def get_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Job)
        .options(selectinload(Job.application))
        .where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.is_new = False
    await db.commit()

    return _serialize_job(job)


def _serialize_job(j: Job) -> dict:
    return {
        "id": str(j.id),
        "external_id": j.external_id,
        "source": j.source,
        "title": j.title,
        "company": j.company,
        "location": j.location,
        "description": j.description,
        "url": j.url,
        "salary_min": j.salary_min,
        "salary_max": j.salary_max,
        "employment_type": j.employment_type,
        "posted_at": j.posted_at.isoformat() if j.posted_at else None,
        "match_score": j.match_score,
        "match_reasoning": j.match_reasoning,
        "is_new": j.is_new,
        "is_dismissed": j.is_dismissed,
        "discovered_at": j.discovered_at.isoformat() if j.discovered_at else None,
        "application_id": str(j.application.id) if j.application else None,
    }


@router.patch("/{job_id}/dismiss")
async def dismiss_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user.id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.is_dismissed = True
    await db.commit()
    return {"ok": True}
