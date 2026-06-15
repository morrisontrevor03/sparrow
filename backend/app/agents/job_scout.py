import asyncio
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

_LEVEL_ORDER = {"new_grad": 0, "entry": 0, "junior": 1, "mid": 2, "senior": 3, "staff": 4, "lead": 4}

# Catches YOE phrases — captures lower bound (group 1) AND optional upper bound (group 2)
# so we can reject ranges like "1-5 years" that pass a lower-only check but really mean senior.
# Examples:
#   "5+ years of experience" → (5, None)
#   "3-5 years experience"   → (3, 5)
#   "3 to 5 years of experience" → (3, 5)
#   "5+ years of software engineering experience" → (5, None)
_YOE_PATTERNS = [
    re.compile(
        r"(\d+)\s*\+?\s*(?:(?:to|-|–|—)\s*(\d+)\s*)?(?:years?|yrs?)(?:\s+\w+){0,5}?\s+(?:of\s+)?(?:experience|exp)\b",
        re.IGNORECASE,
    ),
    # "minimum 3 years", "at least 5 years", "requires 4+ years", "over 5 years"
    re.compile(
        r"(?:minimum|at\s+least|requires?|min\.?|over)\s+(?:of\s+)?(\d+)\s*\+?\s*(?:(?:to|-|–|—)\s*(\d+)\s*)?(?:years?|yrs?)",
        re.IGNORECASE,
    ),
    # "5+ YOE", "3-5 YOE"
    re.compile(
        r"(\d+)\s*\+?\s*(?:(?:to|-|–|—)\s*(\d+)\s*)?\s*yoe\b",
        re.IGNORECASE,
    ),
]

# Reject the match when the YoE phrase is followed by non-job-requirement context
# like "of coursework", "ago", or "from now". These cause false-positive rejections
# (e.g. "3 years of coursework" being read as a YoE requirement).
_YOE_FALSE_POSITIVE_CONTEXT = re.compile(
    r"\b(coursework|studies|study|school|college|university|degree program|"
    r"ago|from\s+now|of\s+age|old)\b",
    re.IGNORECASE,
)

# Maximum acceptable LOWER bound (the job's minimum required years).
# A posting demanding >= this many years is rejected.
_LEVEL_MAX_LOWER = {
    "new_grad": 1, "entry": 2, "junior": 4, "mid": 6, "senior": 10, "staff": 99, "lead": 99,
}
# Maximum acceptable UPPER bound (the "ideally up to" end of a range).
# Catches deceptive ranges like "1-5 years" where the lower bound passes but the
# role is really aimed higher. > this → reject.
_LEVEL_MAX_UPPER = {
    "new_grad": 2, "entry": 3, "junior": 6, "mid": 8, "senior": 15, "staff": 99, "lead": 99,
}

