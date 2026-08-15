"""PostHog analytics client — single shared instance for server-side event capture."""
import logging

from posthog import Posthog

from app.config import settings

logger = logging.getLogger(__name__)

posthog: Posthog | None = None


def init_posthog() -> None:
    """
    Initialise the shared client.

    Wrapped in a try/except on purpose: analytics is never worth a failed
    deploy. The `api_key=` keyword this used to pass was renamed to
    `project_api_key` in posthog 6, which turned a telemetry detail into a
    startup crash — the requirement is now pinned, and this is the backstop.
    """
    global posthog
    if not settings.posthog_api_key:
        logger.warning("POSTHOG_API_KEY not set — analytics disabled")
        return
    try:
        posthog = Posthog(
            project_api_key=settings.posthog_api_key,
            host=settings.posthog_host,
        )
        logger.info("PostHog analytics initialised")
    except Exception:
        posthog = None
        logger.exception("PostHog init failed — continuing without analytics")


def shutdown_posthog() -> None:
    if posthog is None:
        return
    try:
        posthog.flush()
        posthog.shutdown()
    except Exception:
        logger.debug("PostHog shutdown failed", exc_info=True)
