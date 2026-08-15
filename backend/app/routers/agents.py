import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.agent_run import AgentRun
from app.models.user import User

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    runs = (
        (
            await db.execute(
                select(AgentRun)
                .where(AgentRun.user_id == current_user.id)
                .order_by(desc(AgentRun.started_at))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(r.id),
            "campaign_id": str(r.campaign_id) if r.campaign_id else None,
            "agent_type": r.agent_type,
            "trigger": r.trigger,
            "status": r.status,
            "contacts_found": r.contacts_found,
            "drafts_written": r.drafts_written,
            "credits_spent": r.credits_spent,
            "tokens_used": r.tokens_used,
            "duration_ms": r.duration_ms,
            "error_message": r.error_message,
            "current_step": r.current_step,
            "output_summary": r.output_summary,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


@router.get("/health/exa")
async def check_exa(current_user: User = Depends(get_current_user)):
    """Sanity-check the people-search dependency."""
    if not settings.exa_api_key:
        return {"ok": False, "error": "EXA_API_KEY not configured"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.exa.ai/search",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": settings.exa_api_key,
                },
                json={
                    "query": "Head of Engineering at Stripe",
                    "category": "people",
                    "includeDomains": ["linkedin.com"],
                    "numResults": 3,
                    "type": "neural",
                },
            )
            results = resp.json().get("results") or []
            return {
                "ok": resp.status_code == 200,
                "status_code": resp.status_code,
                "result_count": len(results),
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