# For new_grad, reject titles that imply any level above I/Associate.
_NEW_GRAD_TITLE_BLOCK = (
    " ii ", " iii ", " iv ", " v ", " 2 ", " 3 ", " 4 ", " 5 ",
    "experienced", "mid-level", "mid level", " mid ",
)


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
        "new_grad": [
            "- NEW GRAD (0 YOE, currently a student or just graduated). Score 0 if ANY of these are true:",
            "    * title contains Senior/Sr/Staff/Principal/Lead/Manager/Director/VP/Chief/Architect/'II'/'III'/'IV'/'2'/'3'/'4'/Experienced/Mid",
            "    * description requires 1+ YOE (any wording: '1+ years', 'minimum 1 year', 'at least 1 year', '1 YOE')",
            "    * description mentions a year range whose UPPER bound is > 2 (e.g. '0-3 years', '1-5 years' are NOT new-grad-friendly)",
            "    * description requires a graduate degree, PhD, or specific years of post-degree experience",
            "  Acceptable phrasing: '0 years', '0-1 years', '0-2 years', 'recent graduate', 'new grad', 'no experience required', 'entry-level'.",
        ],
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

        # New-grad-only title block: levels like "Engineer II", "SWE 3", "Mid Engineer"
        # all imply someone with prior experience.
        if experience_level == "new_grad":
            if any(kw in title_padded for kw in _NEW_GRAD_TITLE_BLOCK):
                return False

        # YOE check from description. Reject if EITHER bound exceeds the user's caps:
        #   - lower bound >= max_lower → job's minimum exceeds what user has
        #   - upper bound  >  max_upper → range targets someone above user's level
        # The upper-bound check catches deceptive ranges like "1-5 years" where the
        # lower bound passes but the role is really aimed at a senior candidate.
        max_lower = _LEVEL_MAX_LOWER.get(experience_level or "mid", 6)
        max_upper = _LEVEL_MAX_UPPER.get(experience_level or "mid", 8)
        for pattern in _YOE_PATTERNS:
            for m in pattern.finditer(description):
                # Skip false-positives: "3 years of coursework", "5 years ago", etc.
                # Look at the next ~30 chars after the match for disqualifying context.
                tail = description[m.end() : m.end() + 30]
                if _YOE_FALSE_POSITIVE_CONTEXT.search(tail):
                    continue
                try:
                    lower = int(m.group(1))
                except (ValueError, IndexError, TypeError):
                    continue
                if lower >= max_lower:
                    return False
                upper_str = m.group(2) if m.lastindex and m.lastindex >= 2 else None
                if upper_str:
                    try:
                        upper = int(upper_str)
                    except ValueError:
                        continue
                    if upper > max_upper:
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

    async def _score_chunk(
        self,
        chunk: list[dict],
        prefs: UserPreferences,
        ctx: dict,
        experience_level: str,
        employment_types: list[str],
    ) -> list[dict]:
        """Score a single chunk of candidates. Returns those with score >= 0.65 after boosts.

        Scoring runs one chunk at a time so callers can save matches incrementally
        and surface the first results within seconds rather than after the whole
        batch finishes.
        """
        if not chunk:
            return []

        skills_line = ", ".join(ctx["skills"]) if ctx["skills"] else "not parsed"
        exp_line = ", ".join(ctx["experience_roles"]) if ctx["experience_roles"] else "not parsed"
        hard_rules = _experience_hard_rules(experience_level, employment_types)
        target_companies_line = ", ".join(prefs.target_companies or []) or "not specified"

        candidate_lines = []
        for i, job in enumerate(chunk, 1):
            # Feed the model a substantial slice of the description (not just 300
            # chars) — relevance was the weakest part of the funnel and the YOE /
            # level signals it needs usually live deeper in the posting.
            desc_snippet = (job.get("description") or "")[:1500].replace("\n", " ")
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
- If the description mentions "X+ years" / "minimum X years" / "at least X years" / "X-Y years" of
  experience and the candidate doesn't meet X (or the range upper bound Y exceeds the candidate's level),
  score 0. Required years the candidate CANNOT meet:
  new_grad: 1+ years required OR range upper > 2 → 0 (e.g. "1-5 years" is NOT a new-grad role).
  entry: 2+ years required → 0. junior: 4+ years required → 0. mid: 6+ years required → 0.
  senior: 10+ years required → 0.
- If the title strongly implies a higher level than the candidate (Staff, Principal, Director, VP, Manager,
  Architect for non-staff users; II/III/IV/2/3/4/Mid/Experienced for new_grad users), score 0.
