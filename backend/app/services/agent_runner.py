"""
Shared entry points for starting an outreach run.

Both the HTTP API and the MCP server start runs, so the pre-create / background
dispatch logic lives here rather than in either transport.
"""

import logging
import uuid

from app.database import AsyncSessionLocal
from app.models.agent_run import AgentRun

logger = logging.getLogger(__name__)


async def pre_create_run(
    user_id: uuid.UUID, campaign_id: uuid.UUID | None, trigger: str
) -> uuid.UUID:
    """
    Create a queued AgentRun before dispatching, so the UI has something to poll
    the moment the request returns.
    """
    async with AsyncSessionLocal() as db:
        run = AgentRun(
            user_id=user_id,
            campaign_id=campaign_id,
            agent_type="outreach",
            trigger=trigger,
            status="queued",
        )
        db.add(run)
        await db.commit()
        return run.id


async def run_outreach(
    user_id: uuid.UUID,
    campaign_id: uuid.UUID | None,
    trigger: str,
    run_id: uuid.UUID | None = None,
    **kwargs,
) -> dict:
    """Execute an outreach run in its own session. Safe to call as a background task."""
    from app.agents.outreach import OutreachAgent

    async with AsyncSessionLocal() as db:
        agent = OutreachAgent(db, user_id)
        try:
            return await agent.run(
                trigger=trigger, _run_id=run_id, campaign_id=campaign_id, **kwargs
            )
        except Exception:
            logger.exception("Outreach run failed for user=%s campaign=%s", user_id, campaign_id)
            raise
