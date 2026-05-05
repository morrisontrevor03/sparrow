import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from io import BytesIO
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.application import Application
from app.models.user import User
from app.services import quota
from app.services.pdf_service import generate_cover_letter_pdf, generate_resume_pdf

router = APIRouter(prefix="/api/applications", tags=["applications"])


class CoverLetterUpdate(BaseModel):
    cover_letter: str


@router.get("")
async def list_applications(
    status: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Application)
        .options(selectinload(Application.job), selectinload(Application.resume))
        .where(Application.user_id == current_user.id)
        .order_by(desc(Application.created_at))
    )
    if status:
        query = query.where(Application.status == status)

    result = await db.execute(query)
    apps = result.scalars().all()

    return [_serialize_application(a) for a in apps]


@router.get("/{application_id}")
async def get_application(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application)
        .options(selectinload(Application.job), selectinload(Application.resume))
        .where(Application.id == application_id, Application.user_id == current_user.id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return _serialize_application(app)


@router.post("/generate/{job_id}")
async def generate_application(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await quota.can_generate_application(db, current_user.id):
        raise HTTPException(status_code=402, detail="Free plan limit reached — upgrade to Pro for unlimited tailored materials")

    from app.agents.application import ApplicationAgent

    agent = ApplicationAgent(db, current_user.id)
    try:
        app = await agent.generate_for_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result = await db.execute(
        select(Application)
        .options(selectinload(Application.job), selectinload(Application.resume))
        .where(Application.id == app.id)
    )
    app = result.scalar_one()
    return _serialize_application(app)


async def _load_app_for_pdf(application_id: uuid.UUID, user_id, db):
    result = await db.execute(
        select(Application)
        .options(selectinload(Application.job))
        .where(Application.id == application_id, Application.user_id == user_id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if not app.tailored_resume or not app.cover_letter:
        raise HTTPException(status_code=400, detail="Draft is not ready yet")
    return app


def _safe_company(app) -> str:
    raw = app.job.company if app.job else "company"
    return "".join(c for c in raw if c.isalnum() or c in " _-").strip().replace(" ", "_")


@router.get("/{application_id}/cover-letter/pdf")
async def download_cover_letter_pdf(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    app = await _load_app_for_pdf(application_id, current_user.id, db)
    pdf_bytes = generate_cover_letter_pdf(
        name=current_user.full_name or current_user.email,
        email=current_user.email,
        job_title=app.job.title if app.job else "Position",
        company=app.job.company if app.job else "",
        cover_letter=app.cover_letter,
    )
    filename = f"cover_letter_{_safe_company(app)}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{application_id}/resume/pdf")
async def download_resume_pdf(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    app = await _load_app_for_pdf(application_id, current_user.id, db)
    pdf_bytes = generate_resume_pdf(
        name=current_user.full_name or current_user.email,
        email=current_user.email,
        tailored_resume=app.tailored_resume,
    )
    filename = f"resume_{_safe_company(app)}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/{application_id}/cover-letter")
async def update_cover_letter(
    application_id: uuid.UUID,
    body: CoverLetterUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application).where(Application.id == application_id, Application.user_id == current_user.id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    app.cover_letter = body.cover_letter
    await db.commit()
    return {"ok": True}


def _serialize_application(a: Application) -> dict:
    data = {
        "id": str(a.id),
        "user_id": str(a.user_id),
        "job_id": str(a.job_id),
        "resume_id": str(a.resume_id) if a.resume_id else None,
        "status": a.status,
        "tailored_resume": a.tailored_resume,
        "cover_letter": a.cover_letter,
        "tailoring_notes": a.tailoring_notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }
    if a.job:
        data["job"] = {
            "id": str(a.job.id),
            "title": a.job.title,
            "company": a.job.company,
            "location": a.job.location,
            "url": a.job.url,
            "match_score": a.job.match_score,
            "description": a.job.description,
        }
    return data