- For new_grad: only score > 0 when the listing explicitly invites recent graduates, students, or 0-YOE
  applicants. If the listing is silent on YOE but the title says "Software Engineer" (no level marker),
  that is acceptable — but anything implying prior experience is a 0.
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
            # Sonnet over Haiku for the relevance call — level/role nuance from a
            # description is exactly where the cheaper model was producing the
            # off-target matches users complained about.
            raw = await self.complete(prompt, model="claude-sonnet-4-6", max_tokens=1500)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                raw = raw.rsplit("```", 1)[0]
            scores_data: list[dict] = json.loads(raw)
        except Exception as exc:
            logger.warning("Job scoring chunk failed: %s", exc)
            return []

        score_map: dict[int, dict] = {}
        for item in scores_data:
            if not isinstance(item, dict):
                continue
            local_i = item.get("index")
            if not isinstance(local_i, int) or local_i < 1 or local_i > len(chunk):
                continue
            score_map[local_i] = item

        # Apply networking + skill boosts, filter
        networked = ctx["networked_companies"]
        skills_set = {s.lower() for s in ctx["skills"]}

        results = []
        for i, job in enumerate(chunk, 1):
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

            # Unknown-company penalty: Exa general search and the Adzuna/JSearch
            # fallbacks emit company="Unknown" when no employer could be resolved.
            # Rank these down hard so they don't crowd out verified listings.
            if not company or company.strip().lower() == "unknown":
                boost -= 0.15
                reasoning += " | Unverified employer −0.15"

            final_score = min(1.0, base_score + boost)
            if final_score < 0.65:
                continue

            results.append({**job, "match_score": final_score, "match_reasoning": reasoning})

        return results

    async def _score_candidates(
        self,
        candidates: list[dict],
        prefs: UserPreferences,
        ctx: dict,
        experience_level: str,
        employment_types: list[str],
    ) -> list[dict]:
        """Order, chunk, and score a full candidate set in one shot.

        `_execute` scores chunk-by-chunk so it can save incrementally; this method
        keeps the same ordering + chunking but returns every scored match at once.
        It's the entry point the eval harness drives, so production and eval share
        the exact per-chunk scoring path via `_score_chunk`.
        """
        if not candidates:
            return []

        target_companies_lower = {c.lower() for c in (prefs.target_companies or [])}
        priority = [c for c in candidates if (c.get("company") or "").lower() in target_companies_lower]
        rest = [c for c in candidates if c not in priority]
        ordered = (priority + rest)[:100]

        CHUNK_SIZE = 25
        results: list[dict] = []
        for chunk_start in range(0, len(ordered), CHUNK_SIZE):
            chunk = ordered[chunk_start : chunk_start + CHUNK_SIZE]
            results.extend(
                await self._score_chunk(chunk, prefs, ctx, experience_level, employment_types)
            )
        return results

    async def _gather_searches(self, coros: list, limit: int = 8) -> list[dict]:
        """Run search coroutines concurrently (bounded) and flatten the results.

        The four source tracks used to run strictly sequentially — up to ~80
        awaited calls one after another, which is the main reason first results
        took minutes. Fanning them out concurrently (capped to stay friendly with
        per-source rate limits) collapses that to roughly the slowest single call.
        Each source already swallows its own errors; we guard here too so one bad
        query can't sink the whole batch.
        """
        sem = asyncio.Semaphore(limit)

        async def _run(coro):
            async with sem:
                try:
                    return await coro
                except Exception as exc:
                    logger.warning("Job search task failed: %s", exc)
                    return []

        results = await asyncio.gather(*(_run(c) for c in coros))
        flat: list[dict] = []
        for sub in results:
            flat.extend(sub or [])
        return flat

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

        # Location hints — query each non-remote location separately.
        # Cap at 2 locations to bound API fan-out; "Remote" is handled by LLM scoring.
        real_locations = [loc for loc in target_locations if "remote" not in loc.lower()]
        location_hints = real_locations[:2] if real_locations else [""]
        primary_location = location_hints[0]

        # ── Build the full search fan-out, then run it concurrently ─────────
        # All four tracks are independent network calls, so we queue every query
        # up front and dispatch them together rather than awaiting one at a time.
        search_coros: list = []

        # Track A: Exa per-company
        if target_companies:
            for company in target_companies[:10]:
                for role in target_roles[:5]:
                    query = f"{role} job opening at {company}"
                    if primary_location:
                        query += f" {primary_location}"
                    search_coros.append(
                        job_api_client.search_jobs_exa(query, max_results=5, company_hint=company)
                    )

        # Track B: Exa general role search
        for role in target_roles[:5]:
            for loc in location_hints:
                query = f"{role} job opening"
                if loc:
                    query += f" {loc}"
                search_coros.append(job_api_client.search_jobs_exa(query, max_results=8))

        # Track C: JSearch (structured salary/type data)
        for role in target_roles[:5]:
            for loc in location_hints:
                query = f"{role} {loc}".strip()
                search_coros.append(job_api_client.search_jsearch(query, max_results=10))

        # Track D: Adzuna (US-wide aggregator)
        for role in target_roles[:5]:
            for loc in location_hints:
                search_coros.append(
                    job_api_client.search_adzuna(role, location=loc, max_results=15)
                )

        await self._update_progress(f"Searching {len(search_coros)} queries across job sources")
        candidates = await self._gather_searches(search_coros, limit=8)

        # ── Deduplicate by URL ──────────────────────────────────────────────
        seen: set[str] = set(existing_urls)
        unique: list[dict] = []
        for c in candidates:
            url = c.get("url", "")
            if url and url not in seen:
                seen.add(url)
                # Filter out excluded companies early (normalized match — avoid
                # substring false-positives like "Apple" matching "Pineapple Labs")
                if prefs.excluded_companies:
                    company = c.get("company") or ""
                    if any(companies_match(ex, company) for ex in prefs.excluded_companies):
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

        # ── Prioritise target-company hits, then cap at 100 ─────────────────
        target_companies_lower = {c.lower() for c in (prefs.target_companies or [])}
        priority = [c for c in unique if (c.get("company") or "").lower() in target_companies_lower]
        rest = [c for c in unique if c not in priority]
        ordered = (priority + rest)[:100]

        # ── Score + save in waves ───────────────────────────────────────────
        # Scoring the best (target-company) candidates first and persisting after
        # each chunk means matches show up in the dashboard within seconds instead
        # of only after the entire batch finishes.
        CHUNK_SIZE = 25
        total_saved = 0
        all_new_jobs: list[Job] = []

        for chunk_start in range(0, len(ordered), CHUNK_SIZE):
            if not await quota.can_surface_job(self.db, self.user_id):
                break
            chunk = ordered[chunk_start : chunk_start + CHUNK_SIZE]
            await self._update_progress(
                f"Scoring matches ({min(chunk_start + CHUNK_SIZE, len(ordered))}/{len(ordered)})"
            )
            scored = await self._score_chunk(chunk, prefs, ctx, experience_level, employment_types)
            new_jobs = await self._save_job_batch(scored)
            all_new_jobs.extend(new_jobs)
            total_saved += len(new_jobs)
            if total_saved:
                await self._update_progress(
                    f"Found {total_saved} match{'es' if total_saved != 1 else ''} so far"
                )

        logger.info("Job Scout: %d candidates saved", total_saved)

        # ── Digest email (single send across all waves) ─────────────────────
        await self._send_digest(all_new_jobs)

        return {"summary": f"Saved {total_saved} new jobs", "jobs_found": total_saved}

    async def _save_job_batch(self, jobs_data: list[dict]) -> list["Job"]:
        """Persist one wave of scored jobs and return the newly created rows.

        Does not send email — the digest is sent once at the end of the run by
        `_send_digest` so multiple waves don't trigger multiple emails.
        """
        new_jobs: list[Job] = []

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
            new_jobs.append(job)

        await self.db.commit()
        return new_jobs

    async def _send_digest(self, new_jobs: list["Job"]) -> None:
        """Email the user a digest of the run's matches.

        Gate lowered from 0.85 → 0.70: the old bar meant a user whose best match
        was, say, 0.80 got complete silence — no email, no signal the scout had
        run at all. 0.70 ("decent match, worth applying") still keeps lukewarm
        noise out while making sure a productive run is never invisible.
        """
        if not new_jobs:
            return

        top_score = max((j.match_score or 0 for j in new_jobs), default=0)
        if top_score < 0.70:
            return

        user_result = await self.db.execute(select(User).where(User.id == self.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return

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
        saved = len(new_jobs)
        subject = f"{saved} new job{'s' if saved != 1 else ''} found — apply early"
        sent = await send_email(user.email, subject, html)
        if sent:
            for job in new_jobs:
                job.email_sent = True
            await self.db.commit()
