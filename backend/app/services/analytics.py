import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

POSTHOG_API = "https://us.i.posthog.com"


async def posthog_capture(distinct_id: str, event: str, properties: dict | None = None) -> None:
    key = getattr(settings, "posthog_api_key", "")
    if not key:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{POSTHOG_API}/capture/",
                json={
                    "api_key": key,
                    "distinct_id": distinct_id,
                    "event": event,
                    "properties": properties or {},
                },
            )
    except Exception:
        logger.debug("PostHog capture failed silently for event %s", event)
