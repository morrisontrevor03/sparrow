import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import engine
from app.database import Base
from app.scheduler.jobs import register_jobs, scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _validate_env() -> None:
    warnings: list[str] = []
    errors: list[str] = []

    if not settings.anthropic_api_key:
        (errors if settings.environment == "production" else warnings).append("ANTHROPIC_API_KEY")
    if not settings.exa_api_key:
        warnings.append("EXA_API_KEY (networking agent will not work)")
    if not settings.resend_api_key:
        warnings.append("RESEND_API_KEY (email sending will not work)")

    if settings.environment == "production":
        if settings.secret_key == "dev-secret-key-change-in-production":
            errors.append("SECRET_KEY (still using dev default — set a secure random value)")
        if not settings.stripe_secret_key:
            errors.append("STRIPE_SECRET_KEY")
        if not settings.stripe_webhook_secret:
            errors.append("STRIPE_WEBHOOK_SECRET")
        if not settings.stripe_pro_price_id:
            errors.append("STRIPE_PRO_PRICE_ID")

    for w in warnings:
        logger.warning("Missing env var: %s", w)
    if errors:
        raise RuntimeError("Missing required environment variables: " + ", ".join(errors))


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_env()

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

    yield

    scheduler.shutdown()
    logger.info("Scheduler stopped")
    await engine.dispose()


app = FastAPI(
    title="ApplyNow Agent API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
from app.routers import auth, resume, jobs, applications, contacts, agents, dashboard, settings_router, stripe_webhooks  # noqa: E402

app.include_router(auth.router)
app.include_router(resume.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(contacts.router)
app.include_router(agents.router)
app.include_router(dashboard.router)
app.include_router(settings_router.router)
app.include_router(stripe_webhooks.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
