"""
Per-campaign-type targeting profiles.

The old NetworkingAgent hard-coded one worldview: exclude every VP, Director, and
Chief, because a job seeker wants IC peers who will refer them and executives never
reply. That is correct for job search and exactly backwards for business development
and fundraising, where the executive *is* the target.

Each profile supplies three things:
  1. a title-scoring ladder (cheap, deterministic, runs on every search result)
  2. search title variants (what to actually ask Exa for)
  3. prompt fragments (how to frame the ask when drafting outreach)

Scores are 0.0-1.0. A score of 0.0 means "skip this person entirely".
"""

from dataclasses import dataclass, field

# Titles that are noise in every campaign type — never worth an outreach credit.
UNIVERSAL_EXCLUDE = {
    "intern",
    "student",
    "seeking",
    "open to work",
    "looking for",
    "retired",
    "former",
}


@dataclass(frozen=True)
class TargetingProfile:
    key: str
    label: str
    description: str

    # Ordered tiers: the first tier whose keywords appear in the title wins.
    # (score, keywords, reason shown to the user)
    tiers: tuple[tuple[float, frozenset[str], str], ...]
    default_score: float
    default_reason: str
    exclude: frozenset[str] = field(default_factory=frozenset)

    # Extra title phrasings to search for beyond the campaign's target_titles.
    query_expansions: tuple[str, ...] = ()

    # Prompt fragments for outreach drafting.
    persona: str = ""
    ask_guidance: str = ""


_EXEC = frozenset({"chief", "ceo", "cto", "coo", "cfo", "cro", "cmo", "president"})
_VP = frozenset({"vp", "vice president", "head of", "svp", "evp"})
_DIRECTOR = frozenset({"director"})
_MANAGER = frozenset({"manager", "lead", "principal", "staff"})
_RECRUITER = frozenset({"recruiter", "talent", "sourcer", "recruiting", "staffing"})
_FOUNDER = frozenset({"founder", "co-founder", "cofounder", "owner"})
_JUNIOR = frozenset({"junior", "associate", "entry level", "new grad", "early career"})
_INVESTOR = frozenset(
    {"partner", "general partner", "managing director", "principal", "investor", "venture"}
)


BUSINESS_DEVELOPMENT = TargetingProfile(
    key="business_development",
    label="Business development",
    description="Find economic buyers and champions at target accounts.",
    tiers=(
        (0.95, _VP, "VP/Head of — typically owns the budget for this"),
        (0.90, _DIRECTOR, "Director — owns the problem and can sponsor a pilot"),
        (0.85, _FOUNDER, "Founder — direct decision-maker at a company this size"),
        (0.80, _EXEC, "C-level — decision-maker, though harder to reach cold"),
        (0.70, _MANAGER, "Manager/Lead — close to the pain, can champion internally"),
        (0.25, _RECRUITER, "Recruiting function — rarely a buyer"),
    ),
    default_score=0.55,
    default_reason="Individual contributor in a relevant team — useful for context",
    exclude=UNIVERSAL_EXCLUDE,
    query_expansions=("Head of", "VP", "Director of"),
    persona="someone doing business development outreach",
    ask_guidance=(
        "Ask for a short conversation to learn whether this is a real problem for their team. "
        "Do not pitch features, do not attach a deck, and do not ask for a purchase."
    ),
)

JOB_SEARCH = TargetingProfile(
    key="job_search",
    label="Job search",
    description="Find peers and hiring managers who can refer you in.",
    tiers=(
        (0.85, _JUNIOR, "Entry/mid-level peer — great for referrals and team insight"),
        (0.80, _FOUNDER, "Founder — direct hiring decision-maker at a startup"),
        (0.65, _MANAGER, "Manager/Lead — useful for team context and may be hiring"),
        (0.30, _RECRUITER, "Recruiter — a channel, but not a warm introduction"),
        (0.0, _EXEC, ""),
        (0.0, _VP, ""),
        (0.0, _DIRECTOR, ""),
    ),
    default_score=0.75,
    default_reason="Mid-level IC on a relevant team",
    exclude=UNIVERSAL_EXCLUDE,
    query_expansions=("Senior", "Junior", "Associate"),
    persona="a job seeker exploring teams",
    ask_guidance=(
        "Ask to learn about the team or the work. Never ask for a job, a referral, or "
        "an interview in a first message — the goal is a conversation, not a favor."
    ),
)

