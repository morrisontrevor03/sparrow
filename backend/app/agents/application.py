import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)
from app.config import settings
from app.models.application import Application
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User
from app.services.email_service import draft_ready_email, send_email

TOOLS = [
    {
        "name": "get_unprocessed_jobs",
        "description": "Get jobs with high match scores that don't have an application draft yet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "min_score": {"type": "number", "default": 0.75},
            },
        },
    },
    {
        "name": "create_application_draft",
        "description": "Save a tailored resume and cover letter draft for a job. Call this for each job.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "tailored_resume": {
                    "type": "object",
                    "description": "Modified version of the user's structured resume, with bullets tailored to the job description.",
                },
                "cover_letter": {"type": "string", "description": "3-paragraph cover letter for this specific role."},
                "tailoring_notes": {"type": "string", "description": "Brief explanation of what was changed and why."},
            },
            "required": ["job_id", "tailored_resume", "cover_letter", "tailoring_notes"],
        },
    },
]


class ApplicationAgent(BaseAgent):
    agent_type = "application"

    async def _execute(self, **kwargs) -> dict:
        user_result = await self.db.execute(select(User).where(User.id == self.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return {"summary": "User not found"}

        # Get active resume
        resume_result = await self.db.execute(
            select(Resume).where(Resume.user_id == self.user_id, Resume.is_active == True)
        )
        resume = resume_result.scalar_one_or_none()
        if not resume or not resume.structured_data:
            return {"summary": "No parsed resume found — user needs to upload a resume first"}

        system_prompt = f"""You are the ApplyNow Application Agent. For each unprocessed job, tailor the user's resume and write a cover letter.

User's resume (structured):
{json.dumps(resume.structured_data, indent=2)}

Instructions:
1. Call get_unprocessed_jobs to get jobs that need drafts.
2. For each job:
   a. Read the job description carefully.
   b. Tailor the resume: rewrite 2–4 experience bullet points to better match JD keywords and requirements.
      Keep changes authentic — don't invent skills or experience.
   c. Write a 3-paragraph cover letter:
      - Para 1: Hook — why this company/role specifically excites the candidate
      - Para 2: 2–3 concrete experiences that map directly to job requirements
      - Para 3: Brief closing, enthusiasm, CTA
   d. Call create_application_draft with the job_id, tailored_resume, cover_letter, and notes.
3. Process all jobs in the list.
"""

        initial_message = "Check for new jobs that need application drafts and create them."

        await self.run_tool_loop(system_prompt, initial_message, TOOLS)

        apps_created = getattr(self, "_apps_created", 0)
        return {"summary": f"Created {apps_created} application drafts", "applications_created": apps_created}

    async def dispatch_tool(self, name: str, input_data: dict) -> Any:
        if name == "get_unprocessed_jobs":
            return await self._get_unprocessed_jobs(input_data.get("min_score", 0.75))

        if name == "create_application_draft":
            return await self._create_draft(input_data)

        return f"Unknown tool: {name}"

    async def _get_unprocessed_jobs(self, min_score: float) -> str:
        # Jobs with no existing application
        result = await self.db.execute(
            select(Job)
            .outerjoin(Application, Job.id == Application.job_id)
            .where(
                Job.user_id == self.user_id,
                Job.match_score >= min_score,
                Job.is_dismissed == False,
                Application.id == None,
            )
            .limit(5)  # Process max 5 per run to control token usage
        )
        jobs = result.scalars().all()

        rows = []
        for j in jobs:
            desc = j.description or ""
            if len(desc) > 3000:
                logger.warning("Truncating job description for '%s' at %s (%d chars)", j.title, j.company, len(desc))
            rows.append({
                "job_id": str(j.id),
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "description": desc[:3000],
                "url": j.url,
                "match_score": j.match_score,
            })
        return json.dumps(rows)

    async def _create_draft(self, data: dict) -> str:
        job_id = uuid.UUID(data["job_id"])

        # Check job belongs to user
        job_result = await self.db.execute(
            select(Job).where(Job.id == job_id, Job.user_id == self.user_id)
        )
        job = job_result.scalar_one_or_none()
        if not job:
            return "Job not found"

        # Get active resume
        resume_result = await self.db.execute(
            select(Resume).where(Resume.user_id == self.user_id, Resume.is_active == True)
        )
        resume = resume_result.scalar_one_or_none()

        tailored_resume = data.get("tailored_resume")
        cover_letter = (data.get("cover_letter") or "").strip()
        quality_ok = (
            tailored_resume
            and isinstance(tailored_resume, dict)
            and len(cover_letter) >= 50
        )
        if not quality_ok:
            logger.warning(
                "Low-quality draft for '%s' at %s — setting status=draft (tailored=%s, cover_len=%d)",
                job.title, job.company, bool(tailored_resume), len(cover_letter),
            )

        application = Application(
            user_id=self.user_id,
            job_id=job_id,
            resume_id=resume.id if resume else None,
            status="ready" if quality_ok else "draft",
            tailored_resume=tailored_resume,
            cover_letter=cover_letter or None,
            tailoring_notes=data.get("tailoring_notes"),
        )
        self.db.add(application)
        await self.db.flush()
        await self.db.commit()

        if not hasattr(self, "_apps_created"):
            self._apps_created = 0
        self._apps_created += 1

        # Send email notification
        user_result = await self.db.execute(select(User).where(User.id == self.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            html = draft_ready_email(job.title, job.company, str(application.id), settings.frontend_url)
            await send_email(
                user.email,
                f"Draft ready: {job.title} at {job.company}",
                html,
            )

        return f"Draft created for {job.title} at {job.company} (id: {application.id})"
