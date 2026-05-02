import asyncio
import logging

import httpx
from sqlalchemy import select

from app.agents.base import BaseAgent
from app.config import settings
from app.models.contact import Contact
from app.models.user import User, UserPreferences
from app.services import quota

logger = logging.getLogger(__name__)

TARGET_COMPANY_COUNT = 25
JUNIOR_PREFIXES = ["Junior", "Associate", "Entry Level", "New Grad"]
FOUNDER_TITLES = ["Founder", "Co-Founder"]
EXA_SEARCH_URL = "https://api.exa.ai/search"
DISCOVERY_MODEL = "claude-haiku-4-5-20251001"
MAX_DISCOVERED_COMPANIES = 20

EXCLUDE_KEYWORDS = {
    "vp", "vice president", "director", "chief", "ceo", "cto", "coo", "cfo",
    "founder", "owner", "partner", "head of",
}
FOUNDER_KEYWORDS = {"founder", "co-founder", "cofounder"}
RECRUITER_KEYWORDS = {"recruiter", "talent", "sourcer", "recruiting", "staffing"}
JUNIOR_KEYWORDS = {"junior", "associate", "entry level", "new grad", "early career"}
MANAGER_KEYWORDS = {"manager", "lead", "principal", "staff"}


def _is_yc_company(company: str) -> bool:
    return "(yc " in company.lower()


def _clean_company_name(company: str) -> str:
    """Strip any trailing parenthetical (e.g. '(YC S26)') for company matching."""
    import re
    return re.sub(r"\s*\([^)]*\)\s*$", "", company).strip()


def _query_company_name(company: str) -> str:
    """Format a company name for Exa search queries.

    YC companies keep their batch tag (parens removed) so the query is
    anchored to the right startup — 'Harbor YC S26' not just 'Harbor'.
    Other companies have any trailing parenthetical stripped.
    """
    import re
    m = re.search(r"\(YC ([^)]+)\)", company, re.IGNORECASE)
    if m:
        base = _clean_company_name(company)
        return f"{base} YC {m.group(1)}"
    return _clean_company_name(company)


def _companies_match(target: str, found: str) -> bool:
    # Compare against the clean name so '(YC S26)' doesn't break matching.
    t = _clean_company_name(target).lower().strip()
    f = found.lower().strip()
    return t in f or f in t


def _extract_current_company(text: str) -> str:
    """
    Pull the employer from ' at Company', ' @ Company', or '@Company' patterns.
    Exa titles use '@' instead of 'at', so we must handle both.
    """
    # Try each marker in preference order; pick the earliest occurrence.
    candidates = []
    for marker, skip in [(" at ", 4), (" @ ", 3), ("@", 1)]:
        idx = text.lower().find(marker.lower()) if marker != "@" else text.find(marker)
        if idx != -1:
            candidates.append((idx, skip))

    if not candidates:
        return ""

    idx, skip = min(candidates, key=lambda x: x[0])
    rest = text[idx + skip:]
    for delim in (" | ", " · ", "·", " - ", ",", "\n"):
        pos = rest.find(delim)
        if pos != -1:
            rest = rest[:pos]
    return rest.strip()


def _score_title(title: str) -> float:
    t = title.lower()
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return 0.0
    if any(k in t for k in RECRUITER_KEYWORDS):
        return 0.3
    if any(k in t for k in JUNIOR_KEYWORDS):
        return 0.85
    if any(k in t for k in MANAGER_KEYWORDS):
        return 0.65
    return 0.75


def _extract_seniority(title: str) -> str:
    t = title.lower()
    if any(k in t for k in FOUNDER_KEYWORDS):
        return "executive"
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return "executive"
    if any(k in t for k in MANAGER_KEYWORDS):
        return "manager"
    if any(k in t for k in JUNIOR_KEYWORDS):
        return "entry"
    if any(k in t for k in RECRUITER_KEYWORDS):
        return "recruiting"
    return "mid"


_DEPT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("engineering", ["engineer", "developer", "swe", "backend", "frontend", "fullstack", "devops", "infra", "data", "ml", "ai", "platform"]),
    ("product", ["product manager", "pm ", "product lead"]),
    ("design", ["designer", "ux", "ui ", "creative"]),
    ("sales", ["sales", "account executive", "ae ", "business development", "bdr", "sdr"]),
    ("marketing", ["marketing", "growth", "content", "seo", "brand"]),
    ("recruiting", ["recruiter", "talent", "sourcer", "staffing"]),
    ("finance", ["finance", "accounting", "controller", "cfo", "analyst"]),
    ("operations", ["operations", "ops", "program manager", "chief of staff"]),
]


def _extract_department(title: str) -> str | None:
    t = title.lower()
    for dept, keywords in _DEPT_KEYWORDS:
        if any(k in t for k in keywords):
            return dept
    return None


