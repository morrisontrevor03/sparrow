import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.models.contact import Contact
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User, UserPreferences
from app.services import job_api_client, quota
from app.services.company_match import companies_match
from app.services.email_service import new_jobs_digest_email, send_email
from app.config import settings

# Ordered so higher index = warmer relationship
_OUTREACH_RANK = {
    "discovered": 0,
    "message_drafted": 1,
    "sent": 2,
    "replied": 3,
    "meeting_scheduled": 4,
}

# (title keywords) → minimum user level index needed to realistically apply
# level order: entry=0, junior=1, mid=2, senior=3, staff=4, lead=5
_TITLE_LEVEL_GATES = [
    ({"director", "vp", "vice president", "head of", "chief"}, 4),
    ({"staff engineer", "staff software", "staff data", "staff ml", "principal engineer",
      "principal software", "principal data", "principal product", "principal ml"}, 3),
    ({"senior ", "sr. ", " sr ", "lead engineer", "lead developer",
      "lead software", "lead data", "lead ml"}, 2),
]

_LEVEL_ORDER = {"entry": 0, "junior": 1, "mid": 2, "senior": 3, "staff": 4, "lead": 5}


def _experience_hard_rules(experience_level: str, employment_types: list[str]) -> str:
    """Build the non-negotiable experience matching rules injected into the system prompt."""
    seeking_internship = "internship" in (employment_types or [])

    lines: list[str] = [
        "HARD EXPERIENCE MATCHING RULES — these are absolute, override everything else:",
    ]

    if seeking_internship:
        lines += [
            "- This user is seeking INTERNSHIPS. Any non-internship posting (full-time, part-time, contract) must be scored 0.0 and NOT saved.",
            "- Only save internship listings.",
        ]
    else:
        lines += [
            "- This user is NOT seeking internships. Any internship listing must be scored 0.0 and NOT saved.",
        ]

    level_rules: dict[str, list[str]] = {
        "entry": [
            "- User is ENTRY LEVEL (new grad, 0–1 YOE). Score 0.0 and do NOT save if ANY of:",
            "  • Job title contains: Senior, Sr., Staff, Principal, Lead (as seniority), Manager, Director, VP, Head of, Chief",
            "  • Job description requires 2 or more years of experience",
            "  • Role clearly targets experienced professionals",
        ],
        "junior": [
            "- User is JUNIOR LEVEL (1–3 YOE). Score 0.0 and do NOT save if ANY of:",
            "  • Job title contains: Senior, Sr., Staff, Principal, Manager, Director, VP, Head of, Chief",
            "  • Job description requires 4 or more years of experience",
        ],
        "mid": [
            "- User is MID LEVEL (3–5 YOE). Score 0.0 and do NOT save if ANY of:",
            "  • Job title contains: Staff, Principal, Director, VP, Head of, Chief",
            "  • Job description requires 7 or more years of experience",
        ],
        "senior": [
            "- User is SENIOR LEVEL (5–8 YOE). Score 0.0 and do NOT save if ANY of:",
            "  • Job title contains: Director, VP, Head of, Chief (C-suite executive roles)",
            "  • Job description requires 10 or more years of experience",
        ],
        "staff": [
            "- User is STAFF / PRINCIPAL LEVEL (8+ YOE). No hard title restrictions.",
            "  • Use judgment for VP and C-suite roles — only save if they are realistic targets.",
        ],
        "lead": [
            "- User is LEAD / MANAGER LEVEL. No hard title restrictions.",
        ],
    }

    lines += level_rules.get(experience_level, level_rules["mid"])
    lines.append(
        "The user must have a genuine, realistic chance of passing a resume screen. "
        "When in doubt about a mismatch, score 0.0."
    )
    return "\n".join(lines)


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

    async def _build_user_context(self) -> dict:
        """Return resume skills/experience and networking warmth keyed by company name."""
        ctx: dict = {"skills": [], "experience_roles": [], "networked_companies": {}}

        resume_result = await self.db.execute(
            select(Resume).where(Resume.user_id == self.user_id, Resume.is_active == True)
        )
        resume = resume_result.scalar_one_or_none()
        if resume and resume.structured_data:
            data = resume.structured_data
            ctx["skills"] = data.get("skills", [])
            ctx["experience_roles"] = [
                exp["role"] for exp in data.get("experience", []) if exp.get("role")
            ]

        contacts_result = await self.db.execute(
            select(Contact).where(Contact.user_id == self.user_id)
        )
        for contact in contacts_result.scalars().all():
            company = contact.company
            if company not in ctx["networked_companies"]:
                ctx["networked_companies"][company] = {
                    "contact_count": 0,
                    "highest_status": "discovered",
                    "has_meeting": False,
                }
            entry = ctx["networked_companies"][company]
            entry["contact_count"] += 1
            if _OUTREACH_RANK.get(contact.outreach_status, 0) > _OUTREACH_RANK.get(entry["highest_status"], 0):
                entry["highest_status"] = contact.outreach_status
            if contact.outreach_status == "meeting_scheduled":
                entry["has_meeting"] = True

        return ctx

    @staticmethod
    def _passes_experience_filter(
        job: dict, experience_level: str, employment_types: list[str]
    ) -> bool:
        """Safety-net filter: catch obvious experience mismatches the LLM may have missed."""
        title_lower = (job.get("title") or "").lower()
        job_emp_type = (job.get("employment_type") or "").lower()

        seeking_internship = "internship" in (employment_types or [])
        is_internship = "intern" in title_lower or "internship" in job_emp_type

        if seeking_internship and not is_internship:
            return False
        if not seeking_internship and is_internship:
            return False

        user_level = _LEVEL_ORDER.get(experience_level or "mid", 2)

        for keywords, min_level in _TITLE_LEVEL_GATES:
            if any(kw in title_lower for kw in keywords):
                if user_level < min_level:
                    return False

        return True

    @staticmethod
    def _passes_location_filter(job: dict, target_locations: list[str]) -> bool:
        """Enforce that the job location matches at least one of the user's target locations.

        Remote jobs pass if "remote" is in any target location. Jobs with an empty
        location field are assumed remote and pass only when the user wants remote.
        """
        if not target_locations:
            return True

        wants_remote = any("remote" in loc.lower() for loc in target_locations)
        job_location = (job.get("location") or "").lower().strip()

        # Empty location treated as remote
        if not job_location:
            return wants_remote

        if "remote" in job_location or "anywhere" in job_location:
            return wants_remote

        for loc in target_locations:
            if loc.lower() in job_location or job_location in loc.lower():
                return True

        return False

    async def _fetch_company_jobs(
        self,
        company: str,
        roles: list[str],
        locations: list[str],
        existing: set[tuple],
    ) -> list[dict]:
        """Deterministic pre-pass: search both APIs for a specific company + role."""
        results: list[dict] = []
        seen_ids: set[str] = set()
        location_str = locations[0] if locations else ""
        role = roles[0] if roles else "software engineer"

        keywords = f"{role} {company}"
        adzuna = await job_api_client.search_adzuna(keywords, location_str, max_results=10)
        jsearch = await job_api_client.search_jsearch(keywords, location_str, max_results=5)

        for item in adzuna + jsearch:
            ext_id = item.get("external_id") or item.get("url", "")
            if (ext_id, item.get("source", "")) in existing:
                continue
            if ext_id in seen_ids:
                continue
            if not companies_match(company, item.get("company", "")):
                continue
            seen_ids.add(ext_id)
            results.append(item)

        return results

    async def _execute(self, **kwargs) -> dict:
        await self._update_progress("Loading preferences")

        # Load user + preferences
        user_result = await self.db.execute(select(User).where(User.id == self.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return {"summary": "User not found"}

        prefs_result = await self.db.execute(select(UserPreferences).where(UserPreferences.user_id == self.user_id))
        prefs = prefs_result.scalar_one_or_none()
        if not prefs or not prefs.target_roles:
            return {"summary": "No target roles configured"}

        # Store on self so _save_jobs can access them for the safety-net filter
        self._experience_level = prefs.experience_level or "mid"
        self._employment_types = prefs.employment_types or ["full_time"]
        self._target_locations = prefs.target_locations or []

        # Load known external IDs to avoid duplicates
        existing_result = await self.db.execute(
            select(Job.external_id, Job.source).where(Job.user_id == self.user_id)
        )
        existing = {(row.external_id, row.source) for row in existing_result}

        ctx = await self._build_user_context()

        # Format networking signals for the prompt
        networking_lines: list[str] = []
        for company, info in ctx["networked_companies"].items():
            status = info["highest_status"]
            count = info["contact_count"]
            meeting_flag = " (had a meeting)" if info["has_meeting"] else ""
            networking_lines.append(f"  - {company}: {count} contact(s), warmest status = {status}{meeting_flag}")
        networking_section = (
            "\n".join(networking_lines)
            if networking_lines
            else "  (none yet)"
        )

        skills_line = ", ".join(ctx["skills"]) if ctx["skills"] else "not parsed"
        exp_line = ", ".join(ctx["experience_roles"]) if ctx["experience_roles"] else "not parsed"

        hard_rules = _experience_hard_rules(self._experience_level, self._employment_types)

        # --- Deterministic pre-pass: fetch jobs at each target company ---
        target_companies = prefs.target_companies or []
        pre_pass_candidates: list[dict] = []

        if target_companies:
            await self._update_progress("Searching at your target companies")
            for company in target_companies[:10]:
                hits = await self._fetch_company_jobs(
                    company, prefs.target_roles[:2], self._target_locations, existing
                )
                pre_pass_candidates.extend(hits)

        # Build candidate block for the LLM prompt
        candidates_section = ""
        if pre_pass_candidates:
            lines = []
            for i, job in enumerate(pre_pass_candidates[:50], 1):
                lines.append(
                    f"{i}. [{job.get('source','?')}] {job.get('title','')} @ {job.get('company','')} "
                    f"| {job.get('location','')} | {job.get('url','')} | id:{job.get('external_id','')}"
                )
            candidates_section = (
                "\n\nPRE-FETCHED JOBS AT YOUR TARGET COMPANIES (score these first before doing additional searches):\n"
                + "\n".join(lines)
            )

        target_companies_line = ", ".join(target_companies) if target_companies else "not specified"

        system_prompt = f"""You are the ApplyNow Job Scout. Your job is to find highly relevant job postings for a user.

User profile:
- Target roles: {prefs.target_roles}
- Target companies: {target_companies_line}
- Target locations: {self._target_locations or ["Remote"]}
- Experience level: {self._experience_level}
- Min salary: {prefs.min_salary or "not specified"}
- Employment types: {self._employment_types}
- Excluded companies: {prefs.excluded_companies or []}

Resume signals:
- Skills: {skills_line}
- Past experience roles: {exp_line}

Networking warm signals (companies where the user already has contacts):
{networking_section}

{hard_rules}

Scoring instructions:
1. Score the pre-fetched jobs first (if any). Then search for additional jobs using both Adzuna and JSearch.
   Prioritize roles at the user's target companies. Use resume skills to enrich search keywords.
2. Base score (0.0–1.0): how well the role and requirements match the user's profile. Be strict — 0.85+ means excellent match.
3. Networking boost: add +0.10 if the job's company appears in the warm signals with status "sent" or "replied".
   Add +0.15 if status is "meeting_scheduled". Cap final score at 1.0.
4. Skill match boost: add +0.05 if the job description explicitly mentions 2+ of the user's resume skills.
5. Only include jobs with final score >= 0.6.
6. Exclude jobs from excluded companies.
7. In match_reasoning, always mention if a networking or skill boost was applied.
8. Call save_scored_jobs once with all qualified results.
9. Do not save jobs with these (external_id, source) pairs as they already exist: {list(existing)[:50]}
{candidates_section}"""

        initial_message = (
            f"Search for new job postings for these roles: {prefs.target_roles}. "
            f"Locations: {self._target_locations or ['Remote']}. "
            f"Target companies: {target_companies_line}. "
            f"Find the best matches and save them."
        )

        await self._update_progress("Searching for jobs by role")
        await self.run_tool_loop(system_prompt, initial_message, TOOLS)

        # Return stats (set by dispatch_tool)
        jobs_saved = getattr(self, "_jobs_saved", 0)
        return {"summary": f"Saved {jobs_saved} new jobs", "jobs_found": jobs_saved}

    async def dispatch_tool(self, name: str, input_data: dict) -> Any:
        if name == "search_jobs_adzuna":
            await self._update_progress(f"Searching Adzuna for: {input_data.get('keywords', '')[:60]}")
            results = await job_api_client.search_adzuna(
                input_data["keywords"],
                input_data.get("location", ""),
                input_data.get("max_results", 20),
            )
            return json.dumps(results)

        if name == "search_jobs_jsearch":
            await self._update_progress(f"Searching JSearch for: {input_data.get('query', '')[:60]}")
            results = await job_api_client.search_jsearch(
                input_data["query"],
                input_data.get("location", ""),
                input_data.get("max_results", 10),
            )
            return json.dumps(results)

        if name == "save_scored_jobs":
            await self._update_progress("Saving matched jobs")
            return await self._save_jobs(input_data["jobs"])

        return f"Unknown tool: {name}"

    async def _save_jobs(self, jobs_data: list[dict]) -> str:
        saved = 0
        new_jobs = []

        experience_level = getattr(self, "_experience_level", "mid")
        employment_types = getattr(self, "_employment_types", ["full_time"])
        target_locations = getattr(self, "_target_locations", [])

        for item in jobs_data:
            # Hard experience-level safety net (catches LLM oversights)
            if not self._passes_experience_filter(item, experience_level, employment_types):
                continue

            # Strict location filter
            if not self._passes_location_filter(item, target_locations):
                continue

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
                sent = await send_email(user.email, subject, html)
                if sent:
                    for job in new_jobs:
                        job.email_sent = True
                    await self.db.commit()

        return f"Saved {saved} jobs. Digest email sent with {len(new_jobs)} jobs."
