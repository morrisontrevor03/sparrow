import asyncio
import logging
import re
from datetime import datetime
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.company_match import companies_match

logger = logging.getLogger(__name__)

_EXA_URL = "https://api.exa.ai/search"
_JOB_DOMAINS = [
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "greenhouse.io",
    "lever.co",
    "workday.com",
    "ashbyhq.com",
    "smartrecruiters.com",
    "icims.com",
    "myworkdayjobs.com",
    "jobs.lever.co",
    "boards.greenhouse.io",
]


def _company_from_url(url: str) -> str:
    """Extract company name from common ATS URL patterns. Returns '' if unknown."""
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""

    # boards.greenhouse.io/<company>/jobs/...
    if host == "boards.greenhouse.io" or host.endswith(".greenhouse.io"):
        m = re.match(r"^/([^/]+)/", path)
        if m:
            return m.group(1).replace("-", " ").replace("_", " ")

    # jobs.lever.co/<company>/...
    if host == "jobs.lever.co" or host.endswith(".lever.co"):
        m = re.match(r"^/([^/]+)/", path)
        if m:
            return m.group(1).replace("-", " ").replace("_", " ")

    # <company>.ashbyhq.com/... or jobs.ashbyhq.com/<company>/...
    if host.endswith(".ashbyhq.com"):
        sub = host.replace(".ashbyhq.com", "")
        if sub == "jobs":
            m = re.match(r"^/([^/]+)/", path)
            if m:
                return m.group(1).replace("-", " ").replace("_", " ")
        else:
            return sub.replace("-", " ").replace("_", " ")

    # <company>.myworkdayjobs.com/...
    if host.endswith(".myworkdayjobs.com"):
        sub = host.replace(".myworkdayjobs.com", "")
        # often "<company>.wd1.myworkdayjobs.com" — strip wdN.
        sub = re.sub(r"\.wd\d+$", "", sub)
        return sub.replace("-", " ").replace("_", " ")

    # apply.workable.com/<company>/... or <company>.workable.com
    if host == "apply.workable.com":
        m = re.match(r"^/([^/]+)/", path)
        if m:
            return m.group(1).replace("-", " ").replace("_", " ")

    # jobs.smartrecruiters.com/<company>/...
    if host.endswith("smartrecruiters.com"):
        m = re.match(r"^/([^/]+)/", path)
        if m:
            return m.group(1).replace("-", " ").replace("_", " ")

    return ""


async def validate_urls(urls: list[str], concurrency: int = 8, timeout: float = 5.0) -> set[str]:
    """Return the subset of URLs that respond OK (or with a non-fatal status).

    Drops 404/410/451 and connection errors. Keeps 200/3xx and also 403/405
    (bot-walls and HEAD-not-allowed are common false negatives)."""
    bad_codes = {404, 410, 451}
    sem = asyncio.Semaphore(concurrency)
    good: set[str] = set()

    async def check(client: httpx.AsyncClient, url: str) -> None:
        async with sem:
            try:
                resp = await client.head(url, follow_redirects=True, timeout=timeout)
                if resp.status_code in bad_codes:
                    return
                # Some sites reject HEAD with 4xx/5xx but serve GET fine. Try GET fallback.
                if resp.status_code >= 400 and resp.status_code not in (403, 405, 429):
                    resp = await client.get(url, follow_redirects=True, timeout=timeout)
                    if resp.status_code in bad_codes:
                        return
                good.add(url)
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError):
                return
            except Exception:
                # Unknown error — keep the URL rather than drop a real listing
                good.add(url)

    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (compatible; ApplyNowBot/1.0)"}) as client:
        await asyncio.gather(*(check(client, u) for u in urls))
    return good


