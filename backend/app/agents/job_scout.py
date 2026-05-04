import json
import logging
import re

from sqlalchemy import select

from app.agents.base import BaseAgent
from app.models.contact import Contact
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User, UserPreferences
from app.services import job_api_client, quota
from app.services.company_match import companies_match
from app.services.job_api_client import validate_urls
from app.services.email_service import new_jobs_digest_email, send_email
from app.config import settings

logger = logging.getLogger(__name__)

_OUTREACH_RANK = {
    "discovered": 0,
    "message_drafted": 1,
    "sent": 2,
    "replied": 3,
    "meeting_scheduled": 4,
}

_TITLE_LEVEL_GATES = [
    # min_level the user must meet to NOT be filtered out
    ({"director", "vp", " vice president", "head of", "chief", "cto", "ceo", "cfo"}, 5),
    ({"staff ", "principal ", "fellow ", "architect", "manager", "mgr"}, 4),
    ({"senior ", "sr. ", " sr ", "sr/staff", "lead "}, 3),
]

_LEVEL_ORDER = {"entry": 0, "junior": 1, "mid": 2, "senior": 3, "staff": 4, "lead": 4}

# Catches "5+ years of experience", "5 yrs experience", "3-5 years experience",
# and "5+ years of <adjective(s)> experience" (e.g. "5+ years of software engineering experience").
_YOE_PATTERN = re.compile(
    r"(\d+)\s*\+?\s*(?:to\s*\d+\s*|-\s*\d+\s*)?(?:years?|yrs?)(?:\s+\w+){0,5}?\s+(?:experience|exp)\b",
    re.IGNORECASE,
)
# Catches "minimum 3 years", "at least 5 years", "requires 4+ years"
_YOE_MIN_PATTERN = re.compile(
    r"(?:minimum|at\s+least|requires?|min\.?)\s+(?:of\s+)?(\d+)\s*\+?\s*(?:years?|yrs?)",
    re.IGNORECASE,
)

# Strict cap on required YOE the user can accept. A posting demanding >= this
# many years is rejected. Tracks the level's typical YOE upper bound + 1.
_LEVEL_MAX_YOE = {"entry": 2, "junior": 4, "mid": 6, "senior": 10, "staff": 99, "lead": 99}


def _experience_hard_rules(experience_level: str, employment_types: list[str]) -> str:
    seeking_internship = "internship" in (employment_types or [])
    lines = ["HARD EXPERIENCE MATCHING RULES (absolute, override everything):"]

    if seeking_internship:
        lines += [
            "- User seeks INTERNSHIPS only. Score 0 for any non-internship posting.",
        ]
    else:
        lines += [
            "- User is NOT seeking internships. Score 0 for any internship listing.",
        ]

    level_rules = {
        "entry": [
            "- ENTRY LEVEL (0–1 YOE). Score 0 if title contains Senior/Staff/Principal/Lead/Manager/Director/VP/Chief OR requires 2+ YOE.",
        ],
        "junior": [
            "- JUNIOR LEVEL (1–3 YOE). Score 0 if title contains Senior/Staff/Principal/Manager/Director/VP/Chief OR requires 4+ YOE.",
        ],
        "mid": [
            "- MID LEVEL (3–5 YOE). Score 0 if title contains Staff/Principal/Director/VP/Chief OR requires 7+ YOE.",
        ],
        "senior": [
            "- SENIOR LEVEL (5–8 YOE). Score 0 if title contains Director/VP/Chief OR requires 10+ YOE.",
        ],
        "staff": ["- STAFF/PRINCIPAL (8+ YOE). No hard title restrictions."],
        "lead": ["- LEAD/MANAGER. No hard title restrictions."],
    }
    lines += level_rules.get(experience_level, level_rules["mid"])
    return "\n".join(lines)


