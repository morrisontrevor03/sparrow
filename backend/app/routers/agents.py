import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, AsyncSessionLocal
from app.dependencies import get_current_user
from app.models.agent_run import AgentRun
from app.models.user import User
from app.services import quota

router = APIRouter(prefix="/api/agents", tags=["agents"])


class SingleCompanyRequest(BaseModel):
    company: str


async def _run_agent(agent_class, user_id, trigger: str, **kwargs):
    async with AsyncSessionLocal() as db:
        agent = agent_class(db, user_id)
        await agent.run(trigger=trigger, **kwargs)


@router.post("/job-scout/run")
async def trigger_job_scout(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await quota.can_run_agent(db, current_user.id, "job_scout"):
        raise HTTPException(status_code=402, detail="Free plan limit reached — upgrade to Pro for unlimited agent runs")
    from app.agents.job_scout import JobScoutAgent
    background_tasks.add_task(_run_agent, JobScoutAgent, current_user.id, "manual")
    return {"ok": True, "message": "Job Scout started"}


@router.post("/networking/run")
async def trigger_networking(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await quota.can_run_agent(db, current_user.id, "networking"):
        raise HTTPException(status_code=402, detail="Free plan limit reached — upgrade to Pro for unlimited agent runs")
    from app.agents.networking import NetworkingAgent
    background_tasks.add_task(_run_agent, NetworkingAgent, current_user.id, "manual")
    return {"ok": True, "message": "Networking Agent started"}


@router.post("/networking/run-single")
async def trigger_networking_single(
    body: SingleCompanyRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await quota.can_run_agent(db, current_user.id, "networking"):
        raise HTTPException(status_code=402, detail="Free plan limit reached — upgrade to Pro for unlimited agent runs")
    from app.agents.networking import NetworkingAgent
    background_tasks.add_task(
        _run_agent, NetworkingAgent, current_user.id, "manual", company=body.company
    )
    return {"ok": True, "message": f"Networking Agent started for {body.company}"}


@router.post("/application/run")
async def trigger_application_agent(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await quota.can_run_agent(db, current_user.id, "application"):
        raise HTTPException(status_code=402, detail="Free plan limit reached — upgrade to Pro for unlimited agent runs")
    from app.agents.application import ApplicationAgent
    background_tasks.add_task(_run_agent, ApplicationAgent, current_user.id, "manual")
    return {"ok": True, "message": "Application Agent started"}


@router.post("/test-email")
async def test_email(current_user: User = Depends(get_current_user)):
    """Send a test email to the current user and return the raw Resend response."""
    if not settings.resend_api_key:
        return {"ok": False, "error": "RESEND_API_KEY not configured"}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from_email,
                "to": [current_user.email],
                "subject": "ApplyNow email test",
                "html": "<p>This is a test email from ApplyNow. If you see this, email delivery is working.</p>",
            },
        )
    return {
        "ok": resp.status_code in (200, 201),
        "status_code": resp.status_code,
        "resend_response": resp.json() if resp.content else {},
        "from": settings.resend_from_email,
        "to": current_user.email,
    }


@router.get("/test-exa")
async def test_exa(current_user: User = Depends(get_current_user)):
    """Quick sanity-check: hits Exa neural search with a Stripe engineer query."""
    if not settings.exa_api_key:
        return {"error": "EXA_API_KEY not configured"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.exa.ai/search",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": settings.exa_api_key,
                },
                json={
                    "query": "Software Engineer at Stripe",
                    "category": "people",
                    "includeDomains": ["linkedin.com"],
                    "numResults": 3,
                    "type": "neural",
                },
            )
            data = resp.json()
            results = data.get("results") or []
            return {
                "status_code": resp.status_code,
                "result_count": len(results),
                "sample": [
                    {"title": r.get("title"), "url": r.get("url")}
                    for r in results
                ],
            }
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/runs")
async def list_runs(
    agent_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(AgentRun)
        .where(AgentRun.user_id == current_user.id)
        .order_by(desc(AgentRun.started_at))
        .limit(limit)
    )
    if agent_type:
        query = query.where(AgentRun.agent_type == agent_type)

    result = await db.execute(query)
    runs = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "agent_type": r.agent_type,
            "trigger": r.trigger,
            "status": r.status,
            "jobs_found": r.jobs_found,
            "contacts_found": r.contacts_found,
            "applications_created": r.applications_created,
            "tokens_used": r.tokens_used,
            "duration_ms": r.duration_ms,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]
