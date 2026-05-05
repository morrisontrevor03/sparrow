"""PostHog analytics client — single shared instance for server-side event capture."""
import logging
from posthog import Posthog

from app.config import settings

logger = logging.getLogger(__name__)

posthog: Posthog | None = None


def init_posthog() -> None:
    global posthog
    if not settings.posthog_api_key:
        logger.warning("POSTHOG_API_KEY not set — analytics disabled")
        return
    posthog = Posthog(
        api_key=settings.posthog_api_key,
        host=settings.posthog_host,
    )
    logger.info("PostHog analytics initialised")


def shutdown_posthog() -> None:
    if posthog is not None:
        posthog.flush()
        posthog.shutdown()
