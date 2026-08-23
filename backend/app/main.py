import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import Mount

from app.analytics import init_posthog, shutdown_posthog
from app.config import CREDIT_PACKS, pack_price_id, settings
from app.database import Base, engine
from app.mcp_server import mcp as mcp_server
from app.scheduler.jobs import register_jobs, scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _validate_env() -> None:
    warnings: list[str] = []
    errors: list[str] = []

    if not settings.anthropic_api_key:
        (errors if settings.environment == "production" else warnings).append("ANTHROPIC_API_KEY")
    if not settings.exa_api_key:
        warnings.append("EXA_API_KEY (contact discovery will not work)")
    if not settings.resend_api_key:
        warnings.append("RESEND_API_KEY (email sending will not work)")

    if settings.environment == "production":
        if settings.secret_key == "dev-secret-key-change-in-production":
            errors.append("SECRET_KEY (still using dev default — set a secure random value)")
        if not settings.stripe_secret_key:
            errors.append("STRIPE_SECRET_KEY")
        if not settings.stripe_webhook_secret:
            errors.append("STRIPE_WEBHOOK_SECRET")
        missing_packs = [
            pack_id for pack_id in CREDIT_PACKS if not pack_price_id(pack_id)
        ]
        if missing_packs:
            errors.append(f"Stripe price IDs for credit packs: {', '.join(missing_packs)}")

    for w in warnings:
        logger.warning("Missing env var: %s", w)
    if errors:
        raise RuntimeError("Missing required environment variables: " + ", ".join(errors))


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_env()
    init_posthog()

    # Create upload directory
    os.makedirs(settings.upload_dir, exist_ok=True)

    # Create tables (handled by Alembic in prod, kept here for dev convenience)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        logger.error(f"DB init failed (tables may not exist yet): {e}")

    # Start scheduler
    try:
        register_jobs()
        scheduler.start()
        logger.info("Scheduler started")
    except Exception as e:
        logger.error(f"Scheduler failed to start: {e}")

    # The MCP streamable-HTTP transport owns its own session manager, which must
    # be running for /mcp to accept connections.
    async with mcp_server.session_manager.run():
        logger.info("MCP server mounted at /mcp")
        yield

    scheduler.shutdown()
    logger.info("Scheduler stopped")
    shutdown_posthog()
    await engine.dispose()


app = FastAPI(
    title="Sparrow API",
    version="3.0.0",
    lifespan=lifespan,
)

def _cors_origins() -> list[str]:
    url = settings.frontend_url.rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    # Always allow both www and non-www so either subdomain works
    if "://www." in url:
        bare = url.replace("://www.", "://", 1)
        return [url, bare]
    else:
        www = url.replace("://", "://www.", 1)
        return [url, www]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
from app.routers import (  # noqa: E402
    agents,
    auth,
    billing,
    campaigns,
    contacts,
    dashboard,
    oauth,
    resume,
    settings_router,
)

app.include_router(auth.router)
app.include_router(resume.router)
app.include_router(campaigns.router)
app.include_router(contacts.router)
app.include_router(agents.router)
app.include_router(dashboard.router)
app.include_router(settings_router.router)
app.include_router(billing.router)

# OAuth discovery documents must live at the root — MCP clients probe
# /.well-known/oauth-protected-resource on the resource server's origin.
app.include_router(oauth.discovery_router)
app.include_router(oauth.router)

@app.get("/health")
async def health():
    return {"status": "ok"}


# The MCP endpoint. Its own auth layer answers 401 with the
# `WWW-Authenticate: Bearer resource_metadata=...` header clients need to
# discover where to authenticate.
#
# Mounted at the root rather than at "/mcp" deliberately. The sub-app already
# routes `/mcp` internally, so `app.mount("/mcp", ...)` yields `/mcp/mcp` and
# makes a POST to the advertised `/mcp` a 307 redirect to `/mcp/` — which many
# HTTP clients answer by dropping the Authorization header, so the connection
# fails with an auth error that points nowhere.
#
# This must stay the LAST route registered: Starlette matches in order, and a
# root mount registered any earlier swallows every route declared after it.
app.router.routes.append(
    Mount("/", app=mcp_server.streamable_http_app(streamable_http_path="/mcp"))
)
