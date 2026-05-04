import re

# Funding/investor-data platforms that LLMs confuse for funded startups
FUNDING_DB_KEYWORDS = {
    "pitchbook", "angellist", "crunchbase", "carta", "cb insights",
    "cbinsights", "dealroom", "preqin", "signal.nfx", "signal nfx",
    "gust", "fundersclub", "seedinvest", "republic",
}


def clean_company_name(company: str) -> str:
    """Strip trailing parentheticals like '(YC S26)' for matching."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", company).strip()


def query_company_name(company: str) -> str:
    """Format for search queries — YC companies keep their batch tag."""
    m = re.search(r"\(YC ([^)]+)\)", company, re.IGNORECASE)
    if m:
        base = clean_company_name(company)
        return f"{base} YC {m.group(1)}"
    return clean_company_name(company)


def companies_match(target: str, found: str) -> bool:
    """Case-insensitive substring match between cleaned company names."""
    t = clean_company_name(target).lower().strip()
    f = found.lower().strip()
    return t in f or f in t