FUNDRAISING = TargetingProfile(
    key="fundraising",
    label="Fundraising",
    description="Find investors who write cheques at your stage.",
    tiers=(
        (0.95, frozenset({"general partner", "managing partner", "managing director"}),
         "GP/MD — writes cheques and leads rounds"),
        (0.90, frozenset({"partner"}), "Partner — decision-maker on new investments"),
        (0.80, frozenset({"principal"}), "Principal — sources and champions deals internally"),
        (0.70, frozenset({"investor", "venture", "angel"}), "Investor — relevant cheque-writer"),
        (0.55, frozenset({"associate", "analyst"}),
         "Associate/Analyst — sources deals; a realistic first touch"),
        (0.20, _RECRUITER, "Talent partner — portfolio support, not investment"),
    ),
    default_score=0.30,
    default_reason="At the firm but not obviously on the investment team",
    exclude=UNIVERSAL_EXCLUDE,
    query_expansions=("Partner", "Principal", "Investor"),
    persona="a founder raising a round",
    ask_guidance=(
        "Lead with one concrete traction fact. Ask for a short intro call, not for money. "
        "Do not attach a deck or state a valuation in a first message."
    ),
)

RECRUITING = TargetingProfile(
    key="recruiting",
    label="Recruiting",
    description="Find candidates doing the work you want to hire for.",
    tiers=(
        (0.90, frozenset({"senior", "staff", "principal"}),
         "Senior/Staff IC — the experience level you're hiring for"),
        (0.75, _MANAGER, "Lead/Manager — candidate or a source of referrals"),
        (0.60, _JUNIOR, "Earlier-career — a fit for more junior openings"),
        (0.20, _RECRUITER, "Recruiter — a peer, not a candidate"),
        (0.15, _EXEC, "Executive — unlikely to move for an IC role"),
    ),
    default_score=0.70,
    default_reason="IC doing relevant work",
    exclude=UNIVERSAL_EXCLUDE,
    query_expansions=("Senior", "Staff"),
    persona="someone hiring for a team",
    ask_guidance=(
        "Be explicit that you're hiring and say what the role is in the first two sentences. "
        "Respect their time — do not open with a vague 'quick chat' that hides the ask."
    ),
)

CUSTOM = TargetingProfile(
    key="custom",
    label="Custom",
    description="Rank purely on how well the title matches what you asked for.",
    tiers=(),
    default_score=0.70,
    default_reason="Title matches the campaign's target roles",
    exclude=UNIVERSAL_EXCLUDE,
    persona="someone doing professional outreach",
    ask_guidance=(
        "Make the ask specific and small. Say why you're contacting this person "
        "specifically rather than sending a generic note."
    ),
)


PROFILES: dict[str, TargetingProfile] = {
    p.key: p
    for p in (BUSINESS_DEVELOPMENT, JOB_SEARCH, FUNDRAISING, RECRUITING, CUSTOM)
}


def get_profile(campaign_type: str | None) -> TargetingProfile:
    return PROFILES.get(campaign_type or "", CUSTOM)


def score_title(title: str, profile: TargetingProfile) -> tuple[float, str]:
    """
    Score a title against a profile. Returns (score, reason).

    A 0.0 score means skip. Tiers are ordered most-specific-first and the first
    keyword hit wins, so "VP of Engineering" scores as a VP, not as a manager.
    """
    t = (title or "").lower()
    if not t:
        return 0.0, ""

    if any(k in t for k in profile.exclude):
        return 0.0, ""

    for score, keywords, reason in profile.tiers:
        if any(k in t for k in keywords):
            return score, reason

    return profile.default_score, profile.default_reason


def extract_seniority(title: str) -> str:
    t = (title or "").lower()
    if any(k in t for k in _FOUNDER):
        return "founder"
    if any(k in t for k in _EXEC):
        return "executive"
    if any(k in t for k in _VP):
        return "vp"
    if any(k in t for k in _DIRECTOR):
        return "director"
    if any(k in t for k in _INVESTOR):
        return "investor"
    if any(k in t for k in _MANAGER):
        return "manager"
    if any(k in t for k in _JUNIOR):
        return "entry"
    if any(k in t for k in _RECRUITER):
        return "recruiting"
    return "mid"


_DEPT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("engineering", ["engineer", "developer", "swe", "backend", "frontend", "fullstack",
                     "devops", "infra", "platform", "sre"]),
    ("data", ["data", "analytics", "machine learning", " ml ", " ai ", "scientist"]),
    ("product", ["product manager", "pm ", "product lead", "product owner"]),
    ("design", ["designer", "ux", "ui ", "creative", "brand"]),
    ("sales", ["sales", "account executive", "ae ", "business development", "bdr", "sdr",
               "revenue", "partnerships"]),
    ("marketing", ["marketing", "growth", "content", "seo", "demand gen"]),
    ("recruiting", ["recruiter", "talent", "sourcer", "staffing", "people ops"]),
    ("finance", ["finance", "accounting", "controller", "cfo", "treasury"]),
    ("investing", ["partner", "principal", "investor", "venture", "associate"]),
    ("operations", ["operations", "ops", "program manager", "chief of staff", "strategy"]),
]


def extract_department(title: str) -> str | None:
    t = (title or "").lower()
    for dept, keywords in _DEPT_KEYWORDS:
        if any(k in t for k in keywords):
            return dept
    return None