def _parse_exa_job_title(page_title: str) -> tuple[str, str]:
    """Extract (job_title, company) from an Exa job-page title.

    Handles patterns like:
      'Solution Engineer at Salesforce | Greenhouse'
      'Salesforce - Solution Engineer - San Francisco, CA | LinkedIn'
      'Solution Engineer - Salesforce Careers'
    Returns (job_title, company) — either may be empty string.
    """
    # Strip trailing platform suffixes
    for suffix in [" | LinkedIn", " | Indeed", " | Glassdoor", " | Greenhouse", " | Workday"]:
        if page_title.endswith(suffix):
            page_title = page_title[: -len(suffix)].strip()

    # Pattern: "Title at Company" or "Title @ Company"
    m = re.search(r"^(.+?)\s+(?:at|@)\s+(.+)$", page_title, re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # Pattern: "Company - Title" or "Title - Company ..."
    parts = [p.strip() for p in page_title.split(" - ")]
    if len(parts) >= 2:
        # Heuristic: first part with "careers" in it is the company
        if "career" in parts[-1].lower() or "job" in parts[-1].lower():
            return parts[0], re.sub(r"\s*(careers|jobs)\s*$", "", parts[-1], flags=re.IGNORECASE).strip()
        return parts[0], parts[1]

    return page_title.strip(), ""


async def search_jobs_exa(
    query: str,
    max_results: int = 5,
    company_hint: str = "",
) -> list[dict]:
    """Search for job postings via Exa neural search across career pages and job boards."""
    if not settings.exa_api_key:
        logger.warning("EXA_API_KEY not set — skipping Exa job search")
        return []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _EXA_URL,
                headers={"Content-Type": "application/json", "x-api-key": settings.exa_api_key},
                json={
                    "query": query,
                    "type": "neural",
                    "numResults": min(max_results, 10),
                    "includeDomains": _JOB_DOMAINS,
                    "contents": {"text": {"maxCharacters": 800}},
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        logger.warning("Exa job search timeout for query: %s", query[:80])
        return []
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 429:
            logger.warning("Exa rate limit on job search")
        elif status in (401, 403):
            logger.error("Exa auth error (HTTP %d) — check EXA_API_KEY", status)
        else:
            logger.warning("Exa HTTP %d: %s", status, exc.response.text[:200])
        return []
    except Exception as exc:
        logger.warning("Exa job search error: %s", exc)
        return []

    results = []
    for item in data.get("results") or []:
        url = item.get("url", "")
        if not url:
            continue

        page_title = item.get("title", "")
        parsed_title, parsed_company = _parse_exa_job_title(page_title)
        url_company = _company_from_url(url)
        text = item.get("text", "") or ""

        # Resolve company: trust URL-derived first, then title parse.
        # Only fall back to company_hint when the URL/title actually backs it up.
        candidates = [c for c in (url_company, parsed_company) if c]
        company = ""
        if candidates:
            company = candidates[0]

        if company_hint:
            hint_match = any(companies_match(company_hint, c) for c in candidates)
            if hint_match:
                # Use the canonical hint name when we've confirmed the match
                company = company_hint
            elif candidates:
                # We have a real company but it doesn't match the hint — drop it,
                # otherwise we'd mislabel the posting.
                continue
            else:
                # No signal either way — also drop, since the hint is unverified
                continue

        if not company:
            # General search with no company info anywhere — skip
            continue

        results.append({
            "external_id": url,
            "source": "exa",
            "title": parsed_title,
            "company": company,
            "location": "",
            "description": text[:800],
            "url": url,
            "salary_min": None,
            "salary_max": None,
            "employment_type": None,
        })

    return results


async def search_adzuna(keywords: str, location: str = "", max_results: int = 20) -> list[dict]:
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        logger.warning("Adzuna credentials not set")
        return []

    params = {
        "app_id": settings.adzuna_app_id,
        "app_key": settings.adzuna_app_key,
        "results_per_page": max_results,
        "what": keywords,
        "content-type": "application/json",
    }
    if location:
        params["where"] = location
    if settings.free_jobs_per_month:
        params["salary_min"] = 0

    url = "https://api.adzuna.com/v1/api/jobs/us/search/1"

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("Adzuna error: %s", exc)
            return []

    results = []
    for item in data.get("results", []):
        results.append({
            "external_id": item.get("id", ""),
            "source": "adzuna",
            "title": item.get("title", ""),
            "company": item.get("company", {}).get("display_name", "Unknown"),
            "location": item.get("location", {}).get("display_name", ""),
            "description": item.get("description", ""),
            "url": item.get("redirect_url", ""),
            "salary_min": int(item["salary_min"]) if item.get("salary_min") else None,
            "salary_max": int(item["salary_max"]) if item.get("salary_max") else None,
            "employment_type": item.get("contract_type"),
            "posted_at": item.get("created"),
        })
    return results


async def search_jsearch(query: str, location: str = "", max_results: int = 10) -> list[dict]:
    if not settings.jsearch_api_key:
        logger.warning("JSearch API key not set")
        return []

    full_query = f"{query} {location}".strip()
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                "https://jsearch.p.rapidapi.com/search",
                params={"query": full_query, "num_pages": "1", "page": "1"},
                headers={
                    "X-RapidAPI-Key": settings.jsearch_api_key,
                    "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("JSearch error: %s", exc)
            return []

    results = []
    for item in data.get("data", [])[:max_results]:
        results.append({
            "external_id": item.get("job_id", ""),
            "source": "jsearch",
            "title": item.get("job_title", ""),
            "company": item.get("employer_name", "Unknown"),
            "location": f"{item.get('job_city', '')} {item.get('job_state', '')} {item.get('job_country', '')}".strip(),
            "description": item.get("job_description", ""),
            "url": item.get("job_apply_link") or item.get("job_google_link", ""),
            "salary_min": item.get("job_min_salary"),
            "salary_max": item.get("job_max_salary"),
            "employment_type": item.get("job_employment_type"),
            "posted_at": None,
        })
    return results