class JobScoutAgent(BaseAgent):
    agent_type = "job_scout"

    async def _build_user_context(self) -> dict:
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
    def _passes_experience_filter(job: dict, experience_level: str, employment_types: list[str]) -> bool:
        title_lower = (job.get("title") or "").lower()
        # pad with spaces so " senior " / " sr " word-boundary matches work for prefix titles
        title_padded = f" {title_lower} "
        job_emp_type = (job.get("employment_type") or "").lower()
        description = (job.get("description") or "").lower()

        seeking_internship = "internship" in (employment_types or [])
        is_internship = "intern" in title_lower or "internship" in job_emp_type

        if seeking_internship and not is_internship:
            return False
        if not seeking_internship and is_internship:
            return False

        user_level = _LEVEL_ORDER.get(experience_level or "mid", 2)
        for keywords, min_level in _TITLE_LEVEL_GATES:
            if any(kw in title_padded for kw in keywords):
                if user_level < min_level:
                    return False

        # YOE check from description: drop if any required YOE >= user's max.
        # >= matters: a job saying "2+ years" requires 2 or more, which an
        # entry-level (0–1 YOE) candidate doesn't have.
        max_yoe = _LEVEL_MAX_YOE.get(experience_level or "mid", 6)
        for pattern in (_YOE_PATTERN, _YOE_MIN_PATTERN):
            for m in pattern.finditer(description):
                try:
                    required = int(m.group(1))
                except ValueError:
                    continue
                if required >= max_yoe:
                    return False
        return True

    @staticmethod
    def _passes_location_filter(job: dict, target_locations: list[str]) -> bool:
        if not target_locations:
            return True
        # Remote preference: pass all jobs, LLM scores remote eligibility
        if any("remote" in loc.lower() for loc in target_locations):
            return True
        job_location = (job.get("location") or "").lower().strip()
        if not job_location:
            return True  # unknown location — let LLM decide
        if "remote" in job_location or "anywhere" in job_location:
            return False  # explicitly remote but user wants on-site
        for loc in target_locations:
            if loc.lower() in job_location or job_location in loc.lower():
                return True
        return False

    async def _score_candidates(
        self,
        candidates: list[dict],
        prefs: UserPreferences,
        ctx: dict,
        experience_level: str,
        employment_types: list[str],
    ) -> list[dict]:
        """Single LLM call to score all candidates. Returns candidates with score >= 0.6."""
        if not candidates:
            return []

        # Prioritise target-company hits, then cap at 40
        target_companies_lower = {c.lower() for c in (prefs.target_companies or [])}
        priority = [c for c in candidates if (c.get("company") or "").lower() in target_companies_lower]
        rest = [c for c in candidates if c not in priority]
        ordered = (priority + rest)[:40]

        skills_line = ", ".join(ctx["skills"]) if ctx["skills"] else "not parsed"
        exp_line = ", ".join(ctx["experience_roles"]) if ctx["experience_roles"] else "not parsed"
        hard_rules = _experience_hard_rules(experience_level, employment_types)
        target_companies_line = ", ".join(prefs.target_companies or []) or "not specified"

        candidate_lines = []
        for i, job in enumerate(ordered, 1):
            desc_snippet = (job.get("description") or "")[:300].replace("\n", " ")
            candidate_lines.append(
                f"{i}. {job.get('title', '?')} @ {job.get('company', '?')} "
                f"| {job.get('location', '') or 'location unknown'} "
                f"| {desc_snippet}"
            )

        prompt = f"""Score each job posting for this candidate. Return ONLY a JSON array — no text, no markdown.

Candidate profile:
- Target roles: {prefs.target_roles}
- Target companies: {target_companies_line}
- Target locations: {prefs.target_locations or ["Remote"]}
- Experience level: {experience_level}
- Min salary: {prefs.min_salary or "not specified"}
- Employment types: {employment_types}
- Excluded companies: {prefs.excluded_companies or []}
- Resume skills: {skills_line}
- Past experience roles: {exp_line}

{hard_rules}

ADDITIONAL HARD RULES (apply BEFORE scoring):
- If the description mentions "X+ years" / "minimum X years" / "at least X years" of experience and the
  candidate doesn't meet X, score 0. Required years the candidate CANNOT meet:
  entry: 2+ years required → 0. junior: 4+ years required → 0. mid: 6+ years required → 0.
  senior: 10+ years required → 0.
- If the title strongly implies a higher level than the candidate (Staff, Principal, Director, VP, Manager,
  Architect for non-staff users), score 0.
- Do NOT inflate scores for adjacent-but-wrong roles. A "Sales Engineer" listing is not a match for a
  "Software Engineer" candidate.

Scoring:
- 0.9–1.0: Perfect match (right role, right level, target company or strong fit)
- 0.75–0.89: Strong match — clearly within YOE band, role aligns with target roles
- 0.65–0.74: Decent match, worth applying
- Below 0.65: Skip (wrong level, wrong role family, or excluded company)

Job postings to score:
{chr(10).join(candidate_lines)}

Return exactly this JSON format (one entry per posting):
[{{"index": 1, "score": 0.85, "reasoning": "brief reason"}}, ...]"""

        try:
            raw = await self.complete(prompt, model="claude-haiku-4-5-20251001", max_tokens=2000)
            # Strip any markdown code fences if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                raw = raw.rsplit("```", 1)[0]
            scores_data: list[dict] = json.loads(raw)
        except Exception as exc:
            logger.warning("Job scoring failed: %s", exc)
            return []

        # Build index → score map
        score_map = {item["index"]: item for item in scores_data if isinstance(item, dict)}

        # Apply networking + skill boosts, filter, merge
        networked = ctx["networked_companies"]
        skills_set = {s.lower() for s in ctx["skills"]}

        results = []
        for i, job in enumerate(ordered, 1):
            entry = score_map.get(i)
            if not entry:
                continue
            base_score = float(entry.get("score", 0))
            reasoning = entry.get("reasoning", "")

            if base_score <= 0:
                continue

            # Networking boost
            company = job.get("company", "")
            net_info = next(
                (v for k, v in networked.items() if companies_match(k, company)),
                None,
            )
            boost = 0.0
            if net_info:
                status = net_info["highest_status"]
                if status == "meeting_scheduled":
                    boost = 0.15
                    reasoning += f" | Networking boost +0.15: meeting at {company}"
                elif status in ("sent", "replied"):
                    boost = 0.10
                    reasoning += f" | Networking boost +0.10: contact at {company}"

            # Skill boost
            desc_lower = (job.get("description") or "").lower()
            matched_skills = [s for s in skills_set if s in desc_lower]
            if len(matched_skills) >= 2:
                boost += 0.05
                reasoning += f" | Skill boost +0.05: {', '.join(list(matched_skills)[:3])}"

            final_score = min(1.0, base_score + boost)
            if final_score < 0.65:
                continue

            results.append({**job, "match_score": final_score, "match_reasoning": reasoning})

        return results

    async def _execute(self, **kwargs) -> dict:
        await self._update_progress("Loading preferences")

        user_result = await self.db.execute(select(User).where(User.id == self.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return {"summary": "User not found"}

        prefs_result = await self.db.execute(
            select(UserPreferences).where(UserPreferences.user_id == self.user_id)
        )
        prefs = prefs_result.scalar_one_or_none()
        if not prefs or not prefs.target_roles:
            return {"summary": "No target roles configured"}

        experience_level = prefs.experience_level or "mid"
        employment_types = prefs.employment_types or ["full_time"]
        target_locations = prefs.target_locations or []
        target_companies = prefs.target_companies or []
        target_roles = prefs.target_roles

        self._experience_level = experience_level
        self._employment_types = employment_types
        self._target_locations = target_locations

        # Load existing job URLs to deduplicate
        existing_result = await self.db.execute(
            select(Job.external_id).where(Job.user_id == self.user_id)
        )
        existing_urls: set[str] = {row.external_id for row in existing_result if row.external_id}

        ctx = await self._build_user_context()

        # Location hint for search queries (skip "Remote" as a string)
        real_locations = [loc for loc in target_locations if "remote" not in loc.lower()]
        location_hint = real_locations[0] if real_locations else ""

        candidates: list[dict] = []

        # ── Track A: Exa per-company ────────────────────────────────────────
        if target_companies:
            await self._update_progress(f"Searching Exa at {len(target_companies[:10])} target companies")
            for company in target_companies[:10]:
                for role in target_roles[:2]:
                    query = f"{role} job opening at {company}"
                    if location_hint:
                        query += f" {location_hint}"
                    hits = await job_api_client.search_jobs_exa(query, max_results=5, company_hint=company)
                    candidates.extend(hits)

        # ── Track B: Exa general role search ───────────────────────────────
        await self._update_progress("Searching Exa for role matches")
        for role in target_roles[:3]:
            query = f"{role} job opening"
            if location_hint:
                query += f" {location_hint}"
            hits = await job_api_client.search_jobs_exa(query, max_results=8)
            candidates.extend(hits)

        # ── Track C: JSearch (structured salary/type data) ──────────────────
        await self._update_progress("Searching JSearch")
        for role in target_roles[:2]:
            query = f"{role} {location_hint}".strip()
            hits = await job_api_client.search_jsearch(query, max_results=10)
            candidates.extend(hits)

        # ── Deduplicate by URL ──────────────────────────────────────────────
        seen: set[str] = set(existing_urls)
        unique: list[dict] = []
        for c in candidates:
            url = c.get("url", "")
            if url and url not in seen:
                seen.add(url)
                # Filter out excluded companies early
                if prefs.excluded_companies:
                    company = (c.get("company") or "").lower()
                    if any(ex.lower() in company for ex in prefs.excluded_companies):
                        continue
                unique.append(c)

        logger.info("Job Scout: %d unique candidates after dedup", len(unique))

        if not unique:
            return {"summary": "No new job postings found", "jobs_found": 0}

        # ── Validate URLs (drop dead links) ─────────────────────────────────
        await self._update_progress(f"Validating {len(unique)} URLs")
        urls_to_check = [c["url"] for c in unique if c.get("url")]
        good_urls = await validate_urls(urls_to_check)
        unique = [c for c in unique if c.get("url") in good_urls]
        logger.info("Job Scout: %d candidates after URL validation", len(unique))

        if not unique:
            return {"summary": "No reachable job postings found", "jobs_found": 0}

        # ── Score ───────────────────────────────────────────────────────────
        await self._update_progress(f"Scoring {len(unique)} candidates")
        scored = await self._score_candidates(unique, prefs, ctx, experience_level, employment_types)

        logger.info("Job Scout: %d candidates scored >= 0.6", len(scored))

        # ── Save ────────────────────────────────────────────────────────────
        await self._update_progress("Saving matched jobs")
        saved_count = await self._save_jobs(scored)

        return {"summary": f"Saved {saved_count} new jobs", "jobs_found": saved_count}

    async def _save_jobs(self, jobs_data: list[dict]) -> int:
        saved = 0
        new_jobs = []

        experience_level = getattr(self, "_experience_level", "mid")
        employment_types = getattr(self, "_employment_types", ["full_time"])
        target_locations = getattr(self, "_target_locations", [])

        for item in jobs_data:
            if not self._passes_experience_filter(item, experience_level, employment_types):
                continue
            if not self._passes_location_filter(item, target_locations):
                continue
            if not await quota.can_surface_job(self.db, self.user_id):
                break

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

        if saved > 0:
            user_result = await self.db.execute(select(User).where(User.id == self.user_id))
            user = user_result.scalar_one_or_none()
            if user:
                jobs_payload = sorted(
                    [
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
                    ],
                    key=lambda j: j["match_score"],
                    reverse=True,
                )
                html = new_jobs_digest_email(jobs_payload, settings.frontend_url)
                subject = f"{saved} new job{'s' if saved != 1 else ''} found — apply early"
                sent = await send_email(user.email, subject, html)
                if sent:
                    for job in new_jobs:
                        job.email_sent = True
                    await self.db.commit()

        return saved
