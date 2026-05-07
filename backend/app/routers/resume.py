import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.resume import Resume
from app.models.user import User
from app.services.resume_parser import parse_resume, save_upload

router = APIRouter(prefix="/api/resume", tags=["resume"])

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
}
MAX_SIZE_MB = 10


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File must be under {MAX_SIZE_MB}MB")

    file_type = ALLOWED_TYPES[file.content_type]

    # Parse with Claude
    try:
        raw_text, structured_data = await parse_resume(file_bytes, file_type)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse resume: {exc}")

    # Deactivate old resumes
    result = await db.execute(
        select(Resume).where(Resume.user_id == current_user.id, Resume.is_active == True)
    )
    for old in result.scalars().all():
        old.is_active = False

    # Save file
    file_path = save_upload(file_bytes, file.filename or "resume", str(current_user.id))

    # Create DB record
    resume = Resume(
        user_id=current_user.id,
        filename=file.filename or "resume",
        file_path=file_path,
        file_type=file_type,
        raw_text=raw_text,
        structured_data=structured_data,
        is_active=True,
        parsed_at=datetime.now(timezone.utc),
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)

    return {
        "id": str(resume.id),
        "filename": resume.filename,
        "structured_data": resume.structured_data,
        "parsed_at": resume.parsed_at.isoformat() if resume.parsed_at else None,
    }


@router.delete("/{resume_id}", status_code=204)
async def delete_resume(
    resume_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == current_user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    if resume.file_path:
        allowed_root = str(Path(settings.upload_dir).resolve() / str(current_user.id))
        target = str(Path(resume.file_path).resolve())
        if target.startswith(allowed_root) and os.path.exists(resume.file_path):
            os.remove(resume.file_path)

    await db.delete(resume)
    await db.commit()


@router.get("/active")
async def get_active_resume(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Resume).where(Resume.user_id == current_user.id, Resume.is_active == True)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="No active resume")

    return {
        "id": str(resume.id),
        "filename": resume.filename,
        "file_type": resume.file_type,
        "structured_data": resume.structured_data,
        "parsed_at": resume.parsed_at.isoformat() if resume.parsed_at else None,
        "created_at": resume.created_at.isoformat() if resume.created_at else None,
    }
