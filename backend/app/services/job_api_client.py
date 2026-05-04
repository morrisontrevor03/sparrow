import logging
import re
from datetime import datetime

import httpx

from app.config import settings

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

        company = company_hint or parsed_company
        text = item.get("text", "") or ""

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


