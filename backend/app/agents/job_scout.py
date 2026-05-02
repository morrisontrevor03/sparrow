import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.models.job import Job
from app.models.user import User, UserPreferences
from app.services import job_api_client, quota
from app.services.email_service import new_jobs_digest_email, send_email
from app.config import settings

TOOLS = [
    {
        "name": "search_jobs_adzuna",
        "description": "Search for job postings on Adzuna by keyword and location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keywords": {"type": "string", "description": "Job title / role keywords"},
                "location": {"type": "string", "description": "City or region (optional)"},
                "max_results": {"type": "integer", "default": 20},
            },
            "required": ["keywords"],
        },
    },
    {
        "name": "search_jobs_jsearch",
        "description": "Search for job postings via JSearch (aggregates LinkedIn, Indeed, Glassdoor).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "location": {"type": "string"},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "save_scored_jobs",
        "description": "Save a list of scored job matches to the database. Only call this once per run with all results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "jobs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "external_id": {"type": "string"},
                            "source": {"type": "string"},
                            "title": {"type": "string"},
                            "company": {"type": "string"},
                            "location": {"type": "string"},
                            "description": {"type": "string"},
                            "url": {"type": "string"},
                            "salary_min": {"type": "integer"},
                            "salary_max": {"type": "integer"},
                            "employment_type": {"type": "string"},
                            "match_score": {"type": "number", "description": "0.0 to 1.0"},
                            "match_reasoning": {"type": "string"},
                        },
                        "required": ["title", "company", "url", "match_score", "match_reasoning"],
                    },
                }
            },
            "required": ["jobs"],
        },
    },
]


class JobScoutAgent(BaseAgent):
    agent_type = "job_scout"

    async def _execute(self, **kwargs) -> dict:
        # Load user + preferences
        user_result = await self.db.execute(select(User).where(User.id == self.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return {"summary": "User not found"}

        prefs_result = await self.db.execute(select(UserPreferences).where(UserPreferences.user_id == self.user_id))
        prefs = prefs_result.scalar_one_or_none()
        if not prefs or not prefs.target_roles:
            return {"summary": "No target roles configured"}

        # Load known external IDs to avoid duplicates
        existing_result = await self.db.execute(
            select(Job.external_id, Job.source).where(Job.user_id == self.user_id)
        )
        existing = {(row.external_id, row.source) for row in existing_result}

        system_prompt = f"""You are the ApplyNow Job Scout. Your job is to find highly relevant job postings for a user.

User profile:
- Target roles: {prefs.target_roles}
- Target locations: {prefs.target_locations or ["Remote"]}
- Experience level: {prefs.experience_level or "mid"}
- Min salary: {prefs.min_salary or "not specified"}
- Employment types: {prefs.employment_types or ["full_time"]}
- Excluded companies: {prefs.excluded_companies or []}

Instructions:
1. Search for jobs using both Adzuna and JSearch with varied keyword combinations from the target roles.
2. Score each job 0.0 to 1.0 based on how well it matches the user's profile. Be strict — 0.85+ means excellent match.
3. Only include jobs with score >= 0.6.
4. Exclude jobs from excluded companies.
5. Call save_scored_jobs once with all the qualified results.
6. Do not save jobs with these (external_id, source) pairs as they already exist: {list(existing)[:50]}
"""

        initial_message = (
            f"Search for new job postings for these roles: {prefs.target_roles}. "
            f"Locations: {prefs.target_locations or ['Remote']}. "
            f"Find the best matches and save them."
        )

        await self.run_tool_loop(system_prompt, initial_message, TOOLS)

        # Return stats (set by dispatch_tool)
        jobs_saved = getattr(self, "_jobs_saved", 0)
        return {"summary": f"Saved {jobs_saved} new jobs", "jobs_found": jobs_saved}

    async def dispatch_tool(self, name: str, input_data: dict) -> Any:
        if name == "search_jobs_adzuna":
            results = await job_api_client.search_adzuna(
                input_data["keywords"],
                input_data.get("location", ""),
                input_data.get("max_results", 20),
            )
            return json.dumps(results)

        if name == "search_jobs_jsearch":
            results = await job_api_client.search_jsearch(
                input_data["query"],
                input_data.get("location", ""),
                input_data.get("max_results", 10),
            )
            return json.dumps(results)

        if name == "save_scored_jobs":
            return await self._save_jobs(input_data["jobs"])

        return f"Unknown tool: {name}"

    async def _save_jobs(self, jobs_data: list[dict]) -> str:
        saved = 0
        new_jobs = []

        for item in jobs_data:
            # Check quota
            if not await quota.can_surface_job(self.db, self.user_id):
                break

            # De-duplicate
            ext_id = item.get("external_id") or item.get("url")
            source = item.get("source", "unknown")
            existing = await self.db.execute(
                select(Job).where(
                    Job.user_id == self.user_id,
                    Job.external_id == ext_id,
                    Job.source == source,
                )
            )
            if existing.scalar_one_or_none():
                continue

            job = Job(
                user_id=self.user_id,
                external_id=ext_id,
                source=source,
                title=item.get("title", ""),
                company=item.get("company", ""),
                location=item.get("location"),
                description=item.get("description"),
                url=item.get("url", ""),
                salary_min=item.get("salary_min"),
                salary_max=item.get("salary_max"),
                employment_type=item.get("employment_type"),
                match_score=float(item.get("match_score", 0)),
                match_reasoning=item.get("match_reasoning", ""),
            )
            self.db.add(job)
            await self.db.flush()
            await quota.increment_jobs_surfaced(self.db, self.user_id)
            saved += 1
            new_jobs.append(job)

        await self.db.commit()
        self._jobs_saved = saved

        # Send a single digest email for all newly found jobs
        if saved > 0:
            user_result = await self.db.execute(select(User).where(User.id == self.user_id))
            user = user_result.scalar_one_or_none()
            if user:
                jobs_payload = [
                    {
                        "id": str(job.id),
                        "title": job.title,
                        "company": job.company,
                        "location": job.location,
                        "url": job.url,
                        "match_score": job.match_score or 0,
                        "match_reasoning": job.match_reasoning or "",
                    }
                    for job in new_jobs
                ]
                # Sort highest match first
                jobs_payload.sort(key=lambda j: j["match_score"], reverse=True)
                html = new_jobs_digest_email(jobs_payload, settings.frontend_url)
                subject = f"{saved} new job{'s' if saved != 1 else ''} found — apply early"
                await send_email(user.email, subject, html)
                for job in new_jobs:
                    job.email_sent = True
                await self.db.commit()

        return f"Saved {saved} jobs. Digest email sent with {len(new_jobs)} jobs."