class NetworkingAgent(BaseAgent):
    agent_type = "networking"
    max_iterations = 1  # unused but required by base

    async def _execute(self, company: str | None = None, **kwargs) -> dict:
        user_result = await self.db.execute(select(User).where(User.id == self.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return {"summary": "User not found"}

        prefs_result = await self.db.execute(
            select(UserPreferences).where(UserPreferences.user_id == self.user_id)
        )
        prefs = prefs_result.scalar_one_or_none()
        if not prefs:
            return {"summary": "No preferences found"}

        existing_result = await self.db.execute(
            select(Contact.linkedin_url).where(
                Contact.user_id == self.user_id,
                Contact.linkedin_url.isnot(None),
            )
        )
        self._seen_urls: set[str] = {row[0] for row in existing_result}

        if company:
            companies = [company]
        else:
            manual = list(prefs.target_companies or [])
            discovered = await self._discover_companies(prefs)
            manual_lower = {_clean_company_name(c).lower() for c in manual}
            unique_discovered = [c for c in discovered if c.lower() not in manual_lower]
            companies = manual + unique_discovered

        if not companies:
            return {"summary": "No target companies configured — add companies in Settings or set company criteria"}

        if not prefs.target_roles:
            return {"summary": f"Found {len(companies)} companies but no target roles configured — add roles in Settings"}

        junior_titles = [
            f"{prefix} {role}"
            for prefix in JUNIOR_PREFIXES[:2]
            for role in (prefs.target_roles[:2] or [])
        ]

        contacts: list[dict] = []
        for target_company in companies[:TARGET_COMPANY_COUNT]:
            # Two searches per company: mid-level ICs and junior/entry-level
            for titles in [prefs.target_roles[:4], junior_titles]:
                if titles:
                    results = await self._exa_search(target_company, titles, max_results=10)
                    contacts.extend(results)
            # For YC startups, also target founders — they're the direct hiring decision-makers
            if _is_yc_company(target_company):
                results = await self._exa_search(
                    target_company, FOUNDER_TITLES, max_results=5, allow_founders=True
                )
                contacts.extend(results)

        logger.info("Networking: %d raw profiles collected", len(contacts))

        saved, new_contacts = await self._save_contacts(contacts)

        if saved > 0:
            await self._draft_outreach_messages(new_contacts, prefs)

        return {"summary": f"Saved {saved} new contacts", "contacts_found": saved}

    async def _discover_companies(self, prefs: UserPreferences) -> list[str]:
        stages = getattr(prefs, "company_stages", None) or []
        industries = getattr(prefs, "company_industries", None) or []
        if not stages and not industries:
            return []

        parts: list[str] = []
        if stages:
            parts.append(f"funding stage: {', '.join(stages)}")
        if industries:
            parts.append(f"industries: {', '.join(industries)}")

        logger.info("Discovering companies for criteria: %s", "; ".join(parts))

        prompt = (
            f"List exactly {MAX_DISCOVERED_COMPANIES} real, currently-active technology companies "
            f"matching ALL of: {'; '.join(parts)}.\n\n"
            "Rules: one company name per line, no numbering, no extra text, official trading name only "
            "(e.g. 'Stripe' not 'Stripe Inc.'). If fewer real companies match, return as many as you can."
        )
        text = await self.complete(prompt, model=DISCOVERY_MODEL, max_tokens=400)
        lines = text.splitlines()
        companies = []
        for l in lines:
            name = l.strip()
            if not name:
                continue
            # Strip leading "1. " / "1) " / "- " that Claude adds despite instructions
            import re as _re
            name = _re.sub(r"^[\d]+[.)]\s*", "", name)
            name = _re.sub(r"^[-•]\s*", "", name)
            if name:
                companies.append(name)
        companies = companies[:MAX_DISCOVERED_COMPANIES]
        logger.info("Discovered %d companies", len(companies))
        return companies

    async def _exa_search(
        self, company: str, titles: list[str], max_results: int, allow_founders: bool = False
    ) -> list[dict]:
        query_company = _query_company_name(company)
        if len(titles) >= 2:
            query = f"{titles[0]} or {titles[1]} at {query_company}"
        else:
            query = f"{titles[0]} at {query_company}"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    EXA_SEARCH_URL,
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": settings.exa_api_key,
                    },
                    json={
                        "query": query,
                        "category": "people",
                        "includeDomains": ["linkedin.com"],
                        "numResults": min(max_results, 10),
                        "type": "neural",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            logger.warning("Exa timeout for '%s' — skipping company this run", company)
            return []
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 429:
                logger.warning("Exa rate limit hit for '%s' — sleeping 5s", company)
                await asyncio.sleep(5)
            elif status in (401, 403):
                logger.error("Exa auth error (HTTP %d) — check EXA_API_KEY", status)
            else:
                logger.warning("Exa HTTP %d for '%s': %s", status, company, exc.response.text[:200])
            return []
        except Exception as exc:
            logger.warning("Exa search error for '%s': %s", company, exc)
            return []

        people = []
        for result in data.get("results") or []:
            url = result.get("url", "")
            if "linkedin.com/in/" not in url:
                continue
            if url in self._seen_urls:
                continue
            if url.startswith("http://"):
                url = url.replace("http://", "https://", 1)

            # Exa LinkedIn titles:  "Name | Title @ Company"  or  "Name | Title at Company"
            # Older indexed format: "Name - Title at Company | LinkedIn"
            page_title = result.get("title", "")
            name, job_title, current_company = "", "", ""

            if " | " in page_title and not page_title.endswith("| LinkedIn"):
                # Exa format
                name, _, rest = page_title.partition(" | ")
                name = name.strip()
                rest = rest.strip()
            elif " - " in page_title:
                # Fallback for older-style indexed titles
                parts = page_title.split(" - ", 1)
                name = parts[0].strip()
                rest = parts[1].split(" | LinkedIn")[0].strip()
            else:
                rest = ""

            if rest:
                current_company = _extract_current_company(rest)
                # Strip company marker to get the clean job title
                for marker in [f" at {current_company}", f" @ {current_company}", f"@{current_company}"]:
                    if current_company and marker.lower() in rest.lower():
                        idx = rest.lower().find(marker.lower())
                        job_title = rest[:idx].strip().rstrip(",").strip()
                        break
                else:
                    job_title = rest.strip()

            # Require confirmed current employer before saving.
            if not current_company:
                logger.debug("Skipping %s — could not confirm current employer", name)
                continue
            if not _companies_match(company, current_company):
                logger.debug(
                    "Skipping %s — current employer '%s' does not match '%s'",
                    name, current_company, company,
                )
                continue

            score = _score_title(job_title)
            if score == 0.0:
                if allow_founders and any(k in job_title.lower() for k in FOUNDER_KEYWORDS):
                    score = 0.9
                else:
                    continue

            name_parts = name.split()
            people.append({
                "first_name": name_parts[0] if name_parts else "",
                "last_name": " ".join(name_parts[1:]) if len(name_parts) > 1 else "",
                "title": job_title,
                "company": company,
                "linkedin_url": url,
                "relevance_score": score,
                "relevance_reasoning": self._reasoning(job_title),
            })
            self._seen_urls.add(url)

        logger.info("Exa '%s' -> %d profiles", company, len(people))
        await asyncio.sleep(0.3)
        return people

    def _reasoning(self, title: str) -> str:
        t = title.lower()
        if any(k in t for k in FOUNDER_KEYWORDS):
            return "Founder — direct hiring decision-maker at this startup"
        if any(k in t for k in RECRUITER_KEYWORDS):
            return "Recruiter — not a primary networking target"
        if any(k in t for k in JUNIOR_KEYWORDS):
            return "Entry/mid-level peer — great for referrals and culture insight"
        if any(k in t for k in MANAGER_KEYWORDS):
            return "Manager/Lead — useful for team context at smaller companies"
        return "Mid-level IC in relevant team"

    async def _draft_outreach_messages(self, contacts: list[Contact], prefs: UserPreferences) -> None:
        experience = prefs.experience_level or "entry"
        roles = prefs.target_roles or ["software engineering"]
        roles_str = ", ".join(roles[:3])

        for contact in contacts:
            prompt = (
                f"Write a warm, concise LinkedIn cold outreach message (2-3 sentences) from a "
                f"{experience}-level job seeker targeting {roles_str} roles "
                f"to {contact.first_name} {contact.last_name}, who is a {contact.title} at {contact.company}.\n\n"
                "Rules: reference the company or team (not their title), ask to learn about the team or "
                "culture, never ask for a job or referral directly. Return only the message text, no subject line."
            )
            try:
                contact.outreach_message = await self.complete(prompt, max_tokens=300)
            except Exception as exc:
                logger.warning("Outreach draft failed for contact %s: %s", contact.id, exc)

        await self.db.commit()

    async def _save_contacts(self, contacts: list[dict]) -> tuple[int, list[Contact]]:
        saved = 0
        new_contacts: list[Contact] = []
        for item in contacts:
            if not await quota.can_surface_contact(self.db, self.user_id):
                break

            linkedin_url = item.get("linkedin_url") or ""
            if linkedin_url:
                existing = await self.db.execute(
                    select(Contact).where(
                        Contact.user_id == self.user_id,
                        Contact.linkedin_url == linkedin_url,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

            title = item.get("title", "")
            contact = Contact(
                user_id=self.user_id,
                company=item.get("company", ""),
                first_name=item.get("first_name", ""),
                last_name=item.get("last_name"),
                title=title,
                linkedin_url=linkedin_url or None,
                email=None,
                seniority=_extract_seniority(title),
                department=_extract_department(title),
                relevance_score=float(item.get("relevance_score", 0)),
                relevance_reasoning=item.get("relevance_reasoning"),
                outreach_message=None,
            )
            self.db.add(contact)
            await self.db.flush()
            await quota.increment_contacts_surfaced(self.db, self.user_id)
            new_contacts.append(contact)
            saved += 1

        await self.db.commit()
        self._contacts_saved = saved
        return saved, new_contacts
