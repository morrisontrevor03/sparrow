"""
The Sparrow outreach agent.

Given a campaign, finds the right people at target companies and drafts a first
message to each. The discovery mechanics (Exa people search, LinkedIn title
parsing, fuzzy employer matching) are campaign-type agnostic; everything that
encodes *who is worth contacting* and *what to ask them* comes from the campaign's
targeting profile.
"""

import asyncio
import logging
import re
import uuid

import httpx
from sqlalchemy import select

from app.agents.base import BaseAgent
from app.config import settings
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.user import User
from app.services import credits, drafting, targeting
from app.services.company_match import (
    FUNDING_DB_KEYWORDS,
    clean_company_name,
    companies_match,
    query_company_name,
)

logger = logging.getLogger(__name__)

TARGET_COMPANY_COUNT = 25
EXA_SEARCH_URL = "https://api.exa.ai/search"
DISCOVERY_MODEL = "claude-haiku-4-5"
MAX_DISCOVERED_COMPANIES = 20


def _extract_current_company(text: str) -> str:
    """
    Pull the employer from ' at Company', ' @ Company', or '@Company' patterns.
    Exa titles use '@' instead of 'at', so we must handle both.
    """
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


class OutreachAgent(BaseAgent):
    agent_type = "outreach"
    max_iterations = 1  # unused but required by base

    async def _execute(
        self,
        campaign_id: uuid.UUID | None = None,
        company: str | None = None,
        max_contacts: int | None = None,
        **kwargs,
    ) -> dict:
        await self._update_progress("Loading campaign")

        campaign = await self._load_campaign(campaign_id)
        if not campaign:
            return {"summary": "Campaign not found"}

        self._campaign = campaign
        self._profile = targeting.get_profile(campaign.campaign_type)
        self._credits_spent = 0
        self._max_contacts = max_contacts

        user = (
            await self.db.execute(select(User).where(User.id == self.user_id))
        ).scalar_one_or_none()
        if not user:
            return {"summary": "User not found"}

        if not await credits.has_credits(self.db, self.user_id, settings.credits_per_contact):
            return {"summary": "Out of credits — top up to keep running this campaign"}

        existing = await self.db.execute(
            select(Contact.linkedin_url).where(
                Contact.user_id == self.user_id,
                Contact.linkedin_url.isnot(None),
            )
        )
        self._seen_urls: set[str] = {row[0] for row in existing}

        target_locations = campaign.target_locations or []
        only_remote = (
            all("remote" in loc.lower() for loc in target_locations)
            if target_locations
            else True
        )
        self._location_hint = target_locations[0] if target_locations and not only_remote else ""

        companies = await self._resolve_companies(campaign, company)
        if not companies:
            return {
                "summary": "No target companies — add companies, or set industries and "
                "stages so Sparrow can find them for you"
            }
        if not campaign.target_titles:
            return {
                "summary": f"Found {len(companies)} companies but no target titles — "
                "add the roles you want to reach in campaign settings"
            }

        found = await self._search_companies(campaign, companies)
        logger.info("Outreach: %d raw profiles collected", len(found))

        await self._update_progress("Saving contacts")
        saved, new_contacts = await self._save_contacts(found)

        drafted = 0
        if new_contacts:
            await self._update_progress("Drafting outreach messages")
            drafted = await self._draft_outreach_messages(new_contacts, campaign, user)

        summary = f"Found {saved} new contacts"
        if drafted:
            summary += f", drafted {drafted} messages"
        if saved == 0 and found:
            summary = "No new contacts — everyone found was already in your list"

        return {
            "summary": summary,
            "contacts_found": saved,
            "drafts_written": drafted,
            "credits_spent": self._credits_spent,
        }

    async def _load_campaign(self, campaign_id: uuid.UUID | None) -> Campaign | None:
        query = select(Campaign).where(Campaign.user_id == self.user_id)
        if campaign_id:
            query = query.where(Campaign.id == campaign_id)
        else:
            query = query.where(Campaign.status == "active").order_by(Campaign.created_at)
        return (await self.db.execute(query)).scalars().first()

    async def _resolve_companies(self, campaign: Campaign, company: str | None) -> list[str]:
        if company:
            return [company]

        manual = list(campaign.target_companies or [])
        excluded = {clean_company_name(c).lower() for c in (campaign.excluded_companies or [])}
        manual_filtered = [c for c in manual if clean_company_name(c).lower() not in excluded]

        # An explicit company list is a hard boundary unless the user opted in to
        # discovery — expanding past it without asking spends Exa/LLM credits on
        # companies they didn't name.
        if manual and not campaign.discover_beyond_list:
            return manual_filtered

        await self._update_progress("Discovering additional companies")
        discovered = await self._discover_companies(campaign)

        manual_lower = {clean_company_name(c).lower() for c in manual}
        unique = [
            c for c in discovered
            if c.lower() not in manual_lower and clean_company_name(c).lower() not in excluded
        ]
        return manual_filtered + unique

    async def _discover_companies(self, campaign: Campaign) -> list[str]:
        stages = campaign.company_stages or []
        industries = campaign.target_industries or []
        objective = (campaign.objective or "").strip()

        if not stages and not industries and not objective:
            return []

        criteria: list[str] = []
        if stages:
            criteria.append(f"most recent funding round is one of: {', '.join(stages)}")
        if industries:
            criteria.append(f"industries: {', '.join(industries)}")
        if campaign.target_locations:
            criteria.append(f"based in or hiring in: {', '.join(campaign.target_locations)}")

        goal_line = f'The user\'s goal is: "{objective}"\n\n' if objective else ""
        criteria_line = (
            f"matching ALL of: {'; '.join(criteria)}"
            if criteria
            else "that would be a strong fit for that goal"
        )

        prompt = (
            f"{goal_line}"
            f"List exactly {MAX_DISCOVERED_COMPANIES} real, currently-active companies "
            f"{criteria_line}.\n\n"
            "IMPORTANT: Use only the company's LATEST/MOST RECENT funding round — not any "
            "historical round. For example, OpenAI must NOT be included for 'Series A' "
            "because its latest round is Series G.\n\n"
            "CRITICAL: Do NOT include companies whose primary business is tracking, indexing, "
            "or aggregating startup/investment data. Exclude platforms like PitchBook, "
            "AngelList, Crunchbase, Carta, CB Insights, Dealroom, or Preqin. Only include "
            "companies that are actual operating businesses.\n\n"
            "Rules: one company name per line, no numbering, no extra text, official trading "
            "name only (e.g. 'Stripe' not 'Stripe Inc.'). If fewer real companies match, "
            "return as many as you can."
        )

        text = await self.complete(prompt, model=DISCOVERY_MODEL, max_tokens=400)

        companies = []
        for line in text.splitlines():
            name = re.sub(r"^[\d]+[.)]\s*", "", line.strip())
            name = re.sub(r"^[-•]\s*", "", name).strip()
            if name and not any(kw in name.lower() for kw in FUNDING_DB_KEYWORDS):
                companies.append(name)

        companies = companies[:MAX_DISCOVERED_COMPANIES]
        logger.info("Discovered %d companies", len(companies))
        return companies

    async def _search_companies(self, campaign: Campaign, companies: list[str]) -> list[dict]:
        titles = list(campaign.target_titles or [])
        expanded = [
            f"{prefix} {titles[0]}"
            for prefix in self._profile.query_expansions
            if titles
        ]

        results: list[dict] = []
        total = min(len(companies), TARGET_COMPANY_COUNT)
        for idx, target_company in enumerate(companies[:TARGET_COMPANY_COUNT], 1):
            await self._update_progress(f"Searching {target_company} ({idx}/{total})")
            for title_set in (titles[:4], expanded[:2]):
                if title_set:
                    results.extend(await self._exa_search(target_company, title_set))
        return results

    async def _exa_search(
        self, company: str, titles: list[str], max_results: int = 10
    ) -> list[dict]:
        query_company = query_company_name(company)
        if len(titles) >= 2:
            query = f"{titles[0]} or {titles[1]} at {query_company}"
        else:
            query = f"{titles[0]} at {query_company}"

        if self._location_hint:
            query = f"{query} in {self._location_hint}"

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

        raw_results = data.get("results") or []
        people = []
        for result in raw_results:
            person = self._parse_person(result, company)
            if person:
                people.append(person)
                self._seen_urls.add(person["linkedin_url"])

        logger.info(
            "Exa '%s' -> %d raw results, %d parsed profiles (query=%r)",
            company, len(raw_results), len(people), query,
        )
        await asyncio.sleep(0.3)
        return people

    def _parse_person(self, result: dict, company: str) -> dict | None:
        url = result.get("url", "")
        if "linkedin.com/in/" not in url:
            logger.info("Skipping result — not a linkedin.com/in/ url: %r", url)
            return None
        if url.startswith("http://"):
            url = url.replace("http://", "https://", 1)
        if url in self._seen_urls:
            logger.info("Skipping %s — already seen this run", url)
            return None

        parsed = self._parse_person_entity(result) or self._parse_person_title(result)
        if not parsed:
            logger.info(
                "Skipping — could not extract name/title/company. raw result=%r", result
            )
            return None
        first_name, last_name, job_title, current_company = parsed

        if not companies_match(company, current_company):
            logger.info(
                "Skipping %s %s — employer '%s' does not match '%s'",
                first_name, last_name, current_company, company,
            )
            return None

        score, reason = targeting.score_title(job_title, self._profile)
        if score <= 0.0:
            logger.info(
                "Skipping %s %s — title %r scored %s (%s)",
                first_name, last_name, job_title, score, reason,
            )
            return None

        return {
            "first_name": first_name,
            "last_name": last_name,
            "title": job_title,
            "company": company,
            "linkedin_url": url,
            "relevance_score": score,
            "relevance_reasoning": reason,
        }

    @staticmethod
    def _parse_person_entity(result: dict) -> tuple[str, str, str, str] | None:
        """Exa's `category: "people"` results carry a structured `entities` list
        with a `workHistory` — this is the current response shape, not the
        scraped-page `title` string `_parse_person_title` below handles."""
        entities = result.get("entities") or []
        person = next((e for e in entities if e.get("type") == "person"), None)
        if not person:
            return None
        props = person.get("properties") or {}
        work_history = props.get("workHistory") or []
        current_job = next(
            (j for j in work_history if not (j.get("dates") or {}).get("to")), None
        ) or (work_history[0] if work_history else None)
        if not current_job:
            return None

        current_company = (current_job.get("company") or {}).get("name", "")
        job_title = current_job.get("title", "")
        if not current_company or not job_title:
            return None
        return props.get("firstName", ""), props.get("lastName", ""), job_title, current_company

    @staticmethod
    def _parse_person_title(result: dict) -> tuple[str, str, str, str] | None:
        """Fallback for the older scraped-page title format:
        "Name | Title @ Company" or "Name - Title at Company | LinkedIn"."""
        page_title = result.get("title", "")
        name, rest = "", ""

        if " | " in page_title and not page_title.endswith("| LinkedIn"):
            name, _, rest = page_title.partition(" | ")
            name, rest = name.strip(), rest.strip()
        elif " - " in page_title:
            parts = page_title.split(" - ", 1)
            name = parts[0].strip()
            rest = parts[1].split(" | LinkedIn")[0].strip()

        if not rest:
            return None

        current_company = _extract_current_company(rest)
        if not current_company:
            return None

        for marker in (f" at {current_company}", f" @ {current_company}", f"@{current_company}"):
            idx = rest.lower().find(marker.lower())
            if idx != -1:
                job_title = rest[:idx].strip().rstrip(",").strip()
                break
        else:
            job_title = rest.strip()

        name_parts = name.split()
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
        return first_name, last_name, job_title, current_company

    async def _save_contacts(self, found: list[dict]) -> tuple[int, list[Contact]]:
        # Best matches first, so a balance that runs out mid-run spends what's
        # left on the most relevant people rather than whoever came back first.
        found.sort(key=lambda c: c["relevance_score"], reverse=True)

        saved = 0
        new_contacts: list[Contact] = []
        for item in found:
            if self._max_contacts is not None and saved >= self._max_contacts:
                break
            if not await credits.has_credits(self.db, self.user_id, settings.credits_per_contact):
                logger.info("Stopping contact discovery — credit balance exhausted")
                break

            linkedin_url = item.get("linkedin_url") or ""
            if linkedin_url:
                dupe = await self.db.execute(
                    select(Contact).where(
                        Contact.user_id == self.user_id,
                        Contact.linkedin_url == linkedin_url,
                    )
                )
                if dupe.scalar_one_or_none():
                    continue

            title = item.get("title", "")
            contact = Contact(
                user_id=self.user_id,
                campaign_id=self._campaign.id,
                company=item.get("company", ""),
                first_name=item.get("first_name", ""),
                last_name=item.get("last_name"),
                title=title,
                linkedin_url=linkedin_url or None,
                email=None,
                seniority=targeting.extract_seniority(title),
                department=targeting.extract_department(title),
                relevance_score=float(item.get("relevance_score", 0)),
                relevance_reasoning=item.get("relevance_reasoning"),
                outreach_message=None,
            )
            self.db.add(contact)
            await self.db.flush()

            # Charge only after the row exists — a failed insert is never billed.
            await credits.spend(
                self.db,
                self.user_id,
                settings.credits_per_contact,
                "contact_discovered",
                campaign_id=self._campaign.id,
                agent_run_id=self._run.id if self._run else None,
            )
            self._credits_spent += settings.credits_per_contact

            new_contacts.append(contact)
            saved += 1

        await self.db.commit()
        return saved, new_contacts

    async def _draft_outreach_messages(
        self, contacts: list[Contact], campaign: Campaign, user: User
    ) -> int:
        sender = await drafting.build_sender_context(self.db, user)
        objective = (campaign.objective or "").strip() or campaign.name

        drafted = 0
        for contact in contacts:
            if not await credits.has_credits(self.db, self.user_id, settings.credits_per_draft):
                logger.info("Stopping drafting — credit balance exhausted")
                break

            prompt = drafting.build_draft_prompt(sender, contact, self._profile, objective)
            try:
                message = await self.complete(prompt, max_tokens=300)
            except Exception as exc:
                logger.warning("Outreach draft failed for contact %s: %s", contact.id, exc)
                continue

            contact.outreach_message = message
            contact.outreach_status = "message_drafted"
            await self.db.flush()

            await credits.spend(
                self.db,
                self.user_id,
                settings.credits_per_draft,
                "outreach_draft",
                campaign_id=campaign.id,
                agent_run_id=self._run.id if self._run else None,
            )
            self._credits_spent += settings.credits_per_draft
            drafted += 1

        await self.db.commit()
        return drafted
